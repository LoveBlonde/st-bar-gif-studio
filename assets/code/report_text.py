# Executed by build_reports.py (shares its namespace). Writes the four Markdown documents.
g_ps, g_ss, g_vm, g_vn = G["psnr"], G["ssim"], G["vmaf"], G["vmaf_neg"]
gl_ps, gl_ss = SUM["gifsicle_lossy_sierra2_4a"]["psnr"], SUM["gifsicle_lossy_sierra2_4a"]["ssim"]
mv = MATCH
ff_x = 1 / mv["ff_ratio"]
A = AEQ
d75, d90, d100 = DITHER_OFFS[75], DITHER_OFFS[90], DITHER_OFFS[100]
P = CTX["PICK"]

# ============================================================== GitHub (KO)
gh_ko = f"""# ST-GIF v3 벤치마크: gifski · gifsicle · FFmpeg와의 비교

> 측정일 2026-10-26 · 실제 화면·게임 캡처 {NC}개 클립 · 지표 PSNR, SSIM, VMAF(v0.6.1 / NEG), CAMBI, Flicker, TDE
> 원자료와 재현 코드는 [`data/`](../data), [`code/`](../code)에 있습니다.

## 요약

| | 결과 |
|---|---|
| **FFmpeg 2-pass 대비** | Q75 기준 용량 중앙값 **{mv['ff_ratio']*100:.0f}%** (약 {ff_x:.1f}배 축소), 정적 영역 Flicker {mv['flicker'][2]:.2f} → **{mv['flicker'][0]:.2f}** |
| **gifsicle `--lossy` 대비** | 같은 PSNR에서 용량 **{pct(gl_ps['median'])}** ({gl_ps['wins']}/{gl_ps['n']} 클립 우위) |
| **gifski 대비 (PSNR)** | 같은 PSNR에서 용량 {pct(g_ps['median'])} ({g_ps['wins']}/{g_ps['n']} 클립 우위, 유의하지 않음) |
| **gifski 대비 (SSIM)** | 같은 SSIM에서 용량 **{pct(g_ss['median'])}** ({g_ss['wins']}/{g_ss['n']} 클립 우위) |
| **gifski 대비 (VMAF)** | 같은 VMAF에서 용량 **{pct(g_vm['median'])}** ({g_vm['wins']}/{g_vm['n']} 클립 우위) — **gifski가 우세** |
| **밴딩 (CAMBI, 같은 용량대)** | ST-GIF **{mv['cambi'][0]:.2f}** vs gifski **{mv['cambi'][1]:.3f}** (gifski가 {NC - WIN['cambi']}/{NC} 클립에서 우세) |

**한 줄 정리:** ST-GIF v3는 FFmpeg와 gifsicle보다 확실히 작고 안정적인 GIF를 만듭니다. 하지만 **gifski보다 낫다고 말할 수는 없습니다.** SSIM에서는 앞서지만 VMAF와 CAMBI에서는 뒤지고, 그 주된 원인은 현재 구현에서 디더가 사실상 동작하지 않아 생기는 밴딩입니다(아래 [알려진 문제](#알려진-문제-bayer-디더가-사실상-꺼져-있음) 참고).

![인코더 비교](figures/ko/encoder_compare.png)

## 무엇을 어떻게 측정했나

- **데이터:** 화면 캡처 도구로 녹화한 Animated WebP 95개 중 파일 크기 순위로 층화 추출한 **{NC}개**. 해상도 {CTX['R0']} ~ {CTX['R1']}, 클립당 앞 {CTX['T1']}프레임까지 사용, 원본 {CTX['S0']:.1f} ~ {CTX['S1']:.1f} MB. 클립 목록은 [부록](#부록-클립-id)에 있습니다.
- **인코더와 파라미터 sweep**

  | 인코더 | 설정 | sweep |
  |---|---|---|
  | ST-GIF v3 | `encode_st_gif`, 원본의 가변 프레임 지속시간 사용 | Q = 15, 30, 45, 60, 75, 90, 100 |
  | gifski 1.34 | PNG 프레임 입력, `--fps <평균>`, 원본 폭 | Q = 30, 50, 70, 90, 100 |
  | FFmpeg 6.1.1 | `palettegen=stats_mode=diff` + `paletteuse=dither=sierra2_4a:diff_mode=rectangle` | 단일점 |
  | gifsicle 1.94 | FFmpeg 출력에 `-O3 --lossy=N` | N = 20, 40, 80, 140, 200 |

- **지표:** 기준 영상은 원본 WebP를 디코딩한 프레임입니다.
  - PSNR: 전체 프레임 평균
  - SSIM: 약 20프레임 샘플, 2배 다운샘플
  - VMAF v0.6.1과 VMAF-NEG: libvmaf, yuv444p
  - CAMBI: libvmaf 기본 설정 (밴딩 지표, 낮을수록 좋음)
  - Flicker: 원본이 변하지 않은 픽셀에서 결과물이 프레임 간에 변한 정도
  - TDE: 원본의 프레임 간 변화와 결과물의 프레임 간 변화가 어긋난 정도. 깜빡임과 얼어붙음을 모두 벌점으로 줍니다.
- **BD-rate:** (품질, log 용량) 곡선을 PCHIP으로 보간한 뒤 겹치는 품질 구간에서 평균 용량 차이를 계산합니다. 음수면 ST-GIF가 유리합니다.
- **시간축 정렬:** FFmpeg와 gifski는 고정 fps로 입력하므로 균등 시간축으로, ST-GIF는 원본 시간축으로 정렬했습니다. 둘을 섞으면 기준선 PSNR이 실제보다 크게 낮게 나옵니다(예: C01의 FFmpeg는 35.4 dB, 올바른 값은 53.5 dB).

## 결과

### gifski 대비 BD-rate

{bd_summary_table('ko')}
![BD-rate](figures/ko/bd_rate_vs_gifski.png)

대표 클립 3개의 RD 곡선입니다. VMAF BD-rate 기준으로 최상 {P[0]}, 중앙 {P[1]}, 최하 {P[2]}를 골랐습니다.

![대표 RD 곡선](figures/ko/rd_representative.png)

전체 {NC}개 클립의 RD 곡선은 [PSNR](figures/ko/rd_psnr_grid.png) · [SSIM](figures/ko/rd_ssim_grid.png) · [VMAF](figures/ko/rd_vmaf_grid.png)에서 볼 수 있습니다.

### 같은 용량대 비교 (ST-GIF Q75 vs 용량이 가장 가까운 gifski 설정)

용량 비 중앙값(ST / gifski)은 **{mv['ratio']:.2f}**입니다.

{matched_table('ko')}
### 밴딩

![CAMBI](figures/ko/cambi_per_clip.png)

원본 WebP 자체의 CAMBI 중앙값은 {mv['cambi_src']:.2f}입니다. 디더를 쓰는 gifski({mv['cambi'][1]:.3f})는 모든 클립에서, FFmpeg({mv['cambi'][2]:.2f})는 20개 중 17개 클립에서 원본에 있던 밴딩까지 가려줍니다. ST-GIF({mv['cambi'][0]:.2f})는 절반 정도만 줄입니다.

### 화질 상한

Q=100에서의 중앙값입니다.

| | PSNR | VMAF |
|---|---:|---:|
| ST-GIF | {CEIL['st_gif']['psnr']:.1f} dB | {CEIL['st_gif']['vmaf']:.1f} |
| gifski | {CEIL['gifski']['psnr']:.1f} dB | {CEIL['gifski']['vmaf']:.1f} |

ST-GIF는 허용오차 안의 변화를 의도적으로 버리기 때문에 품질을 높여도 원본에 끝까지 가까워지지 않습니다.

## 구성 요소별 기여 (어블레이션)

{CTX['NABL']}개 클립 × Q45·Q75에서 구성 요소를 하나씩 끄거나 바꾼 뒤, **전체 파이프라인의 RD 곡선과 같은 용량에서** 비교했습니다. 음수 ΔPSNR·ΔSSIM, 양수 ΔTDE는 그 구성 요소가 효율에 기여한다는 뜻입니다.

{abl_eq_table('ko')}
- 가장 큰 기여는 **허용오차 유지 판정**입니다. Q45에서 이걸 끄면 용량이 {AQ[45][0]['no_rdo_keep'][0]*100:+.0f}% 늘어납니다.
- 스페클 제거는 작지만 일관되게 기여합니다({A['no_despeckle']['worse_count']}/{A['no_despeckle']['in_range']}). LZW 런 병합({A['no_lzw_coalesce']['worse_count']}/{A['no_lzw_coalesce']['in_range']})과 시공간 안정화({A['no_stab']['worse_count']}/{A['no_stab']['in_range']})는 기여가 작고 클립에 따라 다릅니다.
- 디더를 Floyd–Steinberg로 바꾸면 모든 지표가 나빠집니다. 위치 고정 양자화를 쓰는 선택 자체는 맞습니다.

### 알려진 문제: Bayer 디더가 사실상 꺼져 있음

`quantize_frame_with_locked_bayer`는 `BAYER_4X4`(−7 ~ +8)에 디더 강도를 곱한 뒤 `int16`으로 자릅니다.
- 디더 강도는 Q75에서 {d75[0]:.2f}, Q90에서 {d90[0]:.3f}, Q100에서 {d100[0]:.2f}입니다.
- 이때 0이 아닌 오프셋은 16칸 중 Q75에서 **{d75[1]}칸**({d75[2]}~{d75[3]}), Q90에서 {d90[1]}칸, Q100에서 {d100[1]}칸뿐입니다.
- 3D LUT가 RGB를 4단위로 묶기 때문에 ±1~2 오프셋으로는 선택되는 팔레트 색이 거의 바뀌지 않습니다.

그래서 어블레이션에서 디더를 끈 결과는 Q45에서 **바이트 단위까지 같았고**({DOFF[45]['identical']}/{DOFF[45]['n']}, 원래 디더 강도가 0), Q75에서도 용량 차가 최대 {DOFF[75]['max_rel_bytes']:.2f}%, PSNR 차가 최대 {DOFF[75]['max_dpsnr']:.3f} dB로 사실상 같았습니다. VMAF와 CAMBI 열세의 가장 유력한 원인이며, 다음 버전에서 고쳐야 할 1순위입니다.

## 기존 README 수치와의 차이

README의 "FFmpeg 대비 3~29배 축소"는 **가장 작은 4개 파일**(크기 순위 0, 1, 2, 8)에서 측정한 값입니다. 크기 전 구간에서 고른 {NC}개 클립의 중앙값은 **약 {ff_x:.1f}배**입니다. README 표를 인용할 때는 표본이 다르다는 점을 함께 적는 것을 권합니다.

## 한계

- 기준 영상이 손실 압축된 WebP라서, 원본의 압축 잡음을 지우는 처리는 PSNR에서 불리하게 측정됩니다.
- 표본은 한 사람의 캡처 폴더에서 뽑은 {NC}개 클립이고, 각 설정은 1회씩만 측정했습니다.
- 인코딩 시간은 2 vCPU 클라우드 컨테이너에서 측정했고 병렬 실행 구간이 섞여 있습니다.
- VMAF와 CAMBI는 ST-GIF, gifski, FFmpeg에 대해서만 측정했습니다. gifsicle은 PSNR과 SSIM에서 이미 크게 뒤져서 제외했습니다.

## 재현 방법

[`code/README.md`](../code/README.md)를 참고하세요. 필요한 도구는 `ffmpeg`, `gifsicle` 1.92 이상, `gifski`, Netflix libvmaf의 `vmaf` CLI입니다.

```bash
python rd_bench.py 0 2 & python rd_bench.py 1 2      # 인코딩 + PSNR/SSIM/Flicker/TDE
python vmaf_bench.py 0 2 & python vmaf_bench.py 1 2  # VMAF + CAMBI
python ablation.py                                   # 어블레이션
python build_reports.py out                          # 그림·표·문서 생성
```

## 부록: 클립 ID

{name_table('ko')}
## 부록: 클립별 수치 (gifski 대비 BD-rate)

{clip_table('ko')}"""

