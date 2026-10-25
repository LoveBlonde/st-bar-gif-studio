# 🎬 ST-BAR GIF Studio (`st-bar-gif-studio`)

<p align="center">
  <a href="README.md">🇺🇸 English</a> •
  <a href="README.ko.md">🇰🇷 한국어</a> •
  <a href="README.zh-CN.md"><b>🇨🇳 简体中文</b></a> •
  <a href="README.ja.md">🇯🇵 日本語</a> •
  <a href="README.es.md">🇪🇸 Español</a>
</p>

> **下一代 $O(N)$ 时空 LZW-RDO `.gif` (ST-GIF v3) 与块对齐 `.webp` (ST-BAR v4) 动图压缩优化引擎 + 透明穿透屏幕录制工作室**

[![License: MIT](https://img.shields.io/badge/License-MIT-1dd1a1.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-48dbfb.svg)](https://www.python.org/)
[![Codec: ST-GIF v3 / ST-BAR v4](https://img.shields.io/badge/Codec-ST--GIF%20v3%20%7C%20ST--BAR%20v4-ff6b6b.svg)](#)

---

## 🌟 研究背景与核心成果 (Overview)

传统的动图编码器——例如 **FFmpeg (`palettegen + paletteuse`)**、**Pillow** 以及 **`libwebp` (`WebPAnimEncoder`)**——依赖于贪婪的相邻帧逐像素差分（$I_t$ vs $I_{t-1}$）以及误差扩散抖动（Floyd-Steinberg / Sierra）。当处理包含细微传感器噪点或视频压缩伪影（$\pm 1 \sim 3$ RGB）的真实游戏录屏或屏幕捕获时，传统编码器会出现三个灾难性的效率瓶颈：

1. **时域沸腾 (Temporal Boiling) 与双倍差分惩罚：** 随机像素噪点触发 `A → B → A` 振荡，导致子帧边界框（Bounding Box）膨胀至全屏 100%，并产生肉眼可见的背景闪烁。
2. **抖动相位翻转与 Voronoi 边界跳变：** 误差扩散抖动在帧与帧之间不断翻转棋盘格相位，彻底破坏 `.gif` 的 LZW 字典游程（Run-Length），导致文件体积暴增 **5倍 至 25倍**。
3. **DCT 宏块碎片化（在 Animated WebP 中）：** 逐像素打孔（$\alpha=0$）会在 VP8 $16\times 16$ 宏块内部产生高频阶跃边缘，大幅增加 AC 系数熵。

**`st-bar-gif-studio`** 提出了两种全新的、严格 $O(N)$ 单遍（Single-Pass）时空压缩算法——**ST-GIF v3**（针对经典 `.gif`）和 **ST-BAR v4**（针对现代 `.webp`）——并配备了直观易用的 **鼠标点击穿透式透明录屏框架与连续质量滑块 (`1 ~ 100`) 工作室 GUI**。

---

## 📊 基准测试 1：真实游戏与屏幕录制 (`.gif` 压缩对比)

在真实高分辨率游戏与屏幕捕获素材上，与 **Pillow (`optimize=True`)** 及 **FFmpeg 黄金标准双通道管线 (`palettegen + paletteuse=dither=sierra2_4a:diff_mode=rectangle`)** 进行对比：

![ST-GIF v3 Real-World Benchmark](assets/st_gif_realworld_chart.png)

| 测试序列 (`分辨率`, `帧数`) | 编码方法 | 输出 `.gif` 体积 | 相比 `FFmpeg 2-Pass` 体积缩减 | 编码耗时 | PSNR | SSIM | 时域闪烁 (Flicker ↓) |
| :--- | :--- | ---: | :---: | ---: | :---: | :---: | :---: |
| **Clip 1 (UI / 桌面场景)**<br>(`892×619`, 134帧, 源 1,148 KB) | `Pillow Optimize` | 9,050.7 KB | +138.4% | 4,223 ms | 40.77 dB | 0.9935 | 0.147 |
| | `FFmpeg 2-Pass HQ (sierra2_4a)` | 3,796.5 KB | 基准 (Baseline) | 1,166 ms | 53.51 dB | 0.9988 | 0.090 |
| | `FFmpeg 2-Pass (bayer_s3)` | 4,306.0 KB | +13.4% | 571 ms | 41.56 dB | 0.9974 | 0.085 |
| | **ST-GIF v3 Balanced (`Q=75`)** | **174.7 KB** | **-95.4% (缩小 21.7 倍)** | 7,375 ms | **38.94 dB** | **0.9876** | **0.023 (-74.4%)** |
| | **ST-GIF v3 Compact (`Q=45`)** | **130.5 KB** | **-96.6% (缩小 29.1 倍)** | 4,924 ms | **38.37 dB** | **0.9855** | **0.022 (-75.6%)** |
| **Clip 2 (实机游戏画面)**<br>(`557×331`, 106帧, 源 1,296 KB) | `Pillow Optimize` | 9,510.3 KB | -6.3% | 5,341 ms | 34.86 dB | 0.9698 | 2.008 |
| | `FFmpeg 2-Pass HQ (sierra2_4a)` | 10,146.1 KB | 基准 (Baseline) | 2,329 ms | 33.18 dB | 0.9039 | 2.934 |
| | `FFmpeg 2-Pass (bayer_s3)` | 7,470.3 KB | -26.4% | 1,220 ms | 34.00 dB | 0.9375 | 1.168 |
| | **ST-GIF v3 Balanced (`Q=75`)** | **1,321.0 KB** | **-87.0% (缩小 7.7 倍)** | 2,873 ms | **32.99 dB** | **0.9042 (↑)** | **0.035 (-98.8%)** |
| | **ST-GIF v3 Compact (`Q=45`)** | **1,058.2 KB** | **-89.6% (缩小 9.6 倍)** | **1,958 ms** | **32.07 dB** | 0.8748 | **0.034 (-98.8%)** |
| **Clip 3 (FC Online 足球比赛)**<br>(`496×395`, 109帧, 源 1,356 KB) | `Pillow Optimize` | 10,586.1 KB | -10.7% | 5,859 ms | 32.40 dB | 0.9716 | 1.995 |
| | `FFmpeg 2-Pass HQ (sierra2_4a)` | 11,855.2 KB | 基准 (Baseline) | 2,314 ms | 32.41 dB | 0.9354 | 2.198 |
| | `FFmpeg 2-Pass (bayer_s3)` | 10,842.7 KB | -8.5% | 1,227 ms | 33.90 dB | 0.9562 | 1.164 |
| | **ST-GIF v3 Balanced (`Q=75`)** | **2,240.6 KB** | **-81.1% (缩小 5.3 倍)** | 2,844 ms | **31.51 dB** | **0.9156** | **0.072 (-96.7%)** |
| | **ST-GIF v3 Compact (`Q=45`)** | **1,734.3 KB** | **-85.4% (缩小 6.8 倍)** | **2,086 ms** | **30.86 dB** | 0.8932 | **0.072 (-96.7%)** |
| **Clip 4 (英雄联盟全局镜头平移)**<br>(`1051×482`, 89帧, 源 3,325 KB) | `Pillow Optimize` | 19,797.8 KB | -32.9% | 10,033 ms | 31.51 dB | 0.9492 | 1.968 |
| | `FFmpeg 2-Pass HQ (sierra2_4a)` | 29,484.9 KB | 基准 (Baseline) | 6,645 ms | 30.62 dB | 0.8786 | 3.303 |
| | `FFmpeg 2-Pass (bayer_s3)` | 23,491.0 KB | -20.3% | 3,943 ms | 31.83 dB | 0.9296 | 1.487 |
| | **ST-GIF v3 Balanced (`Q=75`)** | **9,998.9 KB** | **-66.1% (缩小 3.0 倍)** | 6,738 ms | **30.21 dB** | **0.8854 (↑)** | **0.292 (-91.2%)** |
| | **ST-GIF v3 Compact (`Q=45`)** | **8,408.8 KB** | **-71.5% (缩小 3.5 倍)** | **4,859 ms** | **29.61 dB** | 0.8513 | **0.298 (-91.0%)** |

---

## 📊 基准测试 2：Animated WebP 优化 (`ST-BAR v4` vs `libwebp`)

![ST-BAR v4 Benchmark Chart](assets/st_bar_benchmark_chart.png)

![ST-BAR v4 Delta Mask Comparison](assets/st_bar_visual_delta.png)

* 在所有有损（Lossy）测试集中，文件体积比 `libwebp` Fast (`method=4`) 和 Slow (`method=6, minimize_size=True`) **缩减 50% 至 80%**；在无损（Lossless）模式下 **缩减 90% 至 97%（最高达 33 倍压缩率）**。
* 编码速度比 `libwebp minimize_size=True` **快达 28 倍**，同时 **提升 Ground-Truth PSNR (+0.8 至 +4.7 dB)** 并消除 **96% 以上的背景时域噪点闪烁**。

---

## 🧠 核心数学模型与算法架构

### 1. 带符号空间盒残差 (Signed Spatial Box Residual) 与 3-Tap 时域尖峰门控 ($O(N)$)
零均值传感器/压缩噪声 $\eta \sim \mathcal{N}(0, \sigma^2)$ 在 $5\times 5$ 空间窗口（$N=25$）内**保留符号求和**时会相互抵消（$\sigma_{\text{mean}} = \sigma / 5$），而真实的物体运动则会使局部像素向同一方向产生一致性偏移。利用均值滤波器的线性性质（$\text{Box}(C_t - A_{t-1}) = \text{Box}(C_t) - \text{Box}(A_{t-1})$），ST-BAR 仅用纯 8-bit SIMD（`cv2.boxFilter` + `cv2.absdiff`）即可在 $< 1\text{ ms}$/帧内精准分离真实运动。

### 2. 闭环 Voronoi 迟滞与 4 阶倍增前缀 LZW 扫描线合并 (`ST-GIF v3`)
不同于开环量化，`ST-GIF v3` 实时追踪解码器画布上当前显示的精确 RGB 颜色 $\hat{C}_{t-1}(x, y) = \text{Palette}[\hat{P}_{t-1}(x, y)]$，并通过以下公式决策调色板索引 $\hat{p}_t(x, y)$：

$$\hat{p}_t(x, y) = \begin{cases} 255 \text{ (TRANSPARENT)} & \text{if } \|\tilde{I}_t(x,y) - \hat{C}_{t-1}(x,y)\|_\infty \le \tau_{\text{keep}} \text{ or } e_{\text{old}} - e_{\text{new}} \le \delta_{\text{gain}} \\ \hat{p}_t(x - 2^k, y) & \text{if } \|\tilde{I}_t(x,y) - \text{Palette}[\hat{p}_t(x - 2^k, y)]\|_\infty \le \delta_{\text{LZW}} \quad (k \in \{0,1,2,3\}) \\ \text{LUT}_{64^3}(\tilde{I}_t(x,y)) & \text{otherwise} \end{cases}$$

---

## 🚀 快速开始 (Quick Start)

### 1. 安装依赖
```bash
git clone https://github.com/LoveBlonde/st-bar-gif-studio.git
cd st-bar-gif-studio
pip install -r requirements.txt
```

### 2. 启动工作室 GUI
在 Windows 上双击 `run_studio.bat`，或运行以下命令：
```bash
python main.py
```
* **🎥 屏幕区域录制 (`🔴 New Recording`)：** 将半透明录制框放置在游戏或视频上方，按下 **`● REC (或 F9)`** 即可按指定帧率（10~60 FPS）录制。录制框内部支持鼠标点击穿透（Click-through），录制时可正常操作游戏。
* **📂 动图/视频裁剪与编辑：** 支持导入 `.webp`、`.gif`、`.mp4`、`.webm` 文件，进行首尾帧裁剪（Trim）、分辨率缩放（Scale）及倍速调节。
* **🎚️ 连续质量滑块 (`1 ~ 100`) 与实时预览：** 拖动滑块自由调节压缩率，点击 **`[⚡ Test Compress Frame]`** 可在导出前立即预览当前帧的真实压缩画质。

### 3. 命令行接口 (CLI)
```bash
# 将 WebP/MP4 转换为超紧凑 GIF (quality=75 均衡模式, quality=45 极限体积模式)
python main.py -i input.webp -o output.gif -q 75

# 转换或重新优化为 Animated WebP (ST-BAR v4)
python main.py -i input.mp4 -o output.webp -q 80
```

---

## 📄 开源协议 (License)
本项目基于 **MIT License** 分发。详情请参阅 [`LICENSE`](LICENSE) 文件。
