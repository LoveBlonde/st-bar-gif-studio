"""
Builds the four deliverables from the measured data:
  github/BENCHMARK.ko.md, github/BENCHMARK.en.md   (repository benchmark page)
  paper/experiments.ko.md, paper/experiments.en.md (paper experiment-section draft)
Every number in the text is computed here from results.jsonl / vmaf.jsonl / cambi.jsonl / ablation.jsonl.
"""
import os, sys, json, shutil, csv
import numpy as np
import stats as S
import figures as F

OUT = sys.argv[1] if len(sys.argv) > 1 else "deliver"
rows, by, clips, cid, abl, vm = S.load_all()
NC = len(clips)

# ------------------------------------------------------------------ numbers
BD = {anchor: {c: {m: S.bd_rate(by[c][anchor], by[c]["st_gif"], m) for m in ("psnr", "ssim", "vmaf", "vmaf_neg")}
               for c in clips} for anchor in ("gifski", "gifsicle_lossy_sierra2_4a")}
SUM = {a: {m: S.summarize([BD[a][c][m] for c in clips]) for m in ("psnr", "ssim", "vmaf", "vmaf_neg")} for a in BD}
M = S.matched(by, clips, 75)
med = lambda a: float(np.median(a))


def mdiff(k):
    return med([st[k] - g[k] for _, st, g, _ in M])


def mval(k, i):
    return med([m[i][k] for m in M])


def better(k, higher=True):
    return sum((st[k] > g[k]) if higher else (st[k] < g[k]) for _, st, g, _ in M)


MATCH = {
    "ratio": med([st["bytes"] / g["bytes"] for _, st, g, _ in M]),
    "ff_ratio": med([st["bytes"] / ff["bytes"] for _, st, g, ff in M]),
    "ff_dpsnr": med([st["psnr"] - ff["psnr"] for _, st, g, ff in M]),
}
for k in ("psnr", "ssim", "vmaf", "vmaf_neg", "cambi", "flicker", "tde", "ms"):
    MATCH[k] = (mval(k, 1), mval(k, 2), mval(k, 3), mdiff(k))
MATCH["cambi_src"] = med([st["cambi_source"] for _, st, _, _ in M])
WIN = {k: better(k, k in ("psnr", "ssim", "vmaf", "vmaf_neg")) for k in ("psnr", "ssim", "vmaf", "vmaf_neg", "cambi", "flicker", "tde")}
CEIL = {e: {m: med([S.pick(by, c, e, 100)[m] for c in clips]) for m in ("psnr", "vmaf")} for e in ("st_gif", "gifski")}
GSL = {L: med([1 - S.pick(by, c, "gifsicle_lossy_sierra2_4a", L)["bytes"] / by[c]["ffmpeg_sierra2_4a"][0]["bytes"] for c in clips]) for L in (20, 200)}
AEQ = S.ablation_equal_size(by, abl)
AQ = {q: S.ablation_table(abl, q) for q in (45, 75)}
NABL = AQ[75][1]
T_RANGE = (min(by[c]["st_gif"][0]["T"] for c in clips), max(by[c]["st_gif"][0]["T"] for c in clips))
RES = sorted({(by[c]["st_gif"][0]["W"], by[c]["st_gif"][0]["H"]) for c in clips}, key=lambda x: x[0] * x[1])
SRC_MB = (min(by[c]["st_gif"][0]["src_bytes"] for c in clips) / 1e6, max(by[c]["st_gif"][0]["src_bytes"] for c in clips) / 1e6)
DITHER_OFFS = {}
from st_studio.st_gif_codec import BAYER_4X4, map_quality_to_st_gif_params
for q in (45, 60, 75, 90, 100):
    s = map_quality_to_st_gif_params(q, 1.5)["dither_str"]
    o = (BAYER_4X4 * s).astype(np.int16)
    DITHER_OFFS[q] = (s, int((o != 0).sum()), int(o.min()), int(o.max()))


_fa = {(a["clip"], a["q"]): a for a in abl if a["variant"] == "full"}
_nd = [(a, _fa[(a["clip"], a["q"])]) for a in abl if a["variant"] == "no_dither"]
DOFF = {q: {"identical": sum(1 for a, f in _nd if a["q"] == q and a["bytes"] == f["bytes"]),
            "n": sum(1 for a, f in _nd if a["q"] == q),
            "max_rel_bytes": max(abs(a["bytes"] / f["bytes"] - 1) for a, f in _nd if a["q"] == q) * 100,
            "max_dpsnr": max(abs(a["psnr"] - f["psnr"]) for a, f in _nd if a["q"] == q)} for q in (45, 75)}


def pct(x, d=1):
    return f"{x:+.{d}f}%"


def ci(s):
    return f"[{s['ci_lo']:+.1f}%, {s['ci_hi']:+.1f}%]"


def pv(p):
    return "< 0.001" if p < 0.001 else f"{p:.2f}"