# ============================================================== GitHub (EN)
gh_en = f"""# ST-GIF v3 Benchmark vs gifski · gifsicle · FFmpeg

> Measured 2026-10-26 · {NC} real screen/game capture clips · PSNR, SSIM, VMAF (v0.6.1 / NEG), CAMBI, Flicker, TDE
> Raw data and reproduction code: [`data/`](../data), [`code/`](../code).

## Summary

| | Result |
|---|---|
| **vs FFmpeg 2-pass** | At Q75, median size **{mv['ff_ratio']*100:.0f}%** of FFmpeg (≈{ff_x:.1f}× smaller); static-region flicker {mv['flicker'][2]:.2f} → **{mv['flicker'][0]:.2f}** |
| **vs gifsicle `--lossy`** | **{pct(gl_ps['median'])}** bytes at equal PSNR (wins {gl_ps['wins']}/{gl_ps['n']} clips) |
| **vs gifski (PSNR)** | {pct(g_ps['median'])} bytes at equal PSNR (wins {g_ps['wins']}/{g_ps['n']}, not significant) |
| **vs gifski (SSIM)** | **{pct(g_ss['median'])}** bytes at equal SSIM (wins {g_ss['wins']}/{g_ss['n']}) |
| **vs gifski (VMAF)** | **{pct(g_vm['median'])}** bytes at equal VMAF (wins {g_vm['wins']}/{g_vm['n']}) — **gifski is better** |
| **Banding (CAMBI, matched size)** | ST-GIF **{mv['cambi'][0]:.2f}** vs gifski **{mv['cambi'][1]:.3f}** (gifski better on {NC - WIN['cambi']}/{NC} clips) |

**Bottom line:** ST-GIF v3 produces clearly smaller and more stable GIFs than FFmpeg and gifsicle, but it **does not beat gifski**. It wins on SSIM and loses on VMAF and CAMBI, mainly because of banding: the dither is effectively disabled in the current implementation (see [Known issue](#known-issue-the-bayer-dither-is-effectively-off)).

![Encoder comparison](figures/en/encoder_compare.png)

## What was measured

- **Data:** {NC} clips stratified by file-size rank from 95 screen-capture Animated WebP recordings. Resolution {CTX['R0']} – {CTX['R1']}, first {CTX['T1']} frames per clip, source {CTX['S0']:.1f} – {CTX['S1']:.1f} MB. See the [clip list](#appendix-clip-ids).
- **Encoders and parameter sweeps**

  | Encoder | Settings | Sweep |
  |---|---|---|
  | ST-GIF v3 | `encode_st_gif`, source variable frame durations | Q = 15, 30, 45, 60, 75, 90, 100 |
  | gifski 1.34 | PNG frames, `--fps <mean>`, source width | Q = 30, 50, 70, 90, 100 |
  | FFmpeg 6.1.1 | `palettegen=stats_mode=diff` + `paletteuse=dither=sierra2_4a:diff_mode=rectangle` | single point |
  | gifsicle 1.94 | `-O3 --lossy=N` on FFmpeg output | N = 20, 40, 80, 140, 200 |

- **Metrics:** the reference is the decoded source WebP.
  - PSNR: mean over all frames
  - SSIM: about 20 sampled frames, 2× subsampled
  - VMAF v0.6.1 and VMAF-NEG: libvmaf, yuv444p
  - CAMBI: libvmaf defaults (banding, lower is better)
  - Flicker: frame-to-frame change of the output on pixels that are static in the source
  - TDE: mismatch between the output's and the source's frame-to-frame change. Penalizes both flicker and frozen motion.
- **BD-rate:** PCHIP interpolation of (quality, log bytes), mean rate difference over the overlapping quality range. Negative favors ST-GIF.
- **Temporal alignment:** FFmpeg and gifski receive a constant frame rate, so they are aligned on a uniform timeline; ST-GIF is aligned on the source's variable timeline. Mixing the two understates baseline PSNR badly (e.g. FFmpeg on C01: 35.4 dB vs. the correct 53.5 dB).

## Results

### BD-rate vs gifski

{bd_summary_table('en')}
![BD-rate](figures/en/bd_rate_vs_gifski.png)

RD curves of three representative clips, chosen by VMAF BD-rate: best {P[0]}, median {P[1]}, worst {P[2]}.

![Representative RD curves](figures/en/rd_representative.png)

Full {NC}-clip grids: [PSNR](figures/en/rd_psnr_grid.png) · [SSIM](figures/en/rd_ssim_grid.png) · [VMAF](figures/en/rd_vmaf_grid.png).

### Matched-size comparison (ST-GIF Q75 vs the gifski setting closest in size)

Median size ratio (ST / gifski) is **{mv['ratio']:.2f}**.

{matched_table('en')}
### Banding

![CAMBI](figures/en/cambi_per_clip.png)

The source WebP itself has a median CAMBI of {mv['cambi_src']:.2f}. Dithering encoders mask this banding: gifski reaches {mv['cambi'][1]:.3f} and stays below the source on every clip, and FFmpeg reaches {mv['cambi'][2]:.2f} and stays below it on 17 of 20 clips. ST-GIF only roughly halves it ({mv['cambi'][0]:.2f}).

### Fidelity ceiling

Medians at Q=100:

| | PSNR | VMAF |
|---|---:|---:|
| ST-GIF | {CEIL['st_gif']['psnr']:.1f} dB | {CEIL['st_gif']['vmaf']:.1f} |
| gifski | {CEIL['gifski']['psnr']:.1f} dB | {CEIL['gifski']['vmaf']:.1f} |

ST-GIF deliberately discards changes inside its tolerance, so even at the highest quality it never fully converges to the source.

## Component contributions (ablation)

Each component was removed or replaced on {CTX['NABL']} clips at Q45 and Q75, and the result was compared **against the full pipeline's RD curve at the same size**. Negative ΔPSNR/ΔSSIM or positive ΔTDE means the component helps.

{abl_eq_table('en')}
- The **tolerance-based keep decision** contributes most. Removing it grows files by {AQ[45][0]['no_rdo_keep'][0]*100:+.0f}% at Q45.
- Speckle removal helps a little but consistently ({A['no_despeckle']['worse_count']}/{A['no_despeckle']['in_range']}). LZW run coalescing ({A['no_lzw_coalesce']['worse_count']}/{A['no_lzw_coalesce']['in_range']}) and stabilization ({A['no_stab']['worse_count']}/{A['no_stab']['in_range']}) help less and vary by clip.
- Replacing the ordered dither with Floyd–Steinberg hurts every metric, so the choice of position-locked quantization is right.

### Known issue: the Bayer dither is effectively off

`quantize_frame_with_locked_bayer` multiplies `BAYER_4X4` (−7 … +8) by the dither strength and truncates the result to `int16`.
- The dither strength is {d75[0]:.2f} at Q75, {d90[0]:.3f} at Q90 and {d100[0]:.2f} at Q100.
- That leaves only **{d75[1]}/16** non-zero offsets at Q75 ({d75[2]}…{d75[3]}), {d90[1]}/16 at Q90 and {d100[1]}/16 at Q100.
- The 3D LUT bins RGB in steps of 4, so a ±1–2 offset almost never changes the selected palette entry.

As a result, turning the dither off gave **byte-identical files** at Q45 ({DOFF[45]['identical']}/{DOFF[45]['n']}; the strength is already 0 there) and practically identical ones at Q75 (at most {DOFF[75]['max_rel_bytes']:.2f}% size and {DOFF[75]['max_dpsnr']:.3f} dB PSNR difference). This is the most likely cause of the VMAF and CAMBI deficit and the first thing to fix.

## Difference from the numbers in the main README

The README's "3–29× smaller than FFmpeg" was measured on the **four smallest files** (size ranks 0, 1, 2, 8). Over {NC} clips spanning the whole size range, the median is **≈{ff_x:.1f}×**. Please quote the README table together with its sample.

## Limitations

- The reference is a lossy WebP, so removing its compression noise is penalized by PSNR.
- {NC} clips from one person's capture folder; each setting was measured once.
- Encoding times come from a 2-vCPU cloud container and include periods of parallel execution.
- VMAF and CAMBI were measured for ST-GIF, gifski and FFmpeg only. gifsicle was already far behind on PSNR and SSIM.

## Reproduction

See [`code/README.md`](../code/README.md). Requires `ffmpeg`, `gifsicle` ≥ 1.92, `gifski` and the Netflix libvmaf `vmaf` CLI.

```bash
python rd_bench.py 0 2 & python rd_bench.py 1 2      # encode + PSNR/SSIM/Flicker/TDE
python vmaf_bench.py 0 2 & python vmaf_bench.py 1 2  # VMAF + CAMBI
python ablation.py                                   # ablation
python build_reports.py out                          # figures, tables, documents
```

## Appendix: clip IDs

{name_table('en')}
## Appendix: per-clip BD-rate vs gifski

{clip_table('en')}"""

