"""
ST-GIF v3: Ultra-Fast Pure-uint8 Spatio-Temporal Stabilization & Prefix-Doubling LZW-RDO GIF Optimizer.
Supports continuous quality slider (1..100) and real-time GUI progress callbacks.
"""

import time
import numpy as np
import cv2
from PIL import Image
from scipy.spatial import cKDTree

from .st_bar_webp import (
    max_channel_u8,
    fast_bounding_box,
    estimate_game_capture_noise_sigma,
    stabilize_pure_u8_fast,
)
from .gif89a_muxer import assemble_gif89a


BAYER_4X4 = (
    np.array(
        [
            [0, 8, 2, 10],
            [12, 4, 14, 6],
            [3, 11, 1, 9],
            [15, 7, 13, 5],
        ],
        dtype=np.int16,
    )
    - 7
)


def build_motion_weighted_palette_and_lut(
    stab_frames: list[np.ndarray],
    motion_masks: list[np.ndarray],
    num_colors: int = 255,
) -> tuple[np.ndarray, np.ndarray]:
    H, W, _ = stab_frames[0].shape
    T = len(stab_frames)

    sample_pixels = []
    frame_stride = max(1, T // 20)
    for t in range(0, T, frame_stride):
        sample_pixels.append(stab_frames[t][::4, ::4].reshape(-1, 3))

    for t in range(1, T, frame_stride):
        m = motion_masks[t]
        if np.any(m):
            active_pts = stab_frames[t][m]
            if len(active_pts) > 3000:
                idx = np.linspace(0, len(active_pts) - 1, 3000, dtype=np.int32)
                active_pts = active_pts[idx]
            sample_pixels.append(active_pts)

    all_samples = np.vstack(sample_pixels)
    n_pts = len(all_samples)
    side = int(np.ceil(np.sqrt(n_pts)))
    padded = np.zeros((side * side, 3), dtype=np.uint8)
    padded[:n_pts] = all_samples
    padded[n_pts:] = all_samples[: (side * side - n_pts)]
    sample_img = Image.fromarray(padded.reshape(side, side, 3), mode="RGB")

    q_img = sample_img.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw_pal = np.array(q_img.getpalette(), dtype=np.uint8).reshape(-1, 3)

    used_idx = np.unique(np.array(q_img))
    used_idx = used_idx[used_idx < min(num_colors, len(raw_pal))]
    valid_pal = raw_pal[used_idx]

    luma = 0.299 * valid_pal[:, 0] + 0.587 * valid_pal[:, 1] + 0.114 * valid_pal[:, 2]
    order = np.argsort(luma)
    sorted_pal = valid_pal[order]
    n_valid = len(sorted_pal)

    full_palette = np.zeros((256, 3), dtype=np.uint8)
    full_palette[:n_valid] = sorted_pal
    full_palette[255] = [0, 0, 0]

    weights = np.array([1.0, 1.15, 0.85], dtype=np.float32)
    tree = cKDTree(sorted_pal.astype(np.float32) * weights)

    grid_r, grid_g, grid_b = np.mgrid[0:64, 0:64, 0:64]
    grid_pts = np.stack([grid_r * 4 + 2, grid_g * 4 + 2, grid_b * 4 + 2], axis=-1).reshape(-1, 3).astype(np.float32)
    _, indices = tree.query(grid_pts * weights, k=1)
    lut3d = indices.astype(np.uint8).reshape(64, 64, 64)

    return full_palette, lut3d


def quantize_frame_with_locked_bayer(
    rgb: np.ndarray,
    lut3d: np.ndarray,
    palette: np.ndarray,
    bayer_tiled: np.ndarray,
    dither_strength: float = 0.18,
) -> np.ndarray:
    idx0 = lut3d[rgb[..., 0] >> 2, rgb[..., 1] >> 2, rgb[..., 2] >> 2]
    if dither_strength <= 0.0:
        return idx0

    q_rgb = palette[idx0]
    q_err = max_channel_u8(cv2.absdiff(rgb, q_rgb))

    offset = (bayer_tiled * dither_strength).astype(np.int16)[:, :, None]
    dithered_rgb = np.clip(rgb.astype(np.int16) + offset, 0, 255).astype(np.uint8)
    idx_dither = lut3d[dithered_rgb[..., 0] >> 2, dithered_rgb[..., 1] >> 2, dithered_rgb[..., 2] >> 2]

    return np.where(q_err > 7, idx_dither, idx0)


def coalesce_lzw_horizontal_runs(
    idx_map: np.ndarray,
    target_rgb: np.ndarray,
    palette: np.ndarray,
    max_rgb_tol: int = 7,
) -> np.ndarray:
    if max_rgb_tol <= 0:
        return idx_map
    out = idx_map.copy()
    H, W = out.shape

    even_len = (W // 2) * 2
    if even_len >= 2:
        left_idx = out[:, 0:even_len:2]
        curr_idx = out[:, 1:even_len:2]
        diff_mask = curr_idx != left_idx
        if np.any(diff_mask):
            err = max_channel_u8(cv2.absdiff(target_rgb[:, 1:even_len:2], palette[left_idx]))
            out[:, 1:even_len:2] = np.where(diff_mask & (err <= max_rgb_tol), left_idx, curr_idx)

    quad_len = (W // 4) * 4
    if quad_len >= 4:
        anchor_idx = out[:, 1:quad_len:4]
        anchor_rgb = palette[anchor_idx]
        for offset in (2, 3):
            c_idx = out[:, offset:quad_len:4]
            err_c = max_channel_u8(cv2.absdiff(target_rgb[:, offset:quad_len:4], anchor_rgb))
            out[:, offset:quad_len:4] = np.where(err_c <= max_rgb_tol, anchor_idx, c_idx)

    oct_len = (W // 8) * 8
    if oct_len >= 8:
        anchor8_idx = out[:, 3:oct_len:8]
        anchor8_rgb = palette[anchor8_idx]
        for offset in (4, 5, 6, 7):
            c_idx = out[:, offset:oct_len:8]
            err_c = max_channel_u8(cv2.absdiff(target_rgb[:, offset:oct_len:8], anchor8_rgb))
            out[:, offset:oct_len:8] = np.where(err_c <= max_rgb_tol, anchor8_idx, c_idx)

    odd_end = ((W - 1) // 2) * 2 + 1
    if odd_end >= 3:
        left_idx2 = out[:, 1 : odd_end - 1 : 2]
        curr_idx2 = out[:, 2:odd_end:2]
        diff_mask2 = curr_idx2 != left_idx2
        if np.any(diff_mask2):
            err2 = max_channel_u8(cv2.absdiff(target_rgb[:, 2:odd_end:2], palette[left_idx2]))
            out[:, 2:odd_end:2] = np.where(diff_mask2 & (err2 <= max_rgb_tol), left_idx2, curr_idx2)

    return out


def map_quality_to_st_gif_params(quality: int, base_sigma: float) -> dict:
    """
    Maps a continuous user quality slider `quality` in [1, 100] to ST-GIF v3 internal parameters:
    - quality = 100: Ultra-high fidelity (255 colors, gentle hysteresis, subtle locked Bayer dither)
    - quality = 75:  Default Balanced sweet spot
    - quality = 45:  Compact mode (aggressive LZW run coalescing, zero dither)
    - quality = 15:  Extreme compression (reduced palette colors + strong Voronoi lock)
    """
    q = float(np.clip(quality, 1, 100)) / 100.0

    if q >= 0.45:
        num_colors = 255
    else:
        # Smoothly reduce palette size from 255 down to 64 for extreme compression below q=45
        num_colors = int(round(64 + (255 - 64) * (q / 0.45)))

    eff_sigma = base_sigma * (1.50 - 0.85 * q)
    voronoi_keep_tol = max(2, int(round(14.0 - 11.5 * q)))
    voronoi_gain_min = max(1, int(round(7.5 - 6.0 * q)))
    lzw_run_tol = max(2, int(round(13.5 - 10.5 * q)))
    dither_str = 0.0 if q <= 0.50 else float(0.28 * ((q - 0.50) / 0.50))

    return {
        "num_colors": num_colors,
        "eff_sigma": eff_sigma,
        "voronoi_keep_tol": voronoi_keep_tol,
        "voronoi_gain_min": voronoi_gain_min,
        "lzw_run_tol": lzw_run_tol,
        "dither_str": dither_str,
    }


def encode_st_gif(
    frames: list[np.ndarray],
    durations_ms: list[int] | int = 33,
    quality: int = 75,
    mode: str | None = None,
    progress_callback=None,
) -> tuple[bytes, float]:
    """
    Full ST-GIF v3 Optimization Pipeline with continuous quality slider (1..100).
    If `mode` ('high_quality', 'balanced', 'compact') is passed, maps it to quality (90, 75, 45).
    """
    t0 = time.perf_counter()
    T = len(frames)
    H, W, _ = frames[0].shape

    if isinstance(durations_ms, int):
        durations_ms = [durations_ms] * T

    if mode == "high_quality":
        quality = 90
    elif mode == "compact":
        quality = 45
    elif mode == "balanced":
        quality = 75

    base_sigma = estimate_game_capture_noise_sigma(frames)
    params = map_quality_to_st_gif_params(quality, base_sigma)

    eff_sigma = params["eff_sigma"]
    voronoi_keep_tol = params["voronoi_keep_tol"]
    voronoi_gain_min = params["voronoi_gain_min"]
    lzw_run_tol = params["lzw_run_tol"]
    dither_str = params["dither_str"]
    num_colors = params["num_colors"]

    if progress_callback:
        progress_callback(0.10, "1/4 시공간 노이즈 안정화 및 배경 고정 중...")

    stab_frames, motion_masks = stabilize_pure_u8_fast(
        frames, noise_sigma=eff_sigma, anisotropic_smooth=True
    )

    if progress_callback:
        progress_callback(0.28, f"2/4 모션 가중 팔레트({num_colors}색) 및 3D LUT 생성 중...")

    palette, lut3d = build_motion_weighted_palette_and_lut(
        stab_frames, motion_masks, num_colors=num_colors
    )

    bayer_tiled = np.tile(BAYER_4X4, (H // 4 + 1, W // 4 + 1))[:H, :W]

    idx0 = quantize_frame_with_locked_bayer(stab_frames[0], lut3d, palette, bayer_tiled, dither_str)
    idx0 = coalesce_lzw_horizontal_runs(idx0, stab_frames[0], palette, max_rgb_tol=lzw_run_tol)

    canvas_idx = idx0.copy()
    canvas_rgb = palette[canvas_idx]

    subframes = [
        {
            "x": 0,
            "y": 0,
            "w": W,
            "h": H,
            "indices": idx0,
            "delay_cs": max(2, int(round(durations_ms[0] / 10.0))),
            "transparent": False,
            "dispose": 1,
        }
    ]

    for t in range(1, T):
        if progress_callback and (t % max(1, T // 10) == 0):
            progress_callback(0.32 + 0.55 * (t / T), f"3/4 폐루프 LZW-RDO 델타 양자화 중 ({t}/{T})...")

        f_curr = stab_frames[t]
        m_mask = motion_masks[t]
        delay_cs = max(2, int(round(durations_ms[t] / 10.0)))

        drift_err = max_channel_u8(cv2.absdiff(f_curr, canvas_rgb))
        active_mask = m_mask | (drift_err > max(14, voronoi_keep_tol * 2))

        bbox = fast_bounding_box(active_mask)
        if bbox is None:
            subframes[-1]["delay_cs"] += delay_cs
            continue

        x0, y0, x1, y1 = bbox
        sub_target = f_curr[y0:y1, x0:x1]
        sub_motion = active_mask[y0:y1, x0:x1]
        sub_bayer = bayer_tiled[y0:y1, x0:x1]
        sub_canvas_idx = canvas_idx[y0:y1, x0:x1]
        sub_canvas_rgb = canvas_rgb[y0:y1, x0:x1]

        sub_new_idx = quantize_frame_with_locked_bayer(sub_target, lut3d, palette, sub_bayer, dither_str)
        sub_new_idx = coalesce_lzw_horizontal_runs(sub_new_idx, sub_target, palette, max_rgb_tol=lzw_run_tol)
        sub_new_rgb = palette[sub_new_idx]

        err_old = max_channel_u8(cv2.absdiff(sub_target, sub_canvas_rgb))
        err_new = max_channel_u8(cv2.absdiff(sub_target, sub_new_rgb))

        keep_canvas = (
            (~sub_motion)
            | (sub_new_idx == sub_canvas_idx)
            | (err_old <= voronoi_keep_tol)
            | (err_old.astype(np.int16) - err_new.astype(np.int16) <= voronoi_gain_min)
        )

        active_update = ~keep_canvas
        act_u8 = active_update.astype(np.uint8)
        act_neighbors = cv2.boxFilter(act_u8, ddepth=-1, ksize=(3, 3), normalize=False)
        speckle = active_update & (act_neighbors <= 2) & (err_old <= voronoi_keep_tol * 2 + 2)
        keep_canvas |= speckle
        active_update = ~keep_canvas

        if active_update.shape[1] >= 4:
            iso_1px = (
                active_update[:, 1:-1]
                & keep_canvas[:, :-2]
                & keep_canvas[:, 2:]
                & (err_old[:, 1:-1] <= voronoi_keep_tol * 2 + 2)
            )
            keep_canvas[:, 1:-1] |= iso_1px
            active_update = ~keep_canvas

            iso_2px = (
                active_update[:, 1:-2]
                & active_update[:, 2:-1]
                & keep_canvas[:, :-3]
                & keep_canvas[:, 3:]
                & (err_old[:, 1:-2] <= voronoi_keep_tol * 2)
                & (err_old[:, 2:-1] <= voronoi_keep_tol * 2)
            )
            keep_canvas[:, 1:-2] |= iso_2px
            keep_canvas[:, 2:-1] |= iso_2px
            active_update = ~keep_canvas

        rbbox = fast_bounding_box(active_update)
        if rbbox is None:
            subframes[-1]["delay_cs"] += delay_cs
            continue

        rx0, ry0, rx1, ry1 = rbbox
        final_keep = keep_canvas[ry0:ry1, rx0:rx1]
        final_new_idx = sub_new_idx[ry0:ry1, rx0:rx1]
        final_delta_indices = np.where(final_keep, 255, final_new_idx).astype(np.uint8)

        upd_slice_y = slice(y0 + ry0, y0 + ry1)
        upd_slice_x = slice(x0 + rx0, x0 + rx1)
        upd_mask = ~final_keep
        canvas_idx[upd_slice_y, upd_slice_x] = np.where(
            upd_mask, final_new_idx, canvas_idx[upd_slice_y, upd_slice_x]
        )
        canvas_rgb[upd_slice_y, upd_slice_x] = palette[canvas_idx[upd_slice_y, upd_slice_x]]

        subframes.append(
            {
                "x": x0 + rx0,
                "y": y0 + ry0,
                "w": rx1 - rx0,
                "h": ry1 - ry0,
                "indices": final_delta_indices,
                "delay_cs": delay_cs,
                "transparent": True,
                "dispose": 1,
            }
        )

    if progress_callback:
        progress_callback(0.92, "4/4 GIF89a LZW 비트스트림 조립 중...")

    gif_bytes = assemble_gif89a(W, H, palette, subframes, loop_count=0)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    if progress_callback:
        progress_callback(1.0, "완료!")
    return gif_bytes, elapsed_ms
