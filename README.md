# 🎬 ST-BAR GIF Studio (`st-bar-gif-studio`)

> **Next-Generation $O(N)$ Spatio-Temporal LZW-RDO GIF89a & Block-Aligned Animated WebP Compression Engine + Honeycam-Style Screen Recorder Studio**  
> **차세대 $O(N)$ 시공간 LZW-RDO `.gif` 및 블록 정렬 `.webp` 압축 최적화 알고리즘 & 허니캠 스타일 움짤 스튜디오**

[![License: MIT](https://img.shields.io/badge/License-MIT-1dd1a1.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-48dbfb.svg)](https://www.python.org/)
[![Codec: ST-GIF v3 / ST-BAR v4](https://img.shields.io/badge/Codec-ST--GIF%20v3%20%7C%20ST--BAR%20v4-ff6b6b.svg)](#)

---

## 🌟 Overview (연구 배경 및 핵심 성과)

Standard animated image encoders—such as **FFmpeg (`palettegen + paletteuse`)**, **Pillow**, and **`libwebp` (`WebPAnimEncoder`)**—rely on greedy pairwise frame differencing ($I_t$ vs $I_{t-1}$) and error-diffusion dithering (Floyd-Steinberg / Sierra). When applied to real-world game captures or screen recordings containing subtle sensor/compression jitter ($\pm 1 \sim 3$ RGB), standard encoders suffer from three catastrophic inefficiencies:
1. **Temporal Boiling & Double-Delta Penalty:** Random pixel noise triggers `A → B → A` oscillations, expanding sub-frame bounding boxes to 100% of the canvas and causing visible background flicker.
2. **Dither Pattern Phase Flipping & Voronoi Boundary Toggling:** Error-diffusion dithering flips checkerboard patterns across frames, destroying LZW dictionary run lengths in `.gif` and inflating file sizes by **5× to 25×**.
3. **DCT Macroblock Fragmentation (in Animated WebP):** Punching pixel-level transparent holes ($\alpha=0$) creates high-frequency step edges inside VP8 16×16 macroblocks, increasing AC coefficient entropy.

**`st-bar-gif-studio`** introduces two novel, strictly $O(N)$ single-pass compression algorithms—**ST-GIF v3** (for classic `.gif`) and **ST-BAR v4** (for modern `.webp`)—wrapped in a convenient **Honeycam-style Transparent Screen Recorder & Quality-Slider Studio GUI**.

---

## 📊 Benchmark 1: Real-World Game & Screen Captures (`.gif` Compression)

Tested on high-resolution real-world **Honeycam** game/screen captures against **Pillow (`optimize=True`)** and **FFmpeg's Gold-Standard 2-Pass Pipeline (`palettegen + paletteuse=dither=sierra2_4a:diff_mode=rectangle`)**:

![ST-GIF v3 Real-World Honeycam Benchmark](assets/st_gif_honeycam_chart.png)

| Capture Sequence (`Resolution`, `Frames`) | Encoder Method | Output `.gif` Size | Size Reduction vs `FFmpeg 2-Pass` | Encode Time | PSNR | SSIM | Temporal Flicker ↓ |
| :--- | :--- | ---: | :---: | ---: | :---: | :---: | :---: |
| **Clip 1 (UI / Scene)**<br>(`892×619`, 134f, Source 1,148 KB) | `Pillow Optimize` | 9,050.7 KB | +138.4% | 4,223 ms | 40.77 dB | 0.9935 | 0.147 |
| | `FFmpeg 2-Pass HQ (sierra2_4a)` | 3,796.5 KB | Baseline | 1,166 ms | 53.51 dB | 0.9988 | 0.090 |
| | `FFmpeg 2-Pass (bayer_s3)` | 4,306.0 KB | +13.4% | 571 ms | 41.56 dB | 0.9974 | 0.085 |
| | **ST-GIF v3 Balanced (`Q=75`)** | **174.7 KB** | **-95.4% (21.7× smaller)** | 7,375 ms | **38.94 dB** | **0.9876** | **0.023 (-74.4%)** |
| | **ST-GIF v3 Compact (`Q=45`)** | **130.5 KB** | **-96.6% (29.1× smaller)** | 4,924 ms | **38.37 dB** | **0.9855** | **0.022 (-75.6%)** |
| **Clip 2 (Gameplay)**<br>(`557×331`, 106f, Source 1,296 KB) | `Pillow Optimize` | 9,510.3 KB | -6.3% | 5,341 ms | 34.86 dB | 0.9698 | 2.008 |
| | `FFmpeg 2-Pass HQ (sierra2_4a)` | 10,146.1 KB | Baseline | 2,329 ms | 33.18 dB | 0.9039 | 2.934 |
| | `FFmpeg 2-Pass (bayer_s3)` | 7,470.3 KB | -26.4% | 1,220 ms | 34.00 dB | 0.9375 | 1.168 |
| | **ST-GIF v3 Balanced (`Q=75`)** | **1,321.0 KB** | **-87.0% (7.7× smaller)** | 2,873 ms | **32.99 dB** | **0.9042 (↑)** | **0.035 (-98.8%)** |
| | **ST-GIF v3 Compact (`Q=45`)** | **1,058.2 KB** | **-89.6% (9.6× smaller)** | **1,958 ms** | **32.07 dB** | 0.8748 | **0.034 (-98.8%)** |
| **Clip 3 (FC Online)**<br>(`496×395`, 109f, Source 1,356 KB) | `Pillow Optimize` | 10,586.1 KB | -10.7% | 5,859 ms | 32.40 dB | 0.9716 | 1.995 |
| | `FFmpeg 2-Pass HQ (sierra2_4a)` | 11,855.2 KB | Baseline | 2,314 ms | 32.41 dB | 0.9354 | 2.198 |
| | `FFmpeg 2-Pass (bayer_s3)` | 10,842.7 KB | -8.5% | 1,227 ms | 33.90 dB | 0.9562 | 1.164 |
| | **ST-GIF v3 Balanced (`Q=75`)** | **2,240.6 KB** | **-81.1% (5.3× smaller)** | 2,844 ms | **31.51 dB** | **0.9156** | **0.072 (-96.7%)** |
| | **ST-GIF v3 Compact (`Q=45`)** | **1,734.3 KB** | **-85.4% (6.8× smaller)** | **2,086 ms** | **30.86 dB** | 0.8932 | **0.072 (-96.7%)** |
| **Clip 4 (LoL Full-Panning)**<br>(`1051×482`, 89f, Source 3,325 KB) | `Pillow Optimize` | 19,797.8 KB | -32.9% | 10,033 ms | 31.51 dB | 0.9492 | 1.968 |
| | `FFmpeg 2-Pass HQ (sierra2_4a)` | 29,484.9 KB | Baseline | 6,645 ms | 30.62 dB | 0.8786 | 3.303 |
| | `FFmpeg 2-Pass (bayer_s3)` | 23,491.0 KB | -20.3% | 3,943 ms | 31.83 dB | 0.9296 | 1.487 |
| | **ST-GIF v3 Balanced (`Q=75`)** | **9,998.9 KB** | **-66.1% (3.0× smaller)** | 6,738 ms | **30.21 dB** | **0.8854 (↑)** | **0.292 (-91.2%)** |
| | **ST-GIF v3 Compact (`Q=45`)** | **8,408.8 KB** | **-71.5% (3.5× smaller)** | **4,859 ms** | **29.61 dB** | 0.8513 | **0.298 (-91.0%)** |

---

## 📊 Benchmark 2: Animated WebP Optimization (`ST-BAR v4` vs `libwebp`)

![ST-BAR v4 Benchmark Chart](assets/st_bar_benchmark_chart.png)

![ST-BAR v4 Delta Mask Comparison](assets/st_bar_visual_delta.png)

* **50% to 80% smaller file sizes** than `libwebp` Fast (`method=4`) and Slow (`method=6, minimize_size=True`) across all lossy test suites, and **90% to 97% smaller (up to 33× compression)** in lossless mode.
* **Up to 28× faster encoding speed** than `libwebp minimize_size=True`, while **improving Ground-Truth PSNR (+0.8 to +4.7 dB)** and eliminating **96%+ of background temporal boiling**.

---

## 🧠 Core Algorithmic Architecture (핵심 수리 모델 및 알고리즘)

```mermaid
flowchart TD
    A["Input Frame Sequence I_0 ... I_{T-1}"] --> B["Stage 1: L1-Cache Pure-uint8 Temporal Sigma Filter & Anisotropic 1x3 Smoothing"]
    B --> C["Stage 2: Normalized 5x5 Signed Box Residual + 3-Tap Spike Gate & Anchor Lock"]
    C --> D{"Target Output Format?"}
    D -- "GIF89a (ST-GIF v3)" --> E["Motion-Weighted Perceptual Palette + 64x64x64 L2-Cache 3D KD-Tree LUT"]
    E --> F["Closed-Loop Voronoi Hysteresis + 4-Stage Prefix-Doubling LZW Scanline Coalescer"]
    F --> G["Bijection Non-Interlaced LZW Stream Extractor & GIF89a Muxer"]
    D -- "Animated WebP (ST-BAR v4)" --> H["3-Way Entropy Subframe Router: NO_BLEND RGB vs 16x16 Block-Alpha BLEND vs Near-Lossless VP8L"]
    H --> I["Direct RIFF WEBP (VP8X + ANIM + ANMF) Bitstream Assembler"]
```

### 1. Signed Spatial Box Residual & 3-Tap Temporal Spike Gate ($O(N)$)
Zero-mean sensor/compression noise $\eta \sim \mathcal{N}(0, \sigma^2)$ cancels out over a $5\times 5$ spatial window ($N=25$) when summed **with sign preserved** ($\sigma_{\text{mean}} = \sigma / 5$), whereas true object motion shifts local pixels coherently in the same direction. By exploiting the linearity of the box filter ($\text{Box}(C_t - A_{t-1}) = \text{Box}(C_t) - \text{Box}(A_{t-1})$), ST-BAR evaluates coherent motion in pure 8-bit SIMD (`cv2.boxFilter` + `cv2.absdiff`) in $< 1\text{ ms}$ per frame.

### 2. Closed-Loop Voronoi Hysteresis & 4-Stage Prefix-Doubling LZW Coalescer (`ST-GIF v3`)
Instead of open-loop quantization, `ST-GIF v3` tracks the exact RGB color $\hat{C}_{t-1}(x, y) = \text{Palette}[\hat{P}_{t-1}(x, y)]$ currently displayed on the decoder's canvas and selects palette index $\hat{p}_t(x, y)$ via:

$$\hat{p}_t(x, y) = \begin{cases} 255 \text{ (TRANSPARENT)} & \text{if } \|\tilde{I}_t(x,y) - \hat{C}_{t-1}(x,y)\|_\infty \le \tau_{\text{keep}} \text{ or } e_{\text{old}} - e_{\text{new}} \le \delta_{\text{gain}} \\ \hat{p}_t(x - 2^k, y) & \text{if } \|\tilde{I}_t(x,y) - \text{Palette}[\hat{p}_t(x - 2^k, y)]\|_\infty \le \delta_{\text{LZW}} \quad (k \in \{0,1,2,3\}) \\ \text{LUT}_{64^3}(\tilde{I}_t(x,y)) & \text{otherwise} \end{cases}$$

---

## 🚀 Quick Start (설치 및 사용법)

### 1. Installation (설치)
```bash
git clone https://github.com/LoveBlonde/st-bar-gif-studio.git
cd st-bar-gif-studio
pip install -r requirements.txt
```

### 2. Launch Honeycam-Style Studio GUI (프로그램 GUI 실행)
Double-click `run_studio.bat` on Windows, or run:
```bash
python main.py
```
* **🎥 화면 영역 녹화 (허니캠 모드):** 투명한 캡처 프레임 창을 게임이나 영상 위에 올려두고 **`● REC (또는 F9)`** 키를 눌러 원하는 FPS(15~50 FPS)로 즉시 캡처합니다.
* **📂 기존 움짤/영상 최적화:** `.webp`, `.gif`, `.mp4`, `.webm` 파일을 불러와 시작/끝 구간 자르기(Trim), 크기 조절, 배속 조절을 수행합니다.
* **🎚️ 연속 품질 슬라이더 (`1 ~ 100`) & 실시간 프리뷰:** 슬라이더로 압축 강도를 자유롭게 조절하고 **`[⚡ 현재 품질로 압축 테스트 & 화질 미리보기]`**를 눌러 저장 전 정확한 용량(KB/MB)과 실제 압축 화질을 즉시 비교할 수 있습니다.

### 3. Command-Line Interface (CLI 변환)
```bash
# Convert WebP/MP4 to ultra-compact GIF (quality=75 balanced, quality=45 compact)
python main.py -i input.webp -o output.gif -q 75

# Convert or re-optimize to Animated WebP (ST-BAR v4)
python main.py -i input.mp4 -o output.webp -q 80
```

---

## 📄 License
Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.
