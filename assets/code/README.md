# 실험 재현 코드 / Reproduction code

| 파일 | 역할 |
|---|---|
| `rd_bench.py` | RD 벤치마크 본체. 클립마다 FFmpeg 2-pass, gifsicle `-O3 --lossy`, gifski, ST-GIF를 품질 파라미터별로 인코딩하고 PSNR, SSIM, Flicker, TDE를 측정해 `results.jsonl`에 기록합니다. |
| `vmaf_bench.py` | ST-GIF, gifski, FFmpeg 결과물을 다시 인코딩(바이트 일치 검증)한 뒤 Netflix `vmaf` CLI로 VMAF v0.6.1, VMAF-NEG, CAMBI를 측정합니다 (`vmaf.jsonl`, `cambi.jsonl`). |
| `ablation.py` | ST-GIF 구성 요소를 하나씩 끈 변형 7종을 Q=45, 75로 측정합니다 (`ablation.jsonl`). |
| `st_gif_ablate.py` | `st_studio/st_gif_codec.py` 복사본에 어블레이션 스위치(`FLAGS`)만 추가한 파일입니다. 스위치를 모두 켜면 원본과 바이트 단위로 같습니다(20/20 확인). |
| `analyze.py` | 초기 BD-rate 분석 스크립트입니다 (`bd.json`). |
| `stats.py` | 데이터 로딩, BD-rate(PCHIP, log 용량), 부트스트랩 CI, Wilcoxon 검정, 같은 용량 어블레이션 분석 |
| `figures.py` | 한/영 그림 생성 (RD 곡선, BD-rate, 대표 클립, CAMBI) |
| `build_reports.py`, `report_text.py` | 데이터에서 모든 수치를 계산해 GitHub용·논문용 문서(한/영)와 그림, `summary_per_clip.csv`를 생성합니다. |
| `encoder_compare.html`, `render.js` | 인코더 비교 이미지(한/영) 원본과 Playwright 렌더 스크립트 (`?lang=ko` / `?lang=en`) |

## 실행 방법

1. 폴더 구성
   ```
   bench/
     st_studio/            ← st-bar-gif-studio 저장소의 st_studio 폴더를 그대로 복사
       st_gif_ablate.py    ← 이 폴더의 파일을 여기에 추가
     fig/encoder_compare_{ko,en}.png   ← render.js로 생성
     *.py
   ```
2. 의존성
   - `ffmpeg`, `gifsicle` 1.92 이상(`--lossy` 지원), `gifski` (`cargo install gifski`)
   - Netflix libvmaf의 `vmaf` CLI (github.com/Netflix/vmaf, `libvmaf`를 meson으로 빌드). 모델 파일은 저장소의 `model/vmaf_v0.6.1.json`, `model/vmaf_v0.6.1neg.json`을 씁니다.
   - Python: `numpy opencv-python-headless pillow scipy scikit-image matplotlib`
3. 경로 수정
   - `rd_bench.py`: `CLIP_DIR`(입력 WebP 폴더), `GIFSKI`
   - `vmaf_bench.py`: `VMAF`, 모델 파일 경로
4. 실행
   ```bash
   python rd_bench.py 0 2 & python rd_bench.py 1 2       # 워커 2개 병렬, 끝난 클립은 건너뜀
   python vmaf_bench.py 0 2 & python vmaf_bench.py 1 2
   python ablation.py
   python build_reports.py out
   ```

## 주의

- FFmpeg와 gifski에는 평균 fps의 고정 프레임레이트로 입력하므로 평가할 때도 **균등 시간축**으로 정렬합니다(`rd_bench.py`의 `cfr`). ST-GIF는 원본의 가변 시간축으로 정렬합니다. 이걸 섞으면 기준선 PSNR이 크게 낮게 나옵니다.
- 이번 실행에서는 처음 8개 클립 이후로 gifsicle의 Bayer 입력 sweep을 생략했습니다(`if dither == "bayer": continue`). 보고서의 gifsicle 결과는 모두 sierra 입력 기준입니다.
- Windows에서는 `ffmpeg`, `gifsicle`, `gifski`, `vmaf`가 PATH에 있거나 경로가 지정돼 있어야 합니다.
