"""Bilingual (ko/en) figures for the GitHub and paper reports."""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mt
from matplotlib import font_manager
import stats as S

for f in font_manager.findSystemFonts():
    if "NotoSansCJK-Regular" in f or "NotoSansCJK-Bold" in f:
        font_manager.fontManager.addfont(f)
plt.rcParams.update({
    "font.family": ["Noto Sans CJK JP", "DejaVu Sans"], "axes.unicode_minus": False,
    "axes.edgecolor": "#c9c8c2", "axes.labelcolor": "#52514e", "xtick.color": "#52514e", "ytick.color": "#52514e",
    "axes.grid": True, "grid.color": "#ecebe7", "grid.linewidth": 0.8, "figure.facecolor": "#fcfcfb",
    "axes.facecolor": "#fcfcfb", "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True,
})
COL = {"st_gif": "#2a78d6", "gifski": "#eb6834", "gifsicle_lossy_sierra2_4a": "#1baf7a", "ffmpeg_sierra2_4a": "#8a8985"}
MK = {"st_gif": "o", "gifski": "s", "gifsicle_lossy_sierra2_4a": "^", "ffmpeg_sierra2_4a": "D"}
LAB = {
    "ko": {"st_gif": "ST-GIF v3 (Q15–100)", "gifski": "gifski 1.34 (Q30–100)",
           "gifsicle_lossy_sierra2_4a": "FFmpeg + gifsicle -O3 --lossy (20–200)", "ffmpeg_sierra2_4a": "FFmpeg 2-pass (sierra2_4a)",
           "size": "GIF 용량 (로그)", "better": "← ST-GIF가 더 작음 (유리)", "worse": "ST-GIF가 더 큼 (불리) →",
           "median": "중앙값", "bd_title": "gifski 대비 BD-rate (클립별)", "nodata": "겹침 없음"},
    "en": {"st_gif": "ST-GIF v3 (Q15–100)", "gifski": "gifski 1.34 (Q30–100)",
           "gifsicle_lossy_sierra2_4a": "FFmpeg + gifsicle -O3 --lossy (20–200)", "ffmpeg_sierra2_4a": "FFmpeg 2-pass (sierra2_4a)",
           "size": "GIF size (log)", "better": "← ST-GIF smaller (better)", "worse": "ST-GIF larger (worse) →",
           "median": "median", "bd_title": "BD-rate vs gifski (per clip)", "nodata": "no overlap"},
}
MNAME = {"psnr": "PSNR (dB)", "ssim": "SSIM", "vmaf": "VMAF v0.6.1", "vmaf_neg": "VMAF NEG"}


def _fmt_kb(ax):
    ax.set_xscale("log")
    ax.xaxis.set_major_locator(mt.LogLocator(base=10, subs=(1, 2, 5)))
    ax.xaxis.set_minor_formatter(mt.NullFormatter())
    ax.xaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: (f"{v/1000:g}M" if v >= 1000 else f"{v:g}K")))


def _rd(ax, by, c, metric, L, encs):
    for enc in encs:
        pts = sorted([p for p in by[c][enc] if metric in p], key=lambda r: r["bytes"])
        if pts:
            ax.plot([p["bytes"] / 1024 for p in pts], [p[metric] for p in pts], color=COL[enc], lw=2, marker=MK[enc],
                    ms=6, mec="#fcfcfb", mew=1.2, label=L[enc])
    ff = by[c]["ffmpeg_sierra2_4a"][0]
    if metric in ff:
        ax.plot(ff["bytes"] / 1024, ff[metric], MK["ffmpeg_sierra2_4a"], color=COL["ffmpeg_sierra2_4a"], ms=8, mec="#fcfcfb",
                mew=1.2, label=L["ffmpeg_sierra2_4a"])
    _fmt_kb(ax)


def rd_grid(by, clips, cid, metric, lang, path):
    L = LAB[lang]
    encs = ["gifsicle_lossy_sierra2_4a", "gifski", "st_gif"] if metric in ("psnr", "ssim") else ["gifski", "st_gif"]
    fig, axes = plt.subplots(4, 5, figsize=(22, 16.5))
    for ax, c in zip(axes.flat, clips):
        _rd(ax, by, c, metric, L, encs)
        m = by[c]["st_gif"][0]
        ax.set_title(f"{cid[c]}  {m['W']}×{m['H']}, {m['T']}f", fontsize=12, color="#0b0b0b", loc="left")
        ax.tick_params(labelsize=9)
    for ax in axes[-1]:
        ax.set_xlabel(L["size"], fontsize=10)
    for ax in axes[:, 0]:
        ax.set_ylabel(MNAME[metric] + " ↑", fontsize=10)
    h, l = axes.flat[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=4, frameon=False, fontsize=13, bbox_to_anchor=(0.5, 0.995))
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(path, dpi=110); plt.close(fig)


