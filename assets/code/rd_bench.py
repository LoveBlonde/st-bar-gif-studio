"""
Rate-distortion benchmark: ST-GIF v3 vs gifski vs gifsicle --lossy vs FFmpeg 2-pass.
Each encoder is swept over its quality knob; per-clip results are appended to results.jsonl.
"""
import io, os, sys, json, time, glob, shutil, subprocess, tempfile
import numpy as np
from PIL import Image
from skimage.metrics import peak_signal_noise_ratio as psnr
from skimage.metrics import structural_similarity as ssim

sys.path.insert(0, os.path.dirname(__file__))
from st_studio.st_gif_codec import encode_st_gif

CLIP_DIR = "/mnt/user-data/uploads/ScreenCapture"
OUT = os.path.join(os.path.dirname(__file__), "results.jsonl")
GIF_DIR = os.path.join(os.path.dirname(__file__), "gifs")
os.makedirs(GIF_DIR, exist_ok=True)
GIFSKI = os.path.expanduser("~/.cargo/bin/gifski")
MAX_FRAMES = 140

ST_Q = [15, 30, 45, 60, 75, 90, 100]
GIFSKI_Q = [30, 50, 70, 90, 100]
LOSSY = [20, 40, 80, 140, 200]


def load(path):
    im = Image.open(path)
    frames, durs = [], []
    try:
        while len(frames) < MAX_FRAMES:
            durs.append(int(im.info.get("duration", 33) or 33))
            frames.append(np.array(im.convert("RGB")))
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    return frames, durs


def decode(gif_bytes):
    im = Image.open(io.BytesIO(gif_bytes))
    frames, durs = [], []
    try:
        while True:
            durs.append(int(im.info.get("duration", 30) or 30))
            frames.append(np.array(im.convert("RGB")))
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    return frames, durs


def align(dec_f, dec_d, orig_d):
    """Sample decoded (possibly VFR) GIF at the mid-point of each source frame's display interval."""
    dec_end = np.cumsum([max(10, d) for d in dec_d])
    o = np.array([max(10, d) for d in orig_d], dtype=np.float64)
    mids = np.cumsum(o) - o / 2.0
    # rescale if total durations differ (centisecond rounding / fixed-fps encoders)
    mids *= dec_end[-1] / np.sum(o)
    out = []
    for t in mids:
        k = min(int(np.searchsorted(dec_end, t, side="right")), len(dec_f) - 1)
        out.append(dec_f[k])
    return out


