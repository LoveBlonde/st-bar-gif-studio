"""
Real-World Game & Screen Capture Benchmark:
Tests ST-GIF (Balanced & Compact) against:
1. Pillow Standard GIF (save_all=True, optimize=True)
2. FFmpeg 2-Pass GIF (palettegen + paletteuse=dither=sierra2_4a:diff_mode=rectangle)
3. FFmpeg 2-Pass GIF (palettegen + paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle)
on real-world game and screen captures.
"""

import io
import os
import glob
import time
import subprocess
import tempfile
import numpy as np
from PIL import Image
from skimage.metrics import peak_signal_noise_ratio as psnr
from skimage.metrics import structural_similarity as ssim

from st_gif_codec import encode_st_gif
from st_bar_v4 import encode_st_bar_v4

CAPTURE_DIR = os.environ.get("ST_BENCHMARK_CAPTURE_DIR", "./sample_captures")
OUTPUT_DIR = os.environ.get("ST_BENCHMARK_OUTPUT_DIR", "./benchmark_outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_webp_sequence(path: str, max_frames: int = 150):
    im = Image.open(path)
    frames = []
    durations = []
    try:
        while len(frames) < max_frames:
            durations.append(im.info.get("duration", 33))
            frames.append(np.array(im.convert("RGB")))
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    return frames, durations


def decode_gif_frames(gif_bytes: bytes) -> tuple[list[np.ndarray], list[int]]:
    im = Image.open(io.BytesIO(gif_bytes))
    frames = []
    durations = []
    try:
        while True:
            durations.append(im.info.get("duration", 30))
            frames.append(np.array(im.convert("RGB")))
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    return frames, durations


def expand_vfr_to_original_timeline(
    dec_frames: list[np.ndarray],
    dec_durs: list[int],
    orig_count: int,
    orig_durs: list[int],
) -> list[np.ndarray]:
    """Maps VFR decoded GIF frames back onto the original frame timestamps for exact PSNR/SSIM comparison."""
    if len(dec_frames) == orig_count:
        return dec_frames
    dec_cum = np.cumsum([max(10, d) for d in dec_durs])
    orig_cum = np.cumsum([max(10, d) for d in orig_durs]) - (orig_durs[0] // 2)
    mapped = []
    for t_ms in orig_cum:
        idx = int(np.searchsorted(dec_cum, t_ms, side="left"))
        idx = min(idx, len(dec_frames) - 1)
        mapped.append(dec_frames[idx])
    return mapped


def eval_gif_quality(gif_bytes: bytes, orig_frames: list[np.ndarray], orig_durs: list[int]):
    dec_f, dec_d = decode_gif_frames(gif_bytes)
    aligned = expand_vfr_to_original_timeline(dec_f, dec_d, len(orig_frames), orig_durs)

    # Sample 20 evenly spaced frames for fast PSNR/SSIM evaluation on large HD frames
    step = max(1, len(orig_frames) // 20)
    psnr_list = []
    ssim_list = []
    flicker_list = []

    for i in range(0, len(orig_frames), step):
        o = orig_frames[i]
        d = aligned[i]
        psnr_list.append(psnr(o, d, data_range=255))
        # Downsample 2x for fast SSIM on large resolutions
        ssim_list.append(ssim(o[::2, ::2], d[::2, ::2], data_range=255, channel_axis=2))

        if i > 0:
            prev_o = orig_frames[i - 1]
            prev_d = aligned[i - 1]
            # Static region in source: where source changed by <= 3 (compression noise floor)
            src_diff = np.max(np.abs(o.astype(np.int16) - prev_o.astype(np.int16)), axis=2)
            static_mask = src_diff <= 3
            if np.any(static_mask):
                dec_diff = np.abs(d.astype(np.float32) - prev_d.astype(np.float32))
                flicker_list.append(float(np.mean(dec_diff[static_mask])))

    return {
        "psnr": float(np.mean(psnr_list)),
        "ssim": float(np.mean(ssim_list)),
        "flicker": float(np.mean(flicker_list)) if flicker_list else 0.0,
        "coded_frames": len(dec_f),
    }


def encode_pillow_gif(frames: list[np.ndarray], durations: list[int]) -> tuple[bytes, float]:
    t0 = time.perf_counter()
    pil_frames = [Image.fromarray(f) for f in frames]
    buf = io.BytesIO()
    pil_frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=pil_frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    return buf.getvalue(), (time.perf_counter() - t0) * 1000.0


def encode_ffmpeg_gif(frames: list[np.ndarray], durations: list[int], dither: str = "sierra2_4a") -> tuple[bytes, float]:
    """
    Runs FFmpeg's gold-standard 2-pass palettegen + paletteuse (with diff_mode=rectangle) via rawvideo pipe.
    """
    H, W, _ = frames[0].shape
    fps = 1000.0 / max(10.0, float(np.mean(durations)))
    raw_bytes = b"".join(f.tobytes() for f in frames)

    with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as tmp:
        out_path = tmp.name

    if dither == "bayer":
        dither_opt = "dither=bayer:bayer_scale=3:diff_mode=rectangle"
    else:
        dither_opt = f"dither={dither}:diff_mode=rectangle"

    filter_str = f"split[s0][s1];[s0]palettegen=reserve_transparent=1:stats_mode=diff[p];[s1][p]paletteuse={dither_opt}"

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", f"{fps:.2f}",
        "-i", "pipe:0",
        "-vf", filter_str,
        "-loop", "0",
        out_path,
    ]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, input=raw_bytes, capture_output=True)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {proc.stderr.decode('utf-8', errors='replace')}")

    with open(out_path, "rb") as f:
        gif_bytes = f.read()
    os.remove(out_path)
    return gif_bytes, elapsed_ms


def run_realworld_benchmark():
    all_files = sorted(glob.glob(os.path.join(CAPTURE_DIR, "*.webp")), key=os.path.getsize)
    # Select 4 diverse files:
    # 0: Clip 1 (892x619, 134f)
    # 1: Clip 2 (557x331, 106f)
    # 2: Clip 3 (496x395, 109f)
    # 8: Clip 4 (1051x482, 89f)
    test_indices = [0, 1, 2, 8]

    print("=" * 122)
    print("REAL-WORLD SCREEN & GAME CAPTURE GIF COMPRESSION BENCHMARK (Pillow vs FFmpeg 2-Pass vs ST-GIF)")
    print("=" * 122)

    for idx in test_indices:
        fpath = all_files[idx]
        fname = os.path.basename(fpath)
        base_name = os.path.splitext(fname)[0]
        orig_webp_sz = os.path.getsize(fpath)

        frames, durs = load_webp_sequence(fpath, max_frames=140)
        H, W, _ = frames[0].shape
        print(f"\n>>> File: {fname} | Source WebP: {orig_webp_sz/1024:,.1f} KB | Resolution: {W}x{H} | Frames: {len(frames)}")

        # 1. Pillow GIF
        b_pil, t_pil = encode_pillow_gif(frames, durs)
        m_pil = eval_gif_quality(b_pil, frames, durs)

        # 2. FFmpeg 2-Pass Sierra2_4a (Default HQ)
        b_ff_sierra, t_ff_sierra = encode_ffmpeg_gif(frames, durs, dither="sierra2_4a")
        m_ff_sierra = eval_gif_quality(b_ff_sierra, frames, durs)

        # 3. FFmpeg 2-Pass Bayer (Scale=3)
        b_ff_bayer, t_ff_bayer = encode_ffmpeg_gif(frames, durs, dither="bayer")
        m_ff_bayer = eval_gif_quality(b_ff_bayer, frames, durs)

        # 4. ST-GIF Balanced
        b_st_bal, t_st_bal = encode_st_gif(frames, durs, mode="balanced")
        m_st_bal = eval_gif_quality(b_st_bal, frames, durs)

        # 5. ST-GIF Compact
        b_st_cmp, t_st_cmp = encode_st_gif(frames, durs, mode="compact")
        m_st_cmp = eval_gif_quality(b_st_cmp, frames, durs)

        # Save outputs for inspection
        with open(os.path.join(OUTPUT_DIR, f"{base_name}_ffmpeg_sierra.gif"), "wb") as f:
            f.write(b_ff_sierra)
        with open(os.path.join(OUTPUT_DIR, f"{base_name}_st_gif_balanced.gif"), "wb") as f:
            f.write(b_st_bal)
        with open(os.path.join(OUTPUT_DIR, f"{base_name}_st_gif_compact.gif"), "wb") as f:
            f.write(b_st_cmp)

        print(f"  [1] Pillow Optimize GIF          | Size: {len(b_pil)/1024:8.1f} KB | Time: {t_pil:6.0f} ms | PSNR: {m_pil['psnr']:5.2f} dB | SSIM: {m_pil['ssim']:.4f} | Flicker: {m_pil['flicker']:.3f}")
        print(f"  [2] FFmpeg 2-Pass (sierra2_4a)   | Size: {len(b_ff_sierra)/1024:8.1f} KB | Time: {t_ff_sierra:6.0f} ms | PSNR: {m_ff_sierra['psnr']:5.2f} dB | SSIM: {m_ff_sierra['ssim']:.4f} | Flicker: {m_ff_sierra['flicker']:.3f}")
        print(f"  [3] FFmpeg 2-Pass (bayer_s3)     | Size: {len(b_ff_bayer)/1024:8.1f} KB | Time: {t_ff_bayer:6.0f} ms | PSNR: {m_ff_bayer['psnr']:5.2f} dB | SSIM: {m_ff_bayer['ssim']:.4f} | Flicker: {m_ff_bayer['flicker']:.3f}")
        print(f"  [4] ST-GIF Balanced (Ours)       | Size: {len(b_st_bal)/1024:8.1f} KB | Time: {t_st_bal:6.0f} ms | PSNR: {m_st_bal['psnr']:5.2f} dB | SSIM: {m_st_bal['ssim']:.4f} | Flicker: {m_st_bal['flicker']:.3f}  [{100*(1-len(b_st_bal)/len(b_ff_sierra)):+.1f}% vs FFmpeg-HQ, {100*(1-len(b_st_bal)/len(b_pil)):+.1f}% vs Pillow]")
        print(f"  [5] ST-GIF Compact  (Ours)       | Size: {len(b_st_cmp)/1024:8.1f} KB | Time: {t_st_cmp:6.0f} ms | PSNR: {m_st_cmp['psnr']:5.2f} dB | SSIM: {m_st_cmp['ssim']:.4f} | Flicker: {m_st_cmp['flicker']:.3f}  [{100*(1-len(b_st_cmp)/len(b_ff_sierra)):+.1f}% vs FFmpeg-HQ, {100*(1-len(b_st_cmp)/len(b_pil)):+.1f}% vs Pillow]")


if __name__ == "__main__":
    run_realworld_benchmark()