def bd_bars(bd, clips, cid, lang, path, metrics=("psnr", "ssim", "vmaf", "vmaf_neg")):
    L = LAB[lang]
    fig, axes = plt.subplots(1, len(metrics), figsize=(5.2 * len(metrics), 8), sharey=True)
    ids = [cid[c] for c in clips][::-1]
    allv = [bd[c][m] for c in clips for m in metrics if bd[c][m] is not None]
    lo, hi = min(allv + [0]) - 14, max(allv + [0]) + 14
    for ax, m in zip(axes, metrics):
        vals = [bd[c][m] for c in clips][::-1]
        ys = [i for i, v in enumerate(vals) if v is not None]; vs = [v for v in vals if v is not None]
        ax.barh(ys, vs, color="#2a78d6", height=0.62, edgecolor="#fcfcfb", linewidth=2)
        for i, v in enumerate(vals):
            if v is None:
                ax.text(0.5, i, " " + L["nodata"], va="center", fontsize=8, color="#8a8985")
            else:
                ax.text(v + (1.2 if v >= 0 else -1.2), i, f"{v:+.0f}", va="center", ha="left" if v >= 0 else "right", fontsize=8.5, color="#52514e")
        ax.axvline(0, color="#52514e", lw=1)
        med = float(np.median(vs))
        ax.axvline(med, color="#0b0b0b", lw=1.2, ls=(0, (4, 3)))
        ax.text(med, len(ids) - 0.25, f" {L['median']} {med:+.1f}%", fontsize=10.5, color="#0b0b0b", va="bottom")
        ax.set_title(MNAME[m], fontsize=14, loc="left", color="#0b0b0b")
        ax.set_yticks(range(len(ids))); ax.set_yticklabels(ids)
        ax.grid(axis="y", visible=False); ax.set_xlim(lo, hi)
        ax.xaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:+.0f}%"))
    fig.suptitle(L["bd_title"], x=0.01, ha="left", fontsize=16, color="#0b0b0b")
    fig.text(0.5, 0.01, f"{L['better']}          {L['worse']}", ha="center", fontsize=11, color="#52514e")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(path, dpi=110); plt.close(fig)


def representative(by, clips, cid, bd, lang, path, key="vmaf"):
    """RD curves of the best / median / worst clip (by BD-rate on `key`) for PSNR, SSIM, VMAF."""
    L = LAB[lang]
    ranked = sorted([c for c in clips if bd[c][key] is not None], key=lambda c: bd[c][key])
    pick = [ranked[0], ranked[len(ranked) // 2], ranked[-1]]
    tag = {"ko": ["최상", "중앙", "최하"], "en": ["best", "median", "worst"]}[lang]
    fig, axes = plt.subplots(3, 3, figsize=(15, 12))
    for r, c in enumerate(pick):
        for k, m in enumerate(["psnr", "ssim", "vmaf"]):
            ax = axes[r, k]
            _rd(ax, by, c, m, L, ["gifski", "st_gif"])
            if r == 0:
                ax.set_title(MNAME[m] + " ↑", fontsize=13, color="#0b0b0b", loc="left")
            if k == 0:
                mm = by[c]["st_gif"][0]
                ax.set_ylabel(f"{cid[c]} ({tag[r]})\n{mm['W']}×{mm['H']}", fontsize=11)
            if r == 2:
                ax.set_xlabel(L["size"], fontsize=10)
    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=3, frameon=False, fontsize=12, bbox_to_anchor=(0.5, 0.995))
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=120); plt.close(fig)
    return pick


def build_all(outdir):
    rows, by, clips, cid, abl, vm = S.load_all()
    bd_g = S.bd_table(by, clips, "gifski")
    picks = {}
    for lang in ("ko", "en"):
        d = os.path.join(outdir, lang); os.makedirs(d, exist_ok=True)
        for m in ("psnr", "ssim", "vmaf"):
            rd_grid(by, clips, cid, m, lang, os.path.join(d, f"rd_{m}_grid.png"))
        bd_bars(bd_g, clips, cid, lang, os.path.join(d, "bd_rate_vs_gifski.png"))
        picks[lang] = representative(by, clips, cid, bd_g, lang, os.path.join(d, "rd_representative.png"))
    return picks


if __name__ == "__main__":
    import sys
    print(build_all(sys.argv[1] if len(sys.argv) > 1 else "fig_out"))


def cambi_dots(by, clips, cid, lang, path):
    L = LAB[lang]
    M = S.matched(by, clips)
    fig, ax = plt.subplots(figsize=(11, 8))
    ids = [cid[c] for c in clips]
    y = np.arange(len(ids))[::-1]
    src = [st["cambi_source"] for _, st, g, ff in M]
    ax.scatter(src, y, s=80, facecolors="none", edgecolors="#0b0b0b", linewidths=1.5, zorder=3,
               label={"ko": "원본 WebP", "en": "Source WebP"}[lang])
    for key, idx in (("ffmpeg_sierra2_4a", 3), ("gifski", 2), ("st_gif", 1)):
        vals = [m[idx]["cambi"] for m in M]
        lab = {"st_gif": "ST-GIF Q75", "gifski": {"ko": "gifski (같은 용량대)", "en": "gifski (matched size)"}[lang],
               "ffmpeg_sierra2_4a": "FFmpeg 2-pass"}[key]
        ax.scatter(vals, y, s=70, color=COL[key] if key != "ffmpeg_sierra2_4a" else "#1baf7a", marker=MK[key],
                   edgecolors="#fcfcfb", linewidths=1.2, zorder=4, label=lab)
    ax.set_yticks(y); ax.set_yticklabels(ids)
    ax.set_xlabel({"ko": "CAMBI (낮을수록 밴딩이 적음) →", "en": "CAMBI (lower = less banding) →"}[lang])
    ax.set_title({"ko": "밴딩 지표 CAMBI — 클립별", "en": "Banding (CAMBI) per clip"}[lang], loc="left", fontsize=15, color="#0b0b0b")
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, loc="lower right", fontsize=11)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)