VNAME = {
    "ko": {"no_stab": "① 시공간 안정화", "no_lzw_coalesce": "④ LZW 런 병합", "no_dither": "③ Bayer 디더 (끔)",
           "fs_dither": "③ Bayer → Floyd–Steinberg 교체", "no_rdo_keep": "⑤ 허용오차 유지 판정", "no_despeckle": "⑤ 스페클·고립점 제거"},
    "en": {"no_stab": "① Spatio-temporal stabilization", "no_lzw_coalesce": "④ LZW run coalescing", "no_dither": "③ Bayer dither (off)",
           "fs_dither": "③ Bayer → Floyd–Steinberg", "no_rdo_keep": "⑤ Tolerance-based keep decision", "no_despeckle": "⑤ Speckle / isolated-run removal"},
}


def abl_eq_table(lang):
    h = {"ko": "| 제거·교체한 구성 요소 | ΔPSNR (dB) | ΔSSIM | ΔTDE | ΔFlicker | 효율 악화 점 |\n|---|---:|---:|---:|---:|---:|\n",
         "en": "| Component removed / replaced | ΔPSNR (dB) | ΔSSIM | ΔTDE | ΔFlicker | Points worse |\n|---|---:|---:|---:|---:|---:|\n"}[lang]
    for v in S.ABL_VARIANTS[1:]:
        a = AEQ[v]
        h += f"| {VNAME[lang][v]} | {a['psnr']:+.2f} | {a['ssim']:+.4f} | {a['tde']:+.3f} | {a['flicker']:+.3f} | {a['worse_count']}/{a['in_range']} |\n"
    return h


def abl_q_table(lang, q):
    t, n = AQ[q]
    h = {"ko": "| 구성 요소 | 용량 | ΔPSNR (dB) | ΔSSIM | ΔFlicker | ΔTDE |\n|---|---:|---:|---:|---:|---:|\n",
         "en": "| Component | Size | ΔPSNR (dB) | ΔSSIM | ΔFlicker | ΔTDE |\n|---|---:|---:|---:|---:|---:|\n"}[lang]
    for v in S.ABL_VARIANTS[1:]:
        m = t[v]
        h += f"| {VNAME[lang][v]} | {m[0]*100:+.1f}% | {m[1]:+.2f} | {m[2]:+.4f} | {m[3]:+.3f} | {m[4]:+.3f} |\n"
    return h


def clip_table(lang):
    h = {"ko": "| ID | 해상도 | 프레임 | 원본 | BD PSNR | BD SSIM | BD VMAF | BD VMAF-NEG | CAMBI ST / gifski |\n|---|---|---:|---:|---:|---:|---:|---:|---:|\n",
         "en": "| ID | Resolution | Frames | Source | BD PSNR | BD SSIM | BD VMAF | BD VMAF-NEG | CAMBI ST / gifski |\n|---|---|---:|---:|---:|---:|---:|---:|---:|\n"}[lang]
    for c, st, g, ff in M:
        m = by[c]["st_gif"][0]; b = BD["gifski"][c]
        f = lambda x: "n/a" if x is None else f"{x:+.1f}%"
        h += (f"| {cid[c]} | {m['W']}×{m['H']} | {m['T']} | {m['src_bytes']/1e6:.1f} MB | {f(b['psnr'])} | {f(b['ssim'])} | "
              f"{f(b['vmaf'])} | {f(b['vmaf_neg'])} | {st['cambi']:.2f} / {g['cambi']:.2f} |\n")
    return h


def name_table(lang):
    h = {"ko": "| ID | 원본 파일명 |\n|---|---|\n", "en": "| ID | Source file |\n|---|---|\n"}[lang]
    return h + "".join(f"| {cid[c]} | `{c}` |\n" for c in clips)


def bd_summary_table(lang):
    h = {"ko": "| 기준 인코더 | 품질 지표 | BD-rate 중앙값 | 95% CI (부트스트랩) | ST-GIF 우위 | Wilcoxon p |\n|---|---|---:|---|---:|---:|\n",
         "en": "| Anchor | Quality metric | Median BD-rate | 95% CI (bootstrap) | ST-GIF wins | Wilcoxon p |\n|---|---|---:|---|---:|---:|\n"}[lang]
    nm = {"gifski": "gifski 1.34", "gifsicle_lossy_sierra2_4a": "FFmpeg + gifsicle --lossy"}
    for a in ("gifski", "gifsicle_lossy_sierra2_4a"):
        for m in (("psnr", "ssim", "vmaf", "vmaf_neg") if a == "gifski" else ("psnr", "ssim")):
            s = SUM[a][m]
            h += f"| {nm[a]} | {F.MNAME[m]} | **{pct(s['median'])}** | {ci(s)} | {s['wins']}/{s['n']} | {pv(s['p_wilcoxon'])} |\n"
    return h