# ============================================================== Paper (KO)
REFS_KO = """[1] I. Yoo, X. Luo, Y. Wang, F. Yang, and P. Milanfar, "GIFnets: Differentiable GIF encoding framework," in *Proc. IEEE/CVF CVPR*, 2020, pp. 14473–14482.
[2] Y. Wang, G. Liu, Z. Zhu, X. Zhang, and Z. Qian, "VivID: A visually improved GIF encoding network design," *IEEE Trans. Circuits Syst. Video Technol.*, vol. 35, no. 6, pp. 6101–6113, 2025.
[3] Y. Wang, G. Liu, S. Li, X. Zhang, and Z. Qian, "Neural representations for animated GIFs," in *Proc. ICMR '26*, 2026, pp. 459–467.
[4] S.-W. Chiang and L.-M. Po, "Lossy LZW algorithm with adaptive threshold for palettized image compression," in *Proc. ISSPA '96*, 1996, pp. 144–147.
[5] V. Crnojević, V. Šenk, and Ž. Trpovski, "Lossy Lempel-Ziv algorithm for image compression," in *Proc. TELSIKS 2003*, 2003, pp. 522–525.
[6] F. W. Mounts, "A video encoding system with conditional picture-element replenishment," *Bell Syst. Tech. J.*, vol. 48, no. 7, 1969. (권호·쪽수 확인 필요)
[7] Z. Li, A. Aaron, I. Katsavounidis, A. Moorthy, and M. Manohara, "Toward a practical perceptual video quality metric," *Netflix Tech Blog*, 2016.
[8] P. Tandon, M. Afonso, J. Sole, and L. Krasula, "CAMBI: Contrast-aware multiscale banding index," arXiv:2102.00079, 2021.
[9] Z. Wang, A. C. Bovik, H. R. Sheikh, and E. P. Simoncelli, "Image quality assessment: From error visibility to structural similarity," *IEEE Trans. Image Process.*, vol. 13, no. 4, pp. 600–612, 2004.
[10] G. Bjøntegaard, "Calculation of average PSNR differences between RD-curves," ITU-T SG16/Q6 VCEG-M33, 2001.
[11] K. Lesiński, gifski (v1.34) 및 gifsicle `--lossy` (lossy GIF), https://gif.ski, https://kornel.ski/lossygif
[12] E. Kohler, Gifsicle 1.94, https://www.lcdf.org/gifsicle/
"""
REFS_EN = REFS_KO.replace("(권호·쪽수 확인 필요)", "(verify issue/pages)").replace("gifski (v1.34) 및 gifsicle", "gifski (v1.34) and gifsicle")

