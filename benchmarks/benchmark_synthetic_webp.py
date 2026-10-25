"""
ST-BAR (Spatio-Temporal Block-Aligned Stabilization & Delta Routing)
Benchmark Suite & Dataset Generator for Animated WebP / APNG Optimization Research.
"""

import io
import os
import time
import struct
import numpy as np
import cv2
from PIL import Image
from skimage.metrics import structural_similarity as ssim
from skimage.metrics import peak_signal_noise_ratio as psnr


def generate_benchmark_sequences(num_frames=36, width=320, height=240, seed=42):
    """
    Generates 4 realistic & challenging animated image sequences (RGBA/RGB):
    1. 'noisy_cinemagraph': Smooth photographic background + moving subject + realistic sensor noise (sigma=3.5).
       Tests temporal boiling / double-delta penalty in lossy & lossless codecs.
    2. 'disjoint_corners': High-detail background with two small independent animations in top-left & bottom-right.
       Tests bounding-box waste and sub-frame decomposition.
    3. 'gradient_sprite': Complex moving gradient background + bouncing translucent/anti-aliased objects.
       Tests block-boundary fragmentation (alpha mask edge explosion in VP8 DCT / VP8L predictors).
    4. 'ui_screencast': Sharp text/UI dashboard with cursor movement, typing, and localized hover highlights + subtle compression noise.
       Tests sharp-edge preservation and sub-frame delta efficiency.
    """
    rng = np.random.default_rng(seed)
    sequences = {}

    # 1. Noisy Cinemagraph (Natural Scene with localized motion + sensor noise)
    clean_seq1 = []
    noisy_seq1 = []
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    # Rich textured static background (sky/water/foliage simulation)
    bg1 = np.zeros((height, width, 3), dtype=np.float32)
    bg1[..., 0] = 60 + 80 * (yy / height) + 25 * np.sin(xx / 18.0) * np.cos(yy / 22.0)
    bg1[..., 1] = 90 + 60 * (xx / width) + 20 * np.cos((xx + yy) / 15.0)
    bg1[..., 2] = 140 - 50 * (yy / height) + 15 * np.sin(yy / 10.0)
    # Add fine static texture
    fine_tex = rng.normal(0, 6.0, (height, width, 3)).astype(np.float32)
    fine_tex = cv2.GaussianBlur(fine_tex, (3, 3), 0.8)
    bg1 = np.clip(bg1 + fine_tex, 0, 255)

    for t in range(num_frames):
        frame = bg1.copy()
        angle = 2 * np.pi * t / num_frames
        # Moving pendulum / object in the center
        cx = int(width * 0.5 + 55 * np.sin(angle))
        cy = int(height * 0.5 + 30 * np.cos(2 * angle))
        # Draw smooth shaded sphere
        dist2 = (xx - cx) ** 2 + (yy - cy) ** 2
        radius = 28.0
        mask = dist2 < radius ** 2
        z = np.sqrt(np.maximum(0, radius ** 2 - dist2)) / radius
        frame[mask, 0] = np.clip(220 * z[mask] + 30, 0, 255)
        frame[mask, 1] = np.clip(100 * z[mask] + 20, 0, 255)
        frame[mask, 2] = np.clip(70 * z[mask] + 40, 0, 255)

        clean_u8 = np.clip(np.round(frame), 0, 255).astype(np.uint8)
        clean_seq1.append(clean_u8)

        # Realistic video capture noise (camera sensor + YUV420 quantization jitter)
        noise = rng.normal(0, 3.2, (height, width, 3)).astype(np.float32)
        noisy_u8 = np.clip(np.round(frame + noise), 0, 255).astype(np.uint8)
        noisy_seq1.append(noisy_u8)

    sequences["noisy_cinemagraph"] = {
        "input": noisy_seq1,
        "ground_truth": clean_seq1,
        "duration_ms": 50,
    }

    # 2. Disjoint Corners (Two small active regions at opposite corners + slight background jitter)
    clean_seq2 = []
    noisy_seq2 = []
    bg2 = np.zeros((height, width, 3), dtype=np.float32)
    bg2[..., 0] = 40 + 120 * (xx / width)
    bg2[..., 1] = 50 + 100 * (yy / height)
    bg2[..., 2] = 80 + 60 * np.sin(xx / 25.0) * np.sin(yy / 25.0)
    bg2 = np.clip(bg2, 0, 255)

    for t in range(num_frames):
        frame = bg2.copy()
        angle = 2 * np.pi * t / num_frames
        # Top-left spinner
        tl_x, tl_y = int(40 + 14 * np.cos(angle)), int(36 + 14 * np.sin(angle))
        cv2.circle(frame, (tl_x, tl_y), 10, (245, 200, 60), -1, lineType=cv2.LINE_AA)
        # Bottom-right pulsing badge
        br_x, br_y = int(width - 44 + 12 * np.sin(angle)), int(height - 38 + 12 * np.cos(angle))
        cv2.rectangle(frame, (br_x - 12, br_y - 10), (br_x + 12, br_y + 10), (70, 230, 140), -1)

        clean_u8 = np.clip(np.round(frame), 0, 255).astype(np.uint8)
        clean_seq2.append(clean_u8)

        # Slight MPEG/capture dither noise in background (amplitude +/- 2)
        noise = rng.integers(-2, 3, (height, width, 3), dtype=np.int16)
        noisy_u8 = np.clip(clean_u8.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        noisy_seq2.append(noisy_u8)

    sequences["disjoint_corners"] = {
        "input": noisy_seq2,
        "ground_truth": clean_seq2,
        "duration_ms": 50,
    }

    # 3. Gradient Sprite (Rich soft gradient with moving overlapping shapes & temporal shimmer)
    clean_seq3 = []
    noisy_seq3 = []
    for t in range(num_frames):
        frame = bg1.copy()
        # Multiple moving circles that create complex ring deltas when compared frame-to-frame
        for k in range(3):
            phase = 2 * np.pi * (t / num_frames + k / 3.0)
            cx = int(width * 0.5 + (70 - k * 15) * np.cos(phase))
            cy = int(height * 0.5 + (45 - k * 10) * np.sin(phase * 1.0))
            color = (int(80 + 70 * k), int(220 - 50 * k), int(150 + 40 * (k % 2)))
            cv2.circle(frame, (cx, cy), 22 - k * 3, color, -1, lineType=cv2.LINE_AA)

        clean_u8 = np.clip(np.round(frame), 0, 255).astype(np.uint8)
        clean_seq3.append(clean_u8)

        # Temporal spike noise: occasional pixels oscillating +/- 4
        spike_mask = rng.random((height, width, 1)) < 0.25
        noise = (rng.normal(0, 2.5, (height, width, 3)) * spike_mask).astype(np.float32)
        noisy_u8 = np.clip(np.round(frame + noise), 0, 255).astype(np.uint8)
        noisy_seq3.append(noisy_u8)

    sequences["gradient_sprite"] = {
        "input": noisy_seq3,
        "ground_truth": clean_seq3,
        "duration_ms": 50,
    }

    # 4. UI Screencast (Sharp text, boxes, cursor movement, progress bar, slight capture noise)
    clean_seq4 = []
    noisy_seq4 = []
    ui_bg = np.full((height, width, 3), (30, 34, 42), dtype=np.uint8)
    # Sidebar & header
    cv2.rectangle(ui_bg, (0, 0), (75, height), (22, 25, 31), -1)
    cv2.rectangle(ui_bg, (75, 0), (width, 32), (38, 43, 54), -1)
    # Static text lines and cards
    for row in range(4):
        y0 = 48 + row * 44
        cv2.rectangle(ui_bg, (90, y0), (width - 18, y0 + 34), (45, 50, 62), -1)
        cv2.putText(ui_bg, f"Task_Node_{row+1}: Active", (100, y0 + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (210, 215, 225), 1, cv2.LINE_AA)

    for t in range(num_frames):
        frame = ui_bg.copy()
        # Animated progress bar in card 0
        prog_w = int(160 * ((t + 1) / num_frames))
        cv2.rectangle(frame, (100, 74), (100 + prog_w, 78), (80, 190, 250), -1)
        # Animated cursor moving across UI
        cur_x = int(110 + 150 * (0.5 + 0.5 * np.sin(2 * np.pi * t / num_frames)))
        cur_y = int(60 + 120 * (t / num_frames))
        pts = np.array([[cur_x, cur_y], [cur_x, cur_y + 14], [cur_x + 10, cur_y + 10]], np.int32)
        cv2.fillPoly(frame, [pts], (255, 255, 255), lineType=cv2.LINE_AA)

        clean_seq4.append(frame)
        # Screen capture often has slight YUV chroma subsampling jitter (+/- 1~2)
        noise = rng.integers(-1, 2, (height, width, 3), dtype=np.int16)
        noisy_u8 = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        noisy_seq4.append(noisy_u8)

    sequences["ui_screencast"] = {
        "input": noisy_seq4,
        "ground_truth": clean_seq4,
        "duration_ms": 50,
    }

    return sequences


def decode_webp_animation(webp_bytes):
    """Decodes an Animated WebP byte buffer into a list of RGB numpy arrays."""
    im = Image.open(io.BytesIO(webp_bytes))
    frames = []
    try:
        while True:
            frames.append(np.array(im.convert("RGB")))
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    return frames


def compute_metrics(decoded_frames, ground_truth_frames, input_frames):
    """
    Computes:
    - PSNR vs Ground Truth (Clean) & vs Input
    - SSIM vs Ground Truth (Clean)
    - Temporal Flicker Index (TFI): Mean temporal variation in static ground-truth regions!
      Lower TFI = better temporal stability (less background boiling/flicker).
    """
    psnr_gt_list = []
    psnr_in_list = []
    ssim_gt_list = []
    flicker_vals = []

    for t in range(len(decoded_frames)):
        dec = decoded_frames[t]
        gt = ground_truth_frames[t]
        inp = input_frames[t]

        psnr_gt_list.append(psnr(gt, dec, data_range=255))
        psnr_in_list.append(psnr(inp, dec, data_range=255))
        ssim_gt_list.append(ssim(gt, dec, data_range=255, channel_axis=2))

        if t > 0:
            # Find pixels that are truly static in Ground Truth between t-1 and t
            gt_diff = np.max(np.abs(ground_truth_frames[t].astype(np.int16) - ground_truth_frames[t - 1].astype(np.int16)), axis=2)
            static_mask = gt_diff == 0
            if np.any(static_mask):
                dec_diff = np.abs(dec.astype(np.float32) - decoded_frames[t - 1].astype(np.float32))
                flicker_vals.append(float(np.mean(dec_diff[static_mask])))

    return {
        "psnr_gt": float(np.mean(psnr_gt_list)),
        "psnr_in": float(np.mean(psnr_in_list)),
        "ssim_gt": float(np.mean(ssim_gt_list)),
        "flicker_index": float(np.mean(flicker_vals)) if flicker_vals else 0.0,
    }


def encode_baseline_libwebp(frames, duration_ms=50, lossless=False, quality=80, method=4, minimize_size=False):
    """Standard Pillow / libwebp WebPAnimEncoder baseline."""
    pil_frames = [Image.fromarray(f) for f in frames]
    buf = io.BytesIO()
    t0 = time.perf_counter()
    pil_frames[0].save(
        buf,
        format="WEBP",
        save_all=True,
        append_images=pil_frames[1:],
        duration=duration_ms,
        loop=0,
        lossless=lossless,
        quality=quality,
        method=method,
        minimize_size=minimize_size,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return buf.getvalue(), elapsed_ms


if __name__ == "__main__":
    seqs = generate_benchmark_sequences()
    print(f"Generated {len(seqs)} benchmark sequences.")
    for name, data in seqs.items():
        for mode_name, lossless, q, min_sz in [
            ("Lossy_Fast (q=80, m=4, min_sz=False)", False, 80, False),
            ("Lossy_Slow (q=80, m=6, min_sz=True)", False, 80, True),
            ("Lossless_Fast (m=4, min_sz=False)", True, 80, False),
        ]:
            blob, ms = encode_baseline_libwebp(
                data["input"], data["duration_ms"], lossless=lossless, quality=q,
                method=6 if min_sz else 4, minimize_size=min_sz
            )
            dec = decode_webp_animation(blob)
            m = compute_metrics(dec, data["ground_truth"], data["input"])
            print(
                f"[{name:18s}] {mode_name:36s} | Size: {len(blob):8,d} B | "
                f"Time: {ms:6.1f} ms | PSNR(GT): {m['psnr_gt']:5.2f} dB | "
                f"SSIM(GT): {m['ssim_gt']:.4f} | Flicker: {m['flicker_index']:.3f}"
            )
