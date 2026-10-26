import os, sys, json, glob
sys.path.insert(0, os.path.dirname(__file__))
import rd_bench as R
from st_studio import st_gif_ablate as A

VARIANTS = {
    "full": {},
    "no_stab": {"stab": False},
    "no_lzw_coalesce": {"lzw": False},
    "no_dither": {"dither": "none"},
    "fs_dither": {"dither": "fs"},
    "no_rdo_keep": {"rdo_keep": False},
    "no_despeckle": {"despeckle": False},
}
BASE = {"stab": True, "lzw": True, "dither": "bayer", "rdo_keep": True, "despeckle": True}
OUT = "ablation.jsonl"

clips = sorted(glob.glob(os.path.join(R.CLIP_DIR, "*.webp")), key=os.path.getsize)[::2]
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        r = json.loads(l); done.add((r["clip"], r["variant"], r["q"]))
for c in clips:
    frames, durs = R.load(c)
    name = os.path.basename(c)
    for v, fl in VARIANTS.items():
        for q in (45, 75):
            if (name, v, q) in done:
                continue
            A.FLAGS.clear(); A.FLAGS.update(BASE); A.FLAGS.update(fl)
            b, ms = A.encode_st_gif(frames, durs, quality=q)
            r = {"clip": name, "variant": v, "q": q, "bytes": len(b), "ms": ms}
            r.update(R.evaluate(b, frames, durs))
            open(OUT, "a").write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"{name[:30]:30s} {v:16s} q{q} {len(b)/1024:9.1f}KB psnr {r['psnr']:.2f} ssim {r['ssim']:.4f} flk {r['flicker']:.3f} tde {r['tde']:.3f}", flush=True)