pk = f"""# 실험 (논문 초안용)

> 이 문서는 논문의 **실험 절(4장)** 초안입니다. 표와 그림 번호는 임시이고, 본문 수치는 모두 첨부 데이터에서 자동 계산했습니다.
> 맨 끝의 [저자용 메모](#저자용-메모-투고-전-확인)에 이 결과로 **주장할 수 있는 것과 없는 것**을 정리했습니다.

## 4.1 실험 설정

**데이터셋.** 실제 사용 환경을 반영하기 위해 화면·게임 녹화 도구로 만든 Animated WebP 95개에서 {NC}개를 골랐습니다. 파일 크기 순위로 층화 추출해 작은 파일에 편중되지 않게 했습니다. 해상도는 {CTX['R0']}부터 {CTX['R1']}까지이고, 각 클립은 앞 {CTX['T1']}프레임까지 썼습니다(더 짧은 클립은 전체). 원본은 가변 프레임레이트이며, 녹화 과정에서 생긴 ±1~3 수준의 센서·압축 잡음을 포함합니다. 기존 GIF 연구 [1]–[3]이 자연 영상이나 정지 이미지를 128×128 ~ 256×256으로 줄여 평가한 것과 달리, 이 실험은 원본 해상도의 화면 녹화 콘텐츠를 대상으로 합니다.

**비교 대상.** 표준 GIF89a를 출력하는 실용 인코더 세 가지와 비교했습니다.
- FFmpeg 6.1.1 2-pass: `palettegen=stats_mode=diff`, `paletteuse=dither=sierra2_4a:diff_mode=rectangle`
- FFmpeg 출력에 gifsicle 1.94 `-O3 --lossy=N`(N ∈ {{20, 40, 80, 140, 200}}) 적용 [11], [12]
- gifski 1.34, Q ∈ {{30, 50, 70, 90, 100}} [11]

ST-GIF는 Q ∈ {{15, 30, 45, 60, 75, 90, 100}}으로 측정했습니다. 신경망 기반 인코더 [1], [2]는 정지 이미지 단위로 동작하며, 이번 실험에서는 재현하지 않고 4.6절에서 비교 논의만 합니다.

**품질 지표.** 기준 영상은 원본 WebP를 디코딩한 RGB 프레임입니다.
- 화소 충실도: PSNR(전체 프레임 평균), SSIM [9](약 20프레임 샘플)
- 지각 품질: VMAF v0.6.1 [7]. 디노이즈나 샤프닝 같은 향상 처리에 점수를 주지 않는 VMAF-NEG도 함께 썼습니다.
- 밴딩: CAMBI [8]
- 시간 안정성: Flicker와 TDE(아래 정의)

정적 영역 Flicker는 원본에서 채널 최대 변화가 3 이하인 픽셀 집합 Ω_t에서 결과물의 프레임 간 절대 변화 평균으로 정의했습니다. TDE(temporal-difference error)는 다음과 같습니다.

  TDE = mean_t mean_p |(D_t(p) − D_{{t−1}}(p)) − (O_t(p) − O_{{t−1}}(p))|

여기서 D는 결과물, O는 원본입니다. Flicker는 "없던 변화가 생기는 것"만 측정하지만, TDE는 "있던 움직임이 사라지는 것"(얼어붙음)까지 벌점으로 줍니다. 정적 영역을 고정하는 방법이 Flicker에서 부당하게 유리해지는 것을 막으려고 넣었습니다.

**BD-rate.** 각 인코더의 (품질, log 용량) 점들을 단조 PCHIP으로 보간하고, 두 곡선이 겹치는 품질 구간에서 평균 용량 차이를 계산했습니다 [10]. 음수면 ST-GIF가 같은 품질을 더 작은 용량으로 달성합니다. 클립 간 통계는 중앙값, 부트스트랩 95% 신뢰구간(5,000회), Wilcoxon 부호순위 검정으로 보고합니다.

**시간축 정렬.** FFmpeg와 gifski는 평균 fps의 고정 프레임레이트로 입력받으므로 균등 시간축으로, ST-GIF는 원본 가변 시간축으로 디코딩 프레임을 대응시켰습니다. 처음 구현에서는 기준선을 원본 시간축에 맞춰 PSNR이 크게 낮게 측정되는 문제가 있었습니다(예: 한 클립에서 35.4 dB, 올바른 값은 53.5 dB). 가변 프레임레이트 소스로 GIF 인코더를 평가할 때 흔히 생길 수 있는 오류라서 명시합니다.

**구현 환경.** Intel Xeon 2.1 GHz 2 vCPU, Python 3.13, libvmaf(소스 빌드). 모든 인코더는 결정적으로 동작하며, VMAF와 CAMBI 측정용으로 다시 인코딩한 260개 결과물이 1차 측정과 바이트 단위로 일치함을 확인했습니다.

## 4.2 율-품질 비교

**표 1.** gifski와 gifsicle 대비 ST-GIF의 BD-rate (클립 {NC}개)

{bd_summary_table('ko')}
표 1의 결과는 지표에 따라 결론이 갈립니다.
- **gifsicle `--lossy` 대비:** ST-GIF가 모든 클립에서 앞섭니다(PSNR 기준 {pct(gl_ps['median'])}). gifsicle은 FFmpeg 출력 대비 용량을 중앙값 {GSL[20]*100:.0f}%(`--lossy=20`) ~ {GSL[200]*100:.0f}%(`--lossy=200`) 줄이지만, 입력 GIF에 이미 박힌 오차 확산 디더 패턴을 그대로 둔 채 LZW 단계에서만 근사하기 때문에 한계가 있습니다.
- **gifski 대비:**
  - PSNR 기준 BD-rate는 중앙값 {pct(g_ps['median'])}로 통계적으로 유의한 차이가 없습니다(p = {pv(g_ps['p_wilcoxon'])}).
  - SSIM 기준으로는 모든 클립에서 ST-GIF가 앞섭니다({pct(g_ss['median'])}).
  - VMAF와 VMAF-NEG 기준으로는 모든 클립에서 gifski가 앞섭니다({pct(g_vm['median'])}, {pct(g_vn['median'])}).

**그림 1.** 대표 클립의 RD 곡선. VMAF BD-rate 기준 최상({P[0]}), 중앙({P[1]}), 최하({P[2]}) 클립입니다.

![그림 1](figures/ko/rd_representative.png)

**그림 2.** 클립별 gifski 대비 BD-rate

![그림 2](figures/ko/bd_rate_vs_gifski.png)

ST-GIF의 RD 곡선은 용량 축으로 짧고 품질 상한이 낮습니다. Q=100에서의 중앙값은 다음과 같습니다.

| | PSNR | VMAF |
|---|---:|---:|
| ST-GIF | {CEIL['st_gif']['psnr']:.1f} dB | {CEIL['st_gif']['vmaf']:.1f} |
| gifski | {CEIL['gifski']['psnr']:.1f} dB | {CEIL['gifski']['vmaf']:.1f} |

허용오차 안의 변화를 의도적으로 고정하는 설계의 대가입니다.

## 4.3 지각 품질과 밴딩 분석

SSIM과 VMAF가 반대 방향을 가리키는 원인을 밝히기 위해 밴딩 지표 CAMBI를 측정했습니다(그림 3).

**그림 3.** 같은 용량대에서의 클립별 CAMBI

![그림 3](figures/ko/cambi_per_clip.png)

같은 용량대에서 CAMBI 중앙값은 다음과 같습니다.
- ST-GIF: {mv['cambi'][0]:.2f}
- gifski: {mv['cambi'][1]:.3f}
- FFmpeg: {mv['cambi'][2]:.2f}
- 원본 WebP 자체: {mv['cambi_src']:.2f}

ST-GIF는 {NC - WIN['cambi']}/{NC}개 클립에서 gifski보다 밴딩이 심했습니다. 디더를 쓰는 인코더는 원본의 밴딩까지 대체로 가리지만(gifski는 모든 클립, FFmpeg는 17/20), ST-GIF는 디더가 사실상 동작하지 않아(4.5절) 그라데이션 영역에 계단 무늬가 남습니다.

이 결과로 지표 간 불일치를 다음과 같이 해석할 수 있습니다. SSIM은 국소 분산과 공분산에 기반하므로, gifski 출력의 고주파 디더 패턴을 구조 손상으로 크게 벌점 줍니다. 반면 VMAF와 CAMBI는 디더로 가려진 매끈한 그라데이션을 더 높이 평가하고, ST-GIF의 밴딩과 세부 손실을 벌점 줍니다. VMAF-NEG도 같은 결론을 보이므로, 이 차이는 향상 처리에 의한 점수 왜곡으로 설명되지 않습니다. 따라서 **SSIM 우위만으로 지각 품질 우위를 주장할 수는 없습니다.**

## 4.4 시간 안정성

**표 2.** 같은 용량대 비교 (ST-GIF Q75 vs 용량이 가장 가까운 gifski 설정, 용량 비 중앙값 {mv['ratio']:.2f})

{matched_table('ko')}
ST-GIF는 정적 영역 Flicker가 gifski보다 낮았고({WIN['flicker']}/{NC}), 얼어붙음까지 반영한 TDE에서도 {WIN['tde']}/{NC}개 클립에서 우세했습니다. FFmpeg 대비로는 용량을 중앙값 {mv['ff_ratio']*100:.0f}%로 줄이면서 Flicker를 {mv['flicker'][2]:.2f}에서 {mv['flicker'][0]:.2f}로 낮췄습니다. 시간 안정성은 ST-GIF의 일관된 강점이지만, gifski와의 차이는 Flicker 기준 {mv['flicker'][3]:+.3f}로 크지 않습니다.

## 4.5 어블레이션

구성 요소를 하나씩 제거하거나 교체한 변형을 {CTX['NABL']}개 클립에서 Q45와 Q75로 측정했습니다. 품질 파라미터를 고정하면 구성 요소 제거가 용량과 품질을 동시에 바꾸기 때문에, 이 비교만으로는 효율에 대한 기여를 판단할 수 없습니다. 그래서 각 변형을 **전체 파이프라인의 RD 곡선과 같은 용량에서** 비교했습니다(표 3).

**표 3.** 같은 용량에서의 품질 변화 (중앙값). 음수 ΔPSNR·ΔSSIM, 양수 ΔTDE는 해당 구성 요소가 효율에 기여함을 뜻합니다.

{abl_eq_table('ko')}
**표 4.** Q 고정 비교 (Q45, 전체 대비 변화의 중앙값)

{abl_q_table('ko', 45)}
- **허용오차 유지 판정**(디코더 캔버스 기준의 폐루프 조건부 갱신)의 기여가 가장 큽니다. 제거하면 같은 용량에서 TDE가 {A['no_rdo_keep']['tde']:+.3f} 나빠지고, Q45에서 용량이 {AQ[45][0]['no_rdo_keep'][0]*100:+.0f}% 늘어납니다.
- 스페클 제거는 작지만 일관되게 기여합니다({A['no_despeckle']['worse_count']}/{A['no_despeckle']['in_range']}). LZW 런 병합({A['no_lzw_coalesce']['worse_count']}/{A['no_lzw_coalesce']['in_range']})과 시공간 안정화({A['no_stab']['worse_count']}/{A['no_stab']['in_range']})는 기여가 작고 클립에 따라 다릅니다.
- Floyd–Steinberg 교체는 모든 지표를 악화시켜, 위치 고정 양자화의 이점을 확인해 줍니다.

반면 Bayer 디더를 제거한 변형은 Q45에서 전체 파이프라인과 **바이트 단위로 동일**했고({DOFF[45]['identical']}/{DOFF[45]['n']}), Q75에서도 용량 차 최대 {DOFF[75]['max_rel_bytes']:.2f}%, PSNR 차 최대 {DOFF[75]['max_dpsnr']:.3f} dB로 사실상 같았습니다. 현재 구현은 디더 강도(Q75에서 {d75[0]:.2f})를 Bayer 행렬(−7 ~ +8)에 곱한 뒤 정수로 자르기 때문에, 0이 아닌 오프셋이 16칸 중 {d75[1]}칸(Q75) ~ {d100[1]}칸(Q100)에 불과합니다. 그 크기(±1~2)도 3D LUT의 양자화 간격(4)보다 작습니다. 4.3절의 밴딩 열세는 이 구현 문제에서 비롯된 것으로 보입니다.

## 4.6 선행 연구와의 관계

| 연구 | 표준 GIF 출력 | 프레임 간 중복 활용 | 파일 용량 평가 | 실용 인코더와 비교 |
|---|:---:|:---:|:---:|:---:|
| GIFnets [1] | ✓ | ✗ (프레임 단위) | ✗ | ✗ |
| VivID [2] | ✓ | ✗ (저자들이 향후 과제로 명시) | ✗ | ✗ |
| INR for GIF [3] | ✗ (신경망 가중치) | ✓ | ✓ | ✗ |
| 손실 LZW [4], [5] | ✓ [4] / ✗ [5] | ✗ (정지 이미지) | ✓ | ✗ |
| gifski, gifsicle [11], [12] | ✓ | ✓ | — (논문 없음) | — |
| **이 연구** | ✓ | ✓ | ✓ | ✓ |

ST-GIF의 LZW 런 병합은 Chiang과 Po [4]의 손실 LZW와 같은 원리입니다. 허용오차 안에서 LZW 일치를 늘리는 방식인데, [4]는 시각 특성 기반의 적응형 허용오차와 사전 전체 탐색을 쓰는 반면, ST-GIF는 고정 허용오차와 인접 앵커 치환만 씁니다. 따라서 이 구성 요소는 신규 기여가 아닙니다. 허용오차 유지 판정은 고전적 조건부 갱신 [6]을 GIF 투명 델타에 적용한 것으로, 디코더 캔버스와의 폐루프 비교와 개선폭 히스테리시스를 더한 점이 차이입니다.

## 4.7 논의와 한계

1. **기준 영상의 품질.** 기준이 손실 압축된 WebP라서, 원본 잡음을 지우는 처리는 PSNR과 VMAF에서 불리하게 측정됩니다. 원본 자체의 밴딩도 함께 보고했는데(CAMBI {mv['cambi_src']:.2f}), 디더를 쓰는 인코더는 원본보다 낮은 CAMBI를 보여 "원본과 같을수록 좋다"는 가정이 밴딩에서는 성립하지 않을 수 있습니다.
2. **표본 규모.** 한 사용자의 녹화 폴더에서 뽑은 {NC}개 클립입니다. 콘텐츠 유형별(UI, 스포츠 게임, MOBA 등) 결론을 내리기에는 부족합니다.
3. **신경망 기반 인코더와의 비교 부재.** [1], [2]는 프레임 단위 정지 이미지 인코더라 직접 비교의 의미가 제한적이지만, 리뷰 과정에서 요구될 수 있습니다.
4. **주관적 평가 부재.** VMAF와 CAMBI로 지각 품질을 추정했지만, 사용자 평가로 확인하지 않았습니다.

## 그림 목록 (캡션 초안)

- **그림 1.** 대표 클립 3개({P[0]}, {P[1]}, {P[2]})에서 ST-GIF와 gifski의 율-품질 곡선. 열은 PSNR, SSIM, VMAF이고, 회색 마름모는 FFmpeg 2-pass입니다.
- **그림 2.** 클립별 gifski 대비 ST-GIF의 BD-rate. 음수가 ST-GIF에 유리하며, 점선은 중앙값입니다.
- **그림 3.** 같은 용량대에서의 클립별 CAMBI(낮을수록 밴딩이 적음). 빈 원은 원본 WebP의 CAMBI입니다.
- **부록 그림.** 전체 {NC}개 클립의 RD 곡선: [PSNR](figures/ko/rd_psnr_grid.png), [SSIM](figures/ko/rd_ssim_grid.png), [VMAF](figures/ko/rd_vmaf_grid.png)

## 저자용 메모: 투고 전 확인

**이 데이터로 주장할 수 있는 것**
- 표준 GIF 출력 인코더 중 FFmpeg와 gifsicle 대비 용량과 시간 안정성에서 명확한 우위가 있습니다(모든 클립, p < 0.001).
- 화면 녹화 콘텐츠에서 실용 GIF 인코더들을 RD 곡선, BD-rate, 지각 지표로 비교한 첫 체계적 평가입니다(확인한 범위 내).
- 디코더 캔버스 기준 폐루프 유지 판정이 효율에 가장 크게 기여합니다(어블레이션).
- GIF 평가에서 SSIM과 VMAF·CAMBI가 상반된 결론을 낼 수 있다는 관찰, 그리고 가변 프레임레이트 정렬 문제는 그 자체로 방법론적 기여입니다.

**이 데이터로 주장할 수 없는 것**
- "gifski보다 지각 품질이 좋다" 또는 "더 효율적이다". VMAF, VMAF-NEG, CAMBI 모두 반대입니다.
- "화면 고정 Bayer 디더가 효과가 있다". 현재 구현에서는 사실상 동작하지 않습니다.
- LZW 런 병합의 신규성. [4]에 선행 연구가 있습니다.

**권장 포지셔닝:** 국내 학술대회 또는 arXiv에 "화면 녹화 GIF를 위한 실용 인코더 비교와 폐루프 조건부 갱신 분석" 성격으로 내는 것이 데이터와 맞습니다. 국제 학회를 목표로 한다면, 디더를 고치고 적응형 허용오차 [4]를 결합한 개선판이 VMAF·CAMBI에서 gifski와 대등 이상이 되는지 먼저 확인하기를 권합니다.

## 참고문헌

{REFS_KO}
## 부록: 클립 ID와 클립별 수치

{name_table('ko')}
{clip_table('ko')}"""