def matched_table(lang):
    lab = {"ko": ["항목", "ST-GIF Q75", "gifski (최근접 용량)", "FFmpeg 2-pass", "ST − gifski (중앙값)", "ST가 나은 클립"],
           "en": ["Metric", "ST-GIF Q75", "gifski (nearest size)", "FFmpeg 2-pass", "ST − gifski (median)", "Clips where ST is better"]}[lang]
    h = "| " + " | ".join(lab) + " |\n|---|---:|---:|---:|---:|---:|\n"
    rowsdef = [("psnr", "PSNR (dB) ↑", 2), ("ssim", "SSIM ↑", 4), ("vmaf", "VMAF ↑", 1), ("vmaf_neg", "VMAF-NEG ↑", 1),
               ("cambi", "CAMBI ↓", 3), ("flicker", "Flicker ↓", 3), ("tde", "TDE ↓", 3)]
    for k, nm, d in rowsdef:
        a, b, c, dd = MATCH[k]
        h += f"| {nm} | {a:.{d}f} | {b:.{d}f} | {c:.{d}f} | {dd:+.{d}f} | {WIN[k]}/{NC} |\n"
    a, b, c, dd = MATCH["ms"]
    h += f"| {'인코딩 시간' if lang == 'ko' else 'Encoding time'} (s) | {a/1000:.1f} | {b/1000:.1f} | {c/1000:.1f} | {dd/1000:+.1f} | — |\n"
    return h


# ------------------------------------------------------------------ figures
def build_figs(dest):
    for lang in ("ko", "en"):
        d = os.path.join(dest, lang); os.makedirs(d, exist_ok=True)
        for m in ("psnr", "ssim", "vmaf"):
            F.rd_grid(by, clips, cid, m, lang, os.path.join(d, f"rd_{m}_grid.png"))
        F.bd_bars(BD["gifski"], clips, cid, lang, os.path.join(d, "bd_rate_vs_gifski.png"))
        picks = F.representative(by, clips, cid, BD["gifski"], lang, os.path.join(d, "rd_representative.png"))
        F.cambi_dots(by, clips, cid, lang, os.path.join(d, "cambi_per_clip.png"))
        shutil.copy(f"fig/encoder_compare_{lang}.png", os.path.join(d, "encoder_compare.png"))
    return picks


os.makedirs(OUT, exist_ok=True)
gfig = os.path.join(OUT, "github", "figures"); pfig = os.path.join(OUT, "paper", "figures")
picks = build_figs(gfig)
shutil.copytree(gfig, pfig, dirs_exist_ok=True)
PICK = [cid[c] for c in picks]

# data + code
dd = os.path.join(OUT, "data"); os.makedirs(dd, exist_ok=True)
for f in ("results.jsonl", "vmaf.jsonl", "cambi.jsonl", "ablation.jsonl"):
    shutil.copy(f, dd)
with open(os.path.join(dd, "summary_per_clip.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh)
    w.writerow(["id", "clip", "W", "H", "frames", "src_bytes", "bd_psnr_vs_gifski", "bd_ssim_vs_gifski", "bd_vmaf_vs_gifski",
                "bd_vmafneg_vs_gifski", "bd_psnr_vs_gifsicle_lossy", "st75_bytes", "st75_psnr", "st75_ssim", "st75_vmaf", "st75_cambi",
                "st75_flicker", "st75_tde", "gifski_matched_q", "gifski_bytes", "gifski_psnr", "gifski_ssim", "gifski_vmaf",
                "gifski_cambi", "gifski_flicker", "gifski_tde", "ffmpeg_bytes", "ffmpeg_psnr", "ffmpeg_vmaf", "ffmpeg_cambi", "source_cambi"])
    for c, st, g, ff in M:
        m = by[c]["st_gif"][0]; b = BD["gifski"][c]
        w.writerow([cid[c], c, m["W"], m["H"], m["T"], m["src_bytes"], b["psnr"], b["ssim"], b["vmaf"], b["vmaf_neg"],
                    BD["gifsicle_lossy_sierra2_4a"][c]["psnr"], st["bytes"], st["psnr"], st["ssim"], st["vmaf"], st["cambi"],
                    st["flicker"], st["tde"], g["param"], g["bytes"], g["psnr"], g["ssim"], g["vmaf"], g["cambi"], g["flicker"], g["tde"],
                    ff["bytes"], ff["psnr"], ff["vmaf"], ff["cambi"], st["cambi_source"]])
cd = os.path.join(OUT, "code"); os.makedirs(cd, exist_ok=True)
for f in ("rd_bench.py", "vmaf_bench.py", "analyze.py", "ablation.py", "stats.py", "figures.py", "build_reports.py",
          "report_text.py", "st_studio/st_gif_ablate.py", "fig/encoder_compare.html", "fig/render.js"):
    shutil.copy(f, cd)
shutil.copy("report/code/README.md", os.path.join(cd, "README.md"))

G = SUM["gifski"]
CTX = dict(NC=NC, NABL=NABL, T0=T_RANGE[0], T1=T_RANGE[1], R0=f"{RES[0][0]}×{RES[0][1]}", R1=f"{RES[-1][0]}×{RES[-1][1]}",
           S0=SRC_MB[0], S1=SRC_MB[1], PICK=PICK)
exec(open("report_text.py", encoding="utf-8").read())
print("built", OUT)
