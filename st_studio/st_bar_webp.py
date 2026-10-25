"""
ST-BAR v4: Pure-uint8/int16 AVX2 Spatio-Temporal Stabilization & 3-Way Entropy Subframe Router for Animated WebP.
Supports continuous quality slider (1..100) and progress callbacks.
"""

import time
import numpy as np
import cv2

from .webp_riff_muxer import (
    encode_subframe_payload,
    build_anmf_chunk,
    assemble_animated_webp,
)


def max_channel_u8(img3: np.ndarray) -> np.ndarray:
    b, g, r = cv2.split(img3)
    return cv2.max(cv2.max(b, g), r)


def fast_bounding_box(mask_bool: np.ndarray) -> tuple[int, int, int, int] | None:
    row_any = np.any(mask_bool, axis=1)
    if not np.any(row_any):
        return None
    col_any = np.any(mask_bool, axis=0)
    y0 = int(np.argmax(row_any))
    y1 = int(len(row_any) - np.argmax(row_any[::-1]))
    x0 = int(np.argmax(col_any))
    x1 = int(len(col_any) - np.argmax(col_any[::-1]))
    return x0, y0, x1, y1


def estimate_game_capture_noise_sigma(frames: list[np.ndarray]) -> float:
    T = len(frames)
    if T < 2:
        return 1.2
    block_means = []
    for t in range(1, T, max(1, T // 15)):
        d = max_channel_u8(cv2.absdiff(frames[t], frames[t - 1]))
        b8 = cv2.resize(
            d,
            (max(4, d.shape[1] // 8), max(4, d.shape[0] // 8)),
            interpolation=cv2.INTER_AREA,
        )
        block_means.append(b8.ravel())

    all_b8 = np.concatenate(block_means)
    nonzero_b8 = all_b8[all_b8 > 0]
    if len(nonzero_b8) == 0:
        return 1.2
    q25 = float(np.percentile(nonzero_b8, 25))
    return float(np.clip(q25 * 0.85, 1.0, 3.5))


def make_block_aligned_alpha_vec(active_mask: np.ndarray, block_size: int) -> np.ndarray:
    if block_size <= 1:
        return active_mask.astype(np.uint8) * 255

    sh, sw = active_mask.shape
    pad_h = (block_size - (sh % block_size)) % block_size
    pad_w = (block_size - (sw % block_size)) % block_size

    if pad_h > 0 or pad_w > 0:
        padded = np.pad(active_mask, ((0, pad_h), (0, pad_w)), mode="constant", constant_values=False)
    else:
        padded = active_mask

    ph, pw = padded.shape
    gh, gw = ph // block_size, pw // block_size
    blocks = padded.reshape(gh, block_size, gw, block_size).any(axis=(1, 3))
    expanded = np.repeat(np.repeat(blocks, block_size, axis=0), block_size, axis=1)
    return (expanded[:sh, :sw].astype(np.uint8)) * 255


def stabilize_pure_u8_fast(
    frames: list[np.ndarray],
    noise_sigma: float = 1.5,
    anisotropic_smooth: bool = True,
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    T = len(frames)
    H, W, _ = frames[0].shape
    if T == 1:
        return [frames[0].copy()], [np.ones((H, W), dtype=bool)]

    tau_u8 = int(round(max(4.0, 3.1 * noise_sigma)))

    pair_sim = []
    for t in range(T - 1):
        d_max = max_channel_u8(cv2.absdiff(frames[t], frames[t + 1]))
        pair_sim.append(cv2.compare(d_max, tau_u8, cv2.CMP_LE))

    temporal_clean = []
    for t in range(T):
        c = frames[t]
        if t > 0:
            nm1 = c.copy()
            cv2.copyTo(frames[t - 1], pair_sim[t - 1], nm1)
        else:
            nm1 = c

        if t + 1 < T:
            np1 = c.copy()
            cv2.copyTo(frames[t + 1], pair_sim[t], np1)
        else:
            np1 = c

        avg_near = cv2.addWeighted(nm1, 0.5, np1, 0.5, 0)
        clean_u8 = cv2.addWeighted(c, 0.45, avg_near, 0.55, 0)

        if anisotropic_smooth:
            horiz_blur = cv2.boxFilter(clean_u8, ddepth=-1, ksize=(3, 1), normalize=True)
            h_diff = max_channel_u8(cv2.absdiff(horiz_blur, clean_u8))
            h_mask = cv2.compare(h_diff, max(3, int(round(noise_sigma * 1.8))), cv2.CMP_LE)
            cv2.copyTo(horiz_blur, h_mask, clean_u8)

        temporal_clean.append(clean_u8)

    box_thresh_u8 = max(2, int(round(max(1.4, 0.72 * noise_sigma))))
    px_thresh_u8 = max(4, int(round(max(4.5, 3.3 * noise_sigma))))
    box_return_u8 = max(1, int(round(box_thresh_u8 * 0.85)))
    px_return_u8 = max(3, int(round(px_thresh_u8 * 0.75)))
    px_spike_cap = int(round(px_thresh_u8 * 1.8))
    px_strong_u8 = int(round(px_thresh_u8 * 1.5))

    box_clean = [cv2.boxFilter(f, ddepth=-1, ksize=(5, 5), normalize=True) for f in temporal_clean]

    anchor = temporal_clean[0].copy()
    box_anchor = box_clean[0].copy()

    stabilized = [anchor.copy()]
    motion_masks = [np.ones((H, W), dtype=bool)]
    k_dilate = np.ones((3, 3), np.uint8)

    for t in range(1, T):
        curr = temporal_clean[t]
        abs_diff_max = max_channel_u8(cv2.absdiff(curr, anchor))
        coherent_diff_5 = max_channel_u8(cv2.absdiff(box_clean[t], box_anchor))

        is_moving = (coherent_diff_5 > box_thresh_u8) | (abs_diff_max > px_thresh_u8)

        if t + 1 < T:
            next_vs_anchor = max_channel_u8(cv2.absdiff(temporal_clean[t + 1], anchor))
            box_next = max_channel_u8(cv2.absdiff(box_clean[t + 1], box_anchor))
            returns = (box_next <= box_return_u8) & (next_vs_anchor <= px_return_u8)
            spike = returns & (abs_diff_max < px_spike_cap)
            is_moving = is_moving & (~spike)

        m_u8 = is_moving.astype(np.uint8)
        neighbor_count = cv2.boxFilter(m_u8, ddepth=-1, ksize=(3, 3), normalize=False)
        is_moving_clean = (is_moving & (neighbor_count >= 2)) | (abs_diff_max > px_strong_u8)
        dilated_u8 = cv2.dilate(is_moving_clean.astype(np.uint8), k_dilate)

        cv2.copyTo(curr, dilated_u8, anchor)
        cv2.copyTo(box_clean[t], dilated_u8, box_anchor)

        stabilized.append(anchor.copy())
        motion_masks.append(dilated_u8 > 0)

    return stabilized, motion_masks


def encode_st_bar_webp(
    frames: list[np.ndarray],
    durations_ms: list[int] | int = 33,
    quality: int = 80,
    lossless: bool = False,
    progress_callback=None,
) -> tuple[bytes, float]:
    """
    ST-BAR v4 Animated WebP Encoder with continuous quality slider (1..100).
    """
    t0 = time.perf_counter()
    T = len(frames)
    H, W, _ = frames[0].shape

    if isinstance(durations_ms, int):
        durations_ms = [durations_ms] * T

    q_clamped = int(np.clip(quality, 1, 100))
    # Map slider 1..100 continuously to stabilization sensitivity
    base_sigma = estimate_game_capture_noise_sigma(frames)
    sigma_scale = 1.65 - 1.05 * (q_clamped / 100.0)  # q=100 -> 0.6x, q=75 -> 0.86x, q=20 -> 1.44x
    eff_sigma = base_sigma * sigma_scale

    if progress_callback:
        progress_callback(0.10, "시공간 노이즈 안정화 및 모션 분리 중...")

    stab_frames, motion_masks = stabilize_pure_u8_fast(frames, noise_sigma=eff_sigma, anisotropic_smooth=False)

    anmf_chunks = []
    any_alpha_used = False

    p0, a0 = encode_subframe_payload(stab_frames[0], lossless=lossless, quality=q_clamped, method=4)
    any_alpha_used = any_alpha_used or a0
    anmf_chunks.append(build_anmf_chunk(0, 0, W, H, durations_ms[0], True, False, p0))

    for t in range(1, T):
        if progress_callback and (t % max(1, T // 10) == 0):
            progress_callback(0.15 + 0.80 * (t / T), f"WebP 서브프레임 인코딩 중 ({t}/{T})...")

        mask = motion_masks[t]
        f_curr = stab_frames[t]
        dur = int(durations_ms[t])

        bbox = fast_bounding_box(mask)
        if bbox is None:
            sub_tiny = f_curr[0:2, 0:2]
            pt, _ = encode_subframe_payload(sub_tiny, lossless=True, method=1)
            anmf_chunks.append(build_anmf_chunk(0, 0, 2, 2, dur, True, False, pt))
            continue

        raw_x0, raw_y0, x1, y1 = bbox
        x0 = (raw_x0 // 2) * 2
        y0 = (raw_y0 // 2) * 2
        sub_w, sub_h = x1 - x0, y1 - y0
        box_area = sub_w * sub_h

        sub_rgb = f_curr[y0:y1, x0:x1]
        sub_mask = mask[y0:y1, x0:x1]
        active_px = int(np.sum(sub_mask))
        px_occupancy = active_px / float(box_area)

        if lossless:
            if px_occupancy > 0.88:
                payload, has_a = encode_subframe_payload(sub_rgb, lossless=True, method=4)
                no_blend = True
            else:
                alpha_u8 = (sub_mask.astype(np.uint8)) * 255
                rgba = np.dstack([sub_rgb, alpha_u8])
                payload, has_a = encode_subframe_payload(rgba, lossless=True, method=4, exact=False)
                no_blend = False
        else:
            alpha_b16 = make_block_aligned_alpha_vec(sub_mask, block_size=16)
            b16_occupancy = float(np.mean(alpha_b16 > 0))

            if px_occupancy < 0.22 and active_px < 2200:
                smooth_rgb = cv2.bilateralFilter(sub_rgb, d=5, sigmaColor=18.0, sigmaSpace=3.0)
                quant_rgb = ((smooth_rgb.astype(np.uint16) + 2) >> 2 << 2).clip(0, 255).astype(np.uint8)
                alpha_px = (sub_mask.astype(np.uint8)) * 255
                rgba_nl = np.dstack([quant_rgb, alpha_px])
                payload, has_a = encode_subframe_payload(rgba_nl, lossless=True, method=2, exact=False)
                no_blend = False
            elif b16_occupancy >= 0.60:
                payload, has_a = encode_subframe_payload(sub_rgb, lossless=False, quality=q_clamped, method=4)
                no_blend = True
            else:
                rgba_b16 = np.dstack([sub_rgb, alpha_b16])
                payload, has_a = encode_subframe_payload(
                    rgba_b16, lossless=False, quality=q_clamped, method=4, exact=False
                )
                no_blend = False

        any_alpha_used = any_alpha_used or has_a or (not no_blend)
        anmf_chunks.append(build_anmf_chunk(x0, y0, sub_w, sub_h, dur, no_blend, False, payload))

    if progress_callback:
        progress_callback(0.98, "RIFF WEBP 컨테이너 조립 완료 중...")

    webp_bytes = assemble_animated_webp(W, H, anmf_chunks, has_alpha=any_alpha_used)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return webp_bytes, elapsed_ms