# ============================================================== Paper (EN)
latex_t1 = "\\begin{table}[t]\n\\centering\n\\caption{BD-rate of ST-GIF against each anchor over " + str(NC) + " clips (negative favors ST-GIF).}\n\\label{tab:bdrate}\n\\begin{tabular}{llrcrr}\n\\toprule\nAnchor & Metric & Median & 95\\% CI & Wins & $p$ \\\\\n\\midrule\n"
for a, nm in (("gifski", "gifski"), ("gifsicle_lossy_sierra2_4a", "gifsicle")):
    for m in (("psnr", "ssim", "vmaf", "vmaf_neg") if a == "gifski" else ("psnr", "ssim")):
        s = SUM[a][m]
        latex_t1 += f"{nm} & {F.MNAME[m]} & {s['median']:+.1f}\\% & [{s['ci_lo']:+.1f}, {s['ci_hi']:+.1f}] & {s['wins']}/{s['n']} & {'$<$0.001' if s['p_wilcoxon'] < 0.001 else format(s['p_wilcoxon'], '.2f')} \\\\\n"
latex_t1 += "\\bottomrule\n\\end{tabular}\n\\end{table}\n"
latex_t3 = "\\begin{table}[t]\n\\centering\n\\caption{Equal-size ablation: median quality change when a component is removed, relative to the full ST-GIF RD curve.}\n\\label{tab:ablation}\n\\begin{tabular}{lrrrr}\n\\toprule\nComponent & $\\Delta$PSNR & $\\Delta$SSIM & $\\Delta$TDE & Worse \\\\\n\\midrule\n"
for v in S.ABL_VARIANTS[1:]:
    a = AEQ[v]
    latex_t3 += f"{VNAME['en'][v][2:]} & {a['psnr']:+.2f} & {a['ssim']:+.4f} & {a['tde']:+.3f} & {a['worse_count']}/{a['in_range']} \\\\\n"
