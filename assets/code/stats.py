"""Shared data loading + statistics for the GitHub / paper reports."""
import os, json, collections
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.stats import wilcoxon

HERE = os.path.dirname(os.path.abspath(__file__))


def load_all():
    rows = [json.loads(l) for l in open(os.path.join(HERE, "results.jsonl"))]
    vm = {}
    vp = os.path.join(HERE, "vmaf.jsonl")
    if os.path.exists(vp):
        for l in open(vp):
            r = json.loads(l); vm[(r["clip"], r["enc"], r["param"])] = r
    cb = {}
    cp = os.path.join(HERE, "cambi.jsonl")
    if os.path.exists(cp):
        for l in open(cp):
            r = json.loads(l); cb[(r["clip"], r["enc"], r["param"])] = r
    for r in rows:
        k = (r["clip"], r["enc"], r["param"])
        v = vm.get(k)
        if v:
            r["vmaf"] = v["vmaf"]; r["vmaf_neg"] = v["vmaf_neg"]; r["vmaf_hmean"] = v["vmaf_hmean"]
            r["vmaf_bytes_match"] = v["bytes_match"]
        c = v if (v and "cambi" in v) else cb.get(k)
        if c:
            r["cambi"] = c["cambi"]; r["cambi_source"] = c["cambi_source"]; r["cambi_fr"] = c["cambi_full_reference"]
            r["cambi_bytes_match"] = c["bytes_match"]
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        by[r["clip"]][r["enc"]].append(r)
    clips = sorted(by, key=lambda c: by[c]["st_gif"][0]["src_bytes"])
    cid = {c: f"C{i+1:02d}" for i, c in enumerate(clips)}
    abl = []
    ap = os.path.join(HERE, "ablation.jsonl")
    if os.path.exists(ap):
        abl = [json.loads(l) for l in open(ap)]
    return rows, by, clips, cid, abl, vm


def _curve(pts, metric):
    pts = sorted([p for p in pts if metric in p], key=lambda r: r[metric])
    q = np.array([p[metric] for p in pts]); R = np.log(np.array([p["bytes"] for p in pts], float))
    if len(q) == 0:
        return q, R
    keep = np.concatenate([[True], np.diff(q) > 1e-6])
    return q[keep], R[keep]


def bd_rate(anchor, test, metric):
    """% rate difference of `test` vs `anchor` at equal quality over the overlapping quality range (negative = test smaller)."""
    qa, ra = _curve(anchor, metric); qb, rb = _curve(test, metric)
    if len(qa) < 2 or len(qb) < 2:
        return None
    lo, hi = max(qa.min(), qb.min()), min(qa.max(), qb.max())
    span_min = {"psnr": 0.2, "ssim": 0.002, "vmaf": 0.5, "vmaf_neg": 0.5}[metric]
    if hi - lo < span_min:
        return None
    fa, fb = PchipInterpolator(qa, ra), PchipInterpolator(qb, rb)
    x = np.linspace(lo, hi, 200)
    return float((np.exp(np.trapezoid(fb(x) - fa(x), x) / (hi - lo)) - 1) * 100)


def overlap(anchor, test, metric):
    qa, _ = _curve(anchor, metric); qb, _ = _curve(test, metric)
    return max(qa.min(), qb.min()), min(qa.max(), qb.max())


METRICS = ["psnr", "ssim", "vmaf", "vmaf_neg"]


def bd_table(by, clips, anchor_enc, metrics=METRICS):
    out = {}
    for c in clips:
        out[c] = {m: bd_rate(by[c][anchor_enc], by[c]["st_gif"], m) for m in metrics}
    return out


def summarize(vals):
    v = np.array([x for x in vals if x is not None], float)
    if len(v) == 0:
        return None
    p = wilcoxon(v).pvalue if len(v) >= 6 and np.any(v != 0) else float("nan")
    # bootstrap 95% CI of the median
    rng = np.random.default_rng(0)
    bs = np.median(rng.choice(v, size=(5000, len(v)), replace=True), axis=1)
    return {"n": len(v), "median": float(np.median(v)), "mean": float(np.mean(v)), "wins": int(np.sum(v < 0)),
            "ci_lo": float(np.percentile(bs, 2.5)), "ci_hi": float(np.percentile(bs, 97.5)), "p_wilcoxon": float(p),
            "min": float(v.min()), "max": float(v.max())}


def pick(by, c, enc, p):
    return [r for r in by[c][enc] if r["param"] == p][0]


def matched(by, clips, q=75):
    """ST-GIF at quality q vs the gifski setting closest in bytes (log)."""
    res = []
    for c in clips:
        st = pick(by, c, "st_gif", q)
        g = min(by[c]["gifski"], key=lambda r: abs(np.log(r["bytes"] / st["bytes"])))
        ff = by[c]["ffmpeg_sierra2_4a"][0]
        res.append((c, st, g, ff))
    return res


ABL_VARIANTS = ["full", "no_stab", "no_lzw_coalesce", "no_dither", "fs_dither", "no_rdo_keep", "no_despeckle"]


def ablation_table(abl, q):
    clips = sorted({a["clip"] for a in abl})
    full = [c for c in clips if all(any(a["clip"] == c and a["variant"] == v and a["q"] == q for a in abl) for v in ABL_VARIANTS)]
    out = {}
    for v in ABL_VARIANTS[1:]:
        d = []
        for c in full:
            b = [a for a in abl if a["clip"] == c and a["variant"] == "full" and a["q"] == q][0]
            x = [a for a in abl if a["clip"] == c and a["variant"] == v and a["q"] == q][0]
            d.append([x["bytes"] / b["bytes"] - 1, x["psnr"] - b["psnr"], x["ssim"] - b["ssim"], x["flicker"] - b["flicker"], x["tde"] - b["tde"]])
        out[v] = np.median(np.array(d), axis=0) if d else None
    return out, len(full)


def ablation_equal_size(by, abl, metrics=("psnr", "ssim", "tde", "flicker")):
    """For each ablation point, quality minus the full ST-GIF RD curve (PCHIP on log-bytes) at the same size.
    Negative psnr/ssim (or positive tde/flicker) => removing the component makes RD efficiency worse."""
    out = {}
    for v in ABL_VARIANTS[1:]:
        res = {m: [] for m in metrics}; outside = 0; n = 0
        for a in abl:
            if a["variant"] != v:
                continue
            n += 1
            pts = sorted(by[a["clip"]]["st_gif"], key=lambda r: r["bytes"])
            x = np.log([p["bytes"] for p in pts]); lb = np.log(a["bytes"])
            if lb < x.min() or lb > x.max():
                outside += 1; continue
            for m in metrics:
                y = np.array([p[m] for p in pts])
                res[m].append(a[m] - float(PchipInterpolator(x, y)(lb)))
        out[v] = {"n": n, "outside": outside, **{m: float(np.median(res[m])) if res[m] else None for m in metrics},
                  "worse_count": int(sum(1 for d in res["psnr"] if d < -1e-9)), "in_range": n - outside}
        out[v]["fixed_q"] = {}
    return out