def evaluate(gif_bytes, orig, orig_d):
    dec_f, dec_d = decode(gif_bytes)
    if dec_f[0].shape != orig[0].shape:
        return {"error": f"shape {dec_f[0].shape} != {orig[0].shape}"}
    al = align(dec_f, dec_d, orig_d)
    T = len(orig)
    ps, ss, flick, tde = [], [], [], []
    for i in range(T):
        o, d = orig[i], al[i]
        ps.append(psnr(o, d, data_range=255))
        if i % max(1, T // 20) == 0:
            ss.append(ssim(o[::2, ::2], d[::2, ::2], data_range=255, channel_axis=2))
        if i > 0:
            po, pd = orig[i - 1].astype(np.int16), al[i - 1].astype(np.int16)
            do = o.astype(np.int16) - po
            dd = d.astype(np.int16) - pd
            static = np.max(np.abs(do), axis=2) <= 3
            if static.any():
                flick.append(float(np.abs(dd)[static].mean()))
            # temporal-difference error: how far decoded frame-to-frame change deviates from source change
            tde.append(float(np.abs(dd - do).mean()))
    mse = np.mean([10 ** (-p / 10) for p in ps if np.isfinite(p)]) if ps else 0
    return {
        "psnr": float(np.mean([min(p, 100) for p in ps])),
        "psnr_mse": float(-10 * np.log10(mse)) if mse > 0 else 100.0,
        "ssim": float(np.mean(ss)),
        "flicker": float(np.mean(flick)) if flick else 0.0,
        "tde": float(np.mean(tde)) if tde else 0.0,
        "coded_frames": len(dec_f),
    }


def ffmpeg_gif(frames, durs, dither):
    H, W, _ = frames[0].shape
    fps = 1000.0 / max(10.0, float(np.mean(durs)))
    opt = "dither=bayer:bayer_scale=3" if dither == "bayer" else f"dither={dither}"
    vf = f"split[s0][s1];[s0]palettegen=reserve_transparent=1:stats_mode=diff[p];[s1][p]paletteuse={opt}:diff_mode=rectangle"
    with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as t:
        out = t.name
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", f"{fps:.3f}", "-i", "pipe:0", "-vf", vf, "-loop", "0", out]
    t0 = time.perf_counter()
    subprocess.run(cmd, input=b"".join(f.tobytes() for f in frames), check=True, capture_output=True)
    ms = (time.perf_counter() - t0) * 1000
    b = open(out, "rb").read(); os.remove(out)
    return b, ms


def gifsicle(src_bytes, lossy):
    args = ["gifsicle", "-O3"] + ([f"--lossy={lossy}"] if lossy else [])
    t0 = time.perf_counter()
    p = subprocess.run(args, input=src_bytes, capture_output=True, check=True)
    return p.stdout, (time.perf_counter() - t0) * 1000


def gifski(png_dir, n, W, fps, q):
    with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as t:
        out = t.name
    files = [os.path.join(png_dir, f"{i:05d}.png") for i in range(n)]
    cmd = [GIFSKI, "--quiet", "-Q", str(q), "--fps", f"{fps:.3f}", "--width", str(W), "-o", out] + files
    t0 = time.perf_counter()
    subprocess.run(cmd, check=True, capture_output=True)
    ms = (time.perf_counter() - t0) * 1000
    b = open(out, "rb").read(); os.remove(out)
    return b, ms


def run_clip(path, done):
    name = os.path.basename(path)
    frames, durs = load(path)
    H, W, _ = frames[0].shape
    T = len(frames)
    fps = 1000.0 / max(10.0, float(np.mean(durs)))
    meta = {"clip": name, "W": W, "H": H, "T": T, "fps": fps, "src_bytes": os.path.getsize(path)}
    print(f">>> {name} {W}x{H} T={T} fps={fps:.1f}", flush=True)

    cfr = [int(round(1000.0 / fps))] * T  # timeline actually given to fixed-fps encoders (ffmpeg, gifski)

    def record(enc, param, b, ms, keep=False):
        if (name, enc, param) in done:
            return
        r = dict(meta, enc=enc, param=param, bytes=len(b), ms=ms)
        r.update(evaluate(b, frames, durs if enc == "st_gif" else cfr))
        with open(OUT, "a") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if keep:
            with open(os.path.join(GIF_DIR, f"{os.path.splitext(name)[0]}__{enc}_{param}.gif"), "wb") as f:
                f.write(b)
        print(f"   {enc:16s} {str(param):>4s} {len(b)/1024:9.1f} KB {ms:7.0f} ms  PSNR {r.get('psnr',0):5.2f}  "
              f"SSIM {r.get('ssim',0):.4f}  flk {r.get('flicker',0):.3f}  tde {r.get('tde',0):.3f}", flush=True)

    # FFmpeg baselines (+ gifsicle on top of each)
    for dither in ("sierra2_4a", "bayer"):
        b, ms = ffmpeg_gif(frames, durs, dither)
        record(f"ffmpeg_{dither}", 0, b, ms, keep=(dither == "sierra2_4a"))
        b0, ms0 = gifsicle(b, 0)
        record(f"gifsicle_O3_{dither}", 0, b0, ms + ms0)
        if dither == "bayer":
            continue  # lossy sweep on bayer input dropped for remaining clips (dominated by sierra input)
        for L in LOSSY:
            bl, msl = gifsicle(b, L)
            record(f"gifsicle_lossy_{dither}", L, bl, ms + msl, keep=(dither == "sierra2_4a" and L == 80))

    # gifski
    png_dir = tempfile.mkdtemp()
    for i, f in enumerate(frames):
        Image.fromarray(f).save(os.path.join(png_dir, f"{i:05d}.png"), compress_level=1)
    for q in GIFSKI_Q:
        b, ms = gifski(png_dir, T, W, fps, q)
        record("gifski", q, b, ms, keep=(q == 90))
    shutil.rmtree(png_dir)

    # ST-GIF v3
    for q in ST_Q:
        b, ms = encode_st_gif(frames, durs, quality=q)
        record("st_gif", q, b, ms, keep=(q in (45, 75)))


if __name__ == "__main__":
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            r = json.loads(l); done.add((r["clip"], r["enc"], r["param"]))
    clips = sorted(glob.glob(os.path.join(CLIP_DIR, "*.webp")), key=os.path.getsize)
    finished = {c for (c, e, p) in done if e == "st_gif" and p == 100}
    if len(sys.argv) > 2:  # worker k of n
        k, n = int(sys.argv[1]), int(sys.argv[2])
        clips = [c for c in clips if os.path.basename(c) not in finished][k::n]
    for c in clips:
        if os.path.basename(c) in finished:
            continue
        try:
            run_clip(c, done)
        except Exception as e:
            print("FAILED", c, repr(e), flush=True)