latex_t3 += "\\bottomrule\n\\end{tabular}\n\\end{table}\n"

pe = f"""# Experiments (paper draft)

> Draft of the paper's **experiments section (Sec. 4)**. Table and figure numbers are provisional; every number is computed from the attached data.
> The [notes for authors](#notes-for-authors-before-submission) at the end list what these results **do and do not support**.

## 4.1 Experimental Setup

**Dataset.** To reflect real use, we drew {NC} clips from 95 Animated WebP recordings made with a screen/game capture tool, stratified by file-size rank so that small files are not over-represented. Resolutions range from {CTX['R0']} to {CTX['R1']}; we use the first {CTX['T1']} frames of each clip (all frames for shorter clips). Sources have variable frame rates and contain ±1–3 levels of capture and compression noise. Prior GIF work [1]–[3] evaluates natural video or still images downscaled to 128×128–256×256; we evaluate screen-capture content at native resolution.

**Baselines.** We compare against three practical encoders that emit standard GIF89a:
- FFmpeg 6.1.1 two-pass (`palettegen=stats_mode=diff`, `paletteuse=dither=sierra2_4a:diff_mode=rectangle`)
- gifsicle 1.94 `-O3 --lossy=N` (N ∈ {{20, 40, 80, 140, 200}}) applied to the FFmpeg output [11], [12]
- gifski 1.34 with Q ∈ {{30, 50, 70, 90, 100}} [11]

ST-GIF is swept over Q ∈ {{15, 30, 45, 60, 75, 90, 100}}. Learned encoders [1], [2] operate on still frames; we did not reproduce them here and discuss them in Sec. 4.6.

**Quality metrics.** The reference is the decoded source WebP in RGB.
- Pixel fidelity: PSNR (mean over all frames) and SSIM [9] (about 20 sampled frames)
- Perceptual quality: VMAF v0.6.1 [7], together with VMAF-NEG, which does not reward enhancement such as denoising or sharpening
- Banding: CAMBI [8]
- Temporal stability: Flicker and TDE (defined below)

Static-region Flicker is the mean absolute frame-to-frame change of the output over pixels Ω_t whose maximum channel change in the source is at most 3. TDE (temporal-difference error) is

  TDE = mean_t mean_p |(D_t(p) − D_{{t−1}}(p)) − (O_t(p) − O_{{t−1}}(p))|

where D is the output and O the source. Flicker only measures spurious change; TDE also penalizes frozen motion. We added it so that locking static regions cannot be rewarded unfairly.

**BD-rate.** For each encoder we interpolate (quality, log bytes) with monotone PCHIP and average the rate difference over the overlapping quality range [10]. Negative values mean ST-GIF needs fewer bytes for the same quality. Across clips we report the median, a bootstrap 95% CI (5,000 resamples) and the Wilcoxon signed-rank test.

**Temporal alignment.** FFmpeg and gifski receive a constant frame rate equal to the mean source rate, so their decoded frames are aligned on a uniform timeline; ST-GIF frames are aligned on the source's variable timeline. Our first implementation aligned the baselines on the source timeline, which understated their PSNR badly (e.g. 35.4 dB instead of the correct 53.5 dB on one clip). We report this because it is an easy mistake when evaluating GIF encoders on variable-frame-rate sources.

**Implementation.** Intel Xeon 2.1 GHz with 2 vCPUs, Python 3.13 and libvmaf built from source. All encoders are deterministic; the 260 outputs re-encoded for VMAF/CAMBI matched the first run byte for byte.

## 4.2 Rate–Quality Comparison

**Table 1.** BD-rate of ST-GIF against gifski and gifsicle ({NC} clips)

{bd_summary_table('en')}
The conclusion depends on the metric.
- **Against gifsicle `--lossy`:** ST-GIF wins on every clip ({pct(gl_ps['median'])} at equal PSNR). gifsicle reduces the FFmpeg output by a median {GSL[20]*100:.0f}% (`--lossy=20`) to {GSL[200]*100:.0f}% (`--lossy=200`), but it only approximates at the LZW stage and leaves the error-diffusion pattern of its input in place.
- **Against gifski:**
  - The PSNR BD-rate is {pct(g_ps['median'])} and not significant (p = {pv(g_ps['p_wilcoxon'])}).
  - ST-GIF wins on every clip under SSIM ({pct(g_ss['median'])}).
  - It loses on every clip under VMAF and VMAF-NEG ({pct(g_vm['median'])} and {pct(g_vn['median'])}).

**Figure 1.** RD curves of representative clips: best ({P[0]}), median ({P[1]}) and worst ({P[2]}) by VMAF BD-rate.

![Figure 1](figures/en/rd_representative.png)

**Figure 2.** Per-clip BD-rate against gifski

![Figure 2](figures/en/bd_rate_vs_gifski.png)

ST-GIF's RD curves are short along the rate axis and saturate early. Medians at Q=100:

| | PSNR | VMAF |
|---|---:|---:|
| ST-GIF | {CEIL['st_gif']['psnr']:.1f} dB | {CEIL['st_gif']['vmaf']:.1f} |
| gifski | {CEIL['gifski']['psnr']:.1f} dB | {CEIL['gifski']['vmaf']:.1f} |

This is the cost of deliberately locking changes inside the tolerance.

## 4.3 Perceptual Quality and Banding

To explain why SSIM and VMAF disagree, we measured banding with CAMBI (Fig. 3).

**Figure 3.** Per-clip CAMBI at matched size

![Figure 3](figures/en/cambi_per_clip.png)

Median CAMBI at matched size:
- ST-GIF: {mv['cambi'][0]:.2f}
- gifski: {mv['cambi'][1]:.3f}
- FFmpeg: {mv['cambi'][2]:.2f}
- The source WebP itself: {mv['cambi_src']:.2f}

ST-GIF shows more banding than gifski on {NC - WIN['cambi']}/{NC} clips. The dithering encoders largely mask even the banding present in the source (gifski on every clip, FFmpeg on 17/20), while ST-GIF, whose dither is effectively inactive (Sec. 4.5), leaves staircase contours in gradients.

This explains the metric disagreement. SSIM is built on local variance and covariance, so it heavily penalizes the high-frequency dither pattern of gifski. VMAF and CAMBI instead favor the smooth, dither-masked gradients and penalize ST-GIF's banding and loss of detail. VMAF-NEG agrees with VMAF, so the gap is not an artifact of enhancement gain. **The SSIM advantage alone therefore does not establish better perceptual quality.**

## 4.4 Temporal Stability

**Table 2.** Matched-size comparison (ST-GIF Q75 vs the gifski setting closest in size; median size ratio {mv['ratio']:.2f})

{matched_table('en')}
ST-GIF has lower static-region Flicker than gifski on {WIN['flicker']}/{NC} clips, and lower TDE, which also accounts for frozen motion, on {WIN['tde']}/{NC}. Against FFmpeg it cuts the median size to {mv['ff_ratio']*100:.0f}% while reducing Flicker from {mv['flicker'][2]:.2f} to {mv['flicker'][0]:.2f}. Temporal stability is a consistent strength of ST-GIF, but the margin over gifski is small ({mv['flicker'][3]:+.3f} Flicker).

## 4.5 Ablation

We removed or replaced one component at a time on {CTX['NABL']} clips at Q45 and Q75. With the quality parameter fixed, removing a component changes both size and quality, so a fixed-Q comparison cannot show whether the component improves efficiency. We therefore compare each variant **against the full pipeline's RD curve at the same size** (Table 3).

**Table 3.** Quality change at equal size (median). Negative ΔPSNR/ΔSSIM or positive ΔTDE means the component improves efficiency.

{abl_eq_table('en')}
**Table 4.** Fixed-Q comparison (Q45, median change vs. the full pipeline)

{abl_q_table('en', 45)}
- The **tolerance-based keep decision**, a closed-loop conditional replenishment against the decoder canvas, contributes most. Removing it worsens TDE by {A['no_rdo_keep']['tde']:+.3f} at equal size and grows files by {AQ[45][0]['no_rdo_keep'][0]*100:+.0f}% at Q45.
- Speckle removal helps modestly but consistently ({A['no_despeckle']['worse_count']}/{A['no_despeckle']['in_range']}). LZW run coalescing ({A['no_lzw_coalesce']['worse_count']}/{A['no_lzw_coalesce']['in_range']}) and stabilization ({A['no_stab']['worse_count']}/{A['no_stab']['in_range']}) help less and vary by clip.
- Replacing the ordered dither with Floyd–Steinberg degrades every metric, which supports position-locked quantization.

In contrast, removing the Bayer dither gave **byte-identical output** at Q45 ({DOFF[45]['identical']}/{DOFF[45]['n']}) and practically identical output at Q75 (at most {DOFF[75]['max_rel_bytes']:.2f}% size and {DOFF[75]['max_dpsnr']:.3f} dB PSNR difference). The implementation multiplies the 4×4 Bayer matrix (−7…+8) by the dither strength ({d75[0]:.2f} at Q75) and truncates to integers, leaving only {d75[1]}/16 (Q75) to {d100[1]}/16 (Q100) non-zero offsets. Their magnitude (±1–2) is also below the 3D LUT's quantization step of 4. The banding deficit in Sec. 4.3 most likely stems from this implementation issue.

## 4.6 Relation to Prior Work

| Work | Standard GIF output | Uses inter-frame redundancy | Evaluates file size | Compared with practical encoders |
|---|:---:|:---:|:---:|:---:|
| GIFnets [1] | ✓ | ✗ (per frame) | ✗ | ✗ |
| VivID [2] | ✓ | ✗ (left as future work by the authors) | ✗ | ✗ |
| INR for GIF [3] | ✗ (network weights) | ✓ | ✓ | ✗ |
| Lossy LZW [4], [5] | ✓ [4] / ✗ [5] | ✗ (still images) | ✓ | ✗ |
| gifski, gifsicle [11], [12] | ✓ | ✓ | — (no paper) | — |
| **This work** | ✓ | ✓ | ✓ | ✓ |

ST-GIF's LZW run coalescing follows the same principle as the lossy LZW of Chiang and Po [4]: both extend LZW matches within a tolerance. However, [4] uses an adaptive, perception-based tolerance and searches the whole dictionary, whereas ST-GIF uses a fixed tolerance and adjacent-anchor substitution. This component is therefore not a novel contribution. The keep decision applies classic conditional replenishment [6] to GIF transparency deltas; what it adds is a closed-loop comparison against the decoder canvas and gain hysteresis.

## 4.7 Discussion and Limitations

1. **Reference quality.** The reference is a lossy WebP, so removing its noise is penalized by PSNR and VMAF. We also report the source's own banding (CAMBI {mv['cambi_src']:.2f}); dithering encoders score below the source, so "closer to the source is better" may not hold for banding.
2. **Sample size.** {NC} clips from one user's capture folder are not enough for per-genre conclusions (UI, sports games, MOBA, etc.).
3. **No learned-encoder comparison.** [1], [2] are per-frame still-image encoders, so a direct comparison is of limited value, but reviewers may ask for it.
4. **No subjective study.** Perceptual quality was estimated with VMAF and CAMBI and has not been validated with users.

## Figure captions (draft)

- **Fig. 1.** Rate–quality curves of ST-GIF and gifski on three representative clips ({P[0]}, {P[1]}, {P[2]}). Columns: PSNR, SSIM, VMAF. Gray diamond: FFmpeg two-pass.
- **Fig. 2.** Per-clip BD-rate of ST-GIF against gifski. Negative favors ST-GIF; the dashed line is the median.
- **Fig. 3.** Per-clip CAMBI at matched size (lower is less banding). Hollow circles: source WebP.
- **Appendix figures.** RD curves for all {NC} clips: [PSNR](figures/en/rd_psnr_grid.png), [SSIM](figures/en/rd_ssim_grid.png), [VMAF](figures/en/rd_vmaf_grid.png).

## Notes for authors (before submission)

**Supported by the data**
- Among encoders that emit standard GIF, ST-GIF is clearly better than FFmpeg and gifsicle in size and temporal stability (every clip, p < 0.001).
- This is, to our knowledge, the first systematic comparison of practical GIF encoders on screen-capture content using RD curves, BD-rate and perceptual metrics.
- The closed-loop keep decision against the decoder canvas is the largest contributor (ablation).
- The observation that SSIM can disagree with VMAF and CAMBI for GIF, and the variable-frame-rate alignment pitfall, are methodological contributions in their own right.

**Not supported by the data**
- "Better perceptual quality" or "more efficient" than gifski. VMAF, VMAF-NEG and CAMBI all point the other way.
- "The screen-locked Bayer dither is effective." It is inactive in the current implementation.
- Novelty of LZW run coalescing. See [4].

**Suggested positioning:** a domestic conference or arXiv paper framed as "a comparison of practical encoders for screen-capture GIFs and an analysis of closed-loop conditional replenishment" fits the data. For an international venue, first check whether an improved version, with the dither fixed and the adaptive tolerance of [4] incorporated, matches or beats gifski on VMAF and CAMBI.

## References

{REFS_EN}
## Appendix A: LaTeX tables

```latex
{latex_t1}
{latex_t3}```

## Appendix B: Clip IDs and per-clip numbers

{name_table('en')}
{clip_table('en')}"""

for path, txt in ((os.path.join(OUT, "github", "BENCHMARK.ko.md"), gh_ko), (os.path.join(OUT, "github", "BENCHMARK.en.md"), gh_en),
                  (os.path.join(OUT, "paper", "experiments.ko.md"), pk), (os.path.join(OUT, "paper", "experiments.en.md"), pe)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(txt)
