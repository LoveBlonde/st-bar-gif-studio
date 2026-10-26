import json, sys, numpy as np, collections
from scipy.interpolate import PchipInterpolator

rows = [json.loads(l) for l in open("results.jsonl")]
rows = [r for r in rows if "error" not in r]
by = collections.defaultdict(lambda: collections.defaultdict(list))
for r in rows:
    by[r["clip"]][r["enc"]].append(r)

CURVES = {
    "st_gif": "st_gif",
    "gifski": "gifski",
    "gifsicle_lossy": "gifsicle_lossy_sierra2_4a",
    "gifsicle_lossy_bayer": "gifsicle_lossy_bayer",
}


def curve(pts, metric):
    pts = sorted(pts, key=lambda r: r[metric])
    q = np.array([p[metric] for p in pts]); R = np.log(np.array([p["bytes"] for p in pts], float))
    # keep monotone-in-quality points only (remove duplicates)
    keep = np.concatenate([[True], np.diff(q) > 1e-6])
    return q[keep], R[keep]


def bd_rate(a, b, metric="psnr"):
    """Average % bitrate difference of curve b relative to a over overlapping quality interval (negative = b smaller)."""
    if len(a) < 2 or len(b) < 2:
        return None
    qa, ra = curve(a, metric); qb, rb = curve(b, metric)
    if len(a) < 2 or len(b) < 2 or len(qa) < 2 or len(qb) < 2:
        return None
    lo, hi = max(qa.min(), qb.min()), min(qa.max(), qb.max())
    if hi - lo < (0.2 if metric == "psnr" else 0.002):
        return None
    fa, fb = PchipInterpolator(qa, ra), PchipInterpolator(qb, rb)
    x = np.linspace(lo, hi, 200)
    d = np.trapezoid(fb(x) - fa(x), x) / (hi - lo)
    return (np.exp(d) - 1) * 100, lo, hi


def dominance(a, b, metric):
    """Fraction of b's points that are strictly dominated (bigger AND worse) by some point of a."""
    n = 0
    for pb in b:
        if any(pa["bytes"] <= pb["bytes"] and pa[metric] >= pb[metric] for pa in a):
            n += 1
    return n / len(b)


if __name__ == "__main__":
    out = {}
    print(f"{'clip':40s} {'BD(psnr) vs gifski':>20s} {'BD(ssim) vs gifski':>20s} {'BD(psnr) vs gsLossy':>20s} {'dom psnr':>9s} {'dom ssim':>9s}")
    for clip, e in by.items():
        st = e["st_gif"]
        if len(st) < 7 or len(e.get("gifski", [])) < 5:
            continue
        res = {}
        for name, key in CURVES.items():
            if name == "st_gif" or key not in e:
                continue
            res[name] = {
                "bd_psnr": bd_rate(e[key], st, "psnr"),
                "bd_ssim": bd_rate(e[key], st, "ssim"),
                "dom_st_over_psnr": dominance(st, e[key], "psnr"),
                "dom_st_over_ssim": dominance(st, e[key], "ssim"),
                "dom_it_over_st_psnr": dominance(e[key], st, "psnr"),
                "dom_it_over_st_ssim": dominance(e[key], st, "ssim"),
            }
        out[clip] = res
        f = lambda v: "n/a (no overlap)" if v is None else f"{v[0]:+.1f}%"
        g = res.get("gifski", {}); l = res.get("gifsicle_lossy", {})
        print(f"{clip[:40]:40s} {f(g.get('bd_psnr')):>20s} {f(g.get('bd_ssim')):>20s} {f(l.get('bd_psnr')):>20s} "
              f"{g.get('dom_st_over_psnr',0):9.2f} {g.get('dom_st_over_ssim',0):9.2f}")
    json.dump(out, open("bd.json", "w"), ensure_ascii=False, indent=1, default=float)
