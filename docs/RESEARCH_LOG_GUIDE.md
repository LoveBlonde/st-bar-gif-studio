# 📋 `docs/RESEARCH_LOG.md` 작성 가이드 (타 AI 에이전트 작업 지시서)

> **프롬프트 사용법 (다른 AI 클라이언트에게 그대로 전달하세요):**
> *"이 리포지토리의 `docs/RESEARCH_LOG_GUIDE.md` 파일을 읽고, 그 안에 적힌 모든 지침·수식·실험 데이터·논문 비교 내용을 바탕으로 `docs/RESEARCH_LOG.md` (연구 및 엔지니어링 발전 일지) 파일을 상세하고 체계적인 학술/기술 문서 형태로 작성해 줘."*

---

## 1. 작업 개요 및 필수 제약 조건 (Constraints)

1. **생성할 목표 파일**: `docs/RESEARCH_LOG.md`
2. **문서 목적**:
   - `st-bar-gif-studio` (**ST-GIF v3** 및 **ST-BAR v4**) 프로젝트의 초기 알고리즘 설계부터 수식 검증, 화면 캡처 OS 레벨 디버깅, 20개 클립 RD(Rate-Distortion) 벤치마크, 어블레이션(Ablation Study) 원인 규명, 그리고 4편의 선행 학술 논문(1996~2026) 대조를 통한 차세대 개선 방향까지 **전 과정을 논문 작성 및 기술 포트폴리오에 바로 활용할 수 있도록 집대성**한다.
3. **절대 준수 규칙**:
   - ⚠️ **특정 상용 프로그램 브랜드명 언급 절대 금지**: 문서 내 어디에도 `H*neycam`이나 `허*캠` 등의 타사 상용 제품명을 절대 쓰지 말 것. ("기존 상용 움짤 캡처 도구" 또는 `FFmpeg`, `gifsicle`, `gifski`, `Pillow`, `libwebp`로만 표기할 것)
   - 모든 코드 참조는 실제 파일(`st_studio/st_gif_codec.py`, `st_studio/st_bar_webp.py`, `st_studio/gif89a_muxer.py`, `st_studio/gui_app.py`)의 함수명 및 줄 번호와 정확히 일치시킬 것.
   - 수식은 GitHub 마크다운 호환 LaTeX(`$...$`, `$$...$$`)로 명확히 기술할 것.

---

## 2. `docs/RESEARCH_LOG.md` 필수 포함 목차 및 상세 내용

다른 AI 클라이언트는 아래 **Phase 1 ~ Phase 6**의 내용을 빠짐없이 풍부하게 서술하여 `docs/RESEARCH_LOG.md`를 작성해야 한다.

---

### Phase 1. 초기 아키텍처 설계 (`ST-BAR v4` & `ST-GIF v3`)
* **관련 커밋**: `a3c616d`, `dcb271c`
* **해결하려 한 근본 문제 3가지**:
  1. **시간축 끓어오름(Temporal Boiling) & 이중 델타 페널티**: 화면 캡처나 게임 영상의 미세 노이즈($\pm 1 \sim 3$ RGB)가 `A → B → A` 진동을 일으켜 정지 배경임에도 서브프레임 바운딩 박스가 전체 화면(99.9%)으로 팽창.
  2. **오차 확산 디더링 위상 반전 & 허용오차 0(`transdiff`)의 한계**: `FFmpeg`(`sierra2_4a` / `floyd_steinberg`)는 매 프레임 디더 패턴 위상이 뒤집히고 직전 프레임과 인덱스가 정확히 일치($\tau=0$)할 때만 투명 처리하여 GIF LZW 가로 런(Run-Length)이 파편화됨.
  3. **WebP 매크로블록 파편화**: `libwebp`의 `FlattenSimilarBlocks`는 $8\times 8$ 블록 전체가 $\pm 4$ 이내일 때만 투명화하여 노이즈 앞에서 무력화됨.
* **초기 핵심 파이프라인 구성**:
  - **Stage 1 (`st_bar_webp.py:stabilize_pure_u8_fast`)**: L1 캐시 친화적 순수 `uint8` 3-Tap 시간축 시그마 필터($t-1, t, t+1$) + $5\times 5$ 부호 보존 공간 박스 잔차(`cv2.blur`) + 패치워크 앵커 프레임(`anchor`, `box_anchor`) 잠금. (GIF는 $1\times 3$ 가로 비등방성 스무딩 추가)
  - **Stage 2 (`st_gif_codec.py:build_motion_weighted_palette_and_lut`)**: 움직임 마스크($M_t$) 영역 가중 샘플링 글로벌 팔레트(255색 + 투명 255번) + 지각 가중치 $\mathbf{w}=(1.0, 1.15, 0.85)$ 기반 $64^3$ 3D KD-Tree LUT($O(1)$ 양자화).
  - **Stage 3 (`st_gif_codec.py:quantize_frame_with_locked_bayer`)**: 양자화 오차 $e_q > 7$인 그라데이션 픽셀에만 선택적으로 적용되는 화면 절대좌표 고정 $4\times 4$ Bayer 디더링 ($Q > 50$에서만 활성화).
  - **Stage 4 (`st_gif_codec.py:coalesce_lzw_horizontal_runs` & `encode_st_gif`)**: 4단계 블록-앵커 수평 LZW 런 병합 + 디코더 캔버스(`canvas_rgb`) 기준 폐루프 보로노이 히스테리시스 투명 판정 + $3\times 3$ 및 $1\sim 2\text{px}$ 고립 스페클 제거.

---

### Phase 2. 코드-수식 정합성 전수 감사 및 7대 교정 (Code-Math Alignment)
* **관련 커밋**: `a480046`, `03317d7`, `730fee4`
* **배경**: 문서의 이론 수식과 실제 최적화 구현(`st_studio/`)을 한 줄씩 대조하여 발견된 7가지 차이를 100% 실제 코드 기준으로 정합화함.
* **반드시 기록할 7대 정합화 항목**:
  1. **LZW 수평 런 병합 수식 교정 (`st_gif_codec.py:113-160`)**:
     - 초기 문서에는 단순 지수 거리 $x - 2^k$ ($k \in \{0,1,2,3\}$)로 적혀 있었으나, 실제 코드는 $2 \to 4 \to 8$ 블록의 고정 앵커로 연쇄 병합(Chained Block-Anchor Coalescing)하고 마지막에 짝수 경계를 스티칭하는 4단계 구조임(참조 거리 최대 4칸):
       $$a_k(x)=\begin{cases} x-1 & k=1,\; x\equiv 1 \pmod 2\\ 4\lfloor x/4\rfloor+1 & k=2,\; x \bmod 4\in\{2,3\}\\ 8\lfloor x/8\rfloor+3 & k=3,\; x \bmod 8\in\{4,\dots,7\}\\ x-1 & k=4,\; x\equiv 0 \pmod 2,\ x\ge 2 \end{cases}$$
       $$\hat{p}_t(x, y) \leftarrow \hat{p}_t(a_k(x), y) \quad \text{if } \|\tilde{I}_t(x, y) - \text{Pal}[\hat{p}_t(a_k(x), y)]\|_\infty \le \delta_{\text{LZW}}$$
  2. **투명 픽셀(255) 판정의 4중 조건 및 스페클 후처리 명문화 (`st_gif_codec.py:295-330`)**:
     - 단순 오차 비교뿐 아니라 $\neg \text{active}_t(x,y) \lor (p_{\text{new}} = p_{\text{canvas}}) \lor (e_{\text{old}} \le \tau_{\text{keep}}) \lor (e_{\text{old}} - e_{\text{new}} \le \delta_{\text{gain}})$의 4중 OR 조건과, 드리프트 가드($\text{active}_t = M_t \lor (e_{\text{old}} > \tau_{\text{keep}} + 6)$), $3\times 3$ 이웃 2개 이하 스페클 제거, 가로 $1\sim 2\text{px}$ 고립 갱신 제거를 명문화.
  3. **조건부 고정 $4\times 4$ Bayer 디더링 수식 반영 (`st_gif_codec.py:92-110`)**:
     - $e_q(x,y) > 7$ 및 $Q > 50$ 조건부 디더링 수식 명시.
  4. **패치워크 앵커 박스 평균(`box_anchor`)의 선형 근사(`≈`) 명시 (`st_bar_webp.py:126-155`)**:
     - `box_anchor`는 매번 전체 프레임을 다시 블러링하는 대신 움직인 영역(`dilated_u8`)에만 `box_clean[t]`를 덮어쓰는 패치워크 구조이므로 모션 경계에서 $\text{Box}(C_t - A) \approx \text{Box}(C_t) - B_{\text{anchor}}$ 근사 관계임을 정확히 표기.
  5. **Stage 1의 $1\times 3$ 비등방성 가로 스무딩 분기 명시**:
     - GIF(`anisotropic_smooth=True`, 가로 LZW 런 연장 목적)와 WebP(`anisotropic_smooth=False`, 2D 매크로블록 보존 목적)의 차이를 아키텍처 다이어그램에 반영.
  6. **시간 복잡도 표현 정밀화**:
     - "단일 패스(single-pass)"라는 모호한 표현 대신, 프레임 쌍 유사도·안정화·팔레트 샘플링·인코딩이 각각 선형 시간으로 수행되는 **"엄밀한 선형 시간 $O(N)$ (프레임당 상수 패스)"**로 정밀화.
  7. **WebP 3-Way 서브프레임 라우터 명칭 정밀화 (`st_bar_webp.py:225-247`)**:
     - 엔트로피 추정치가 아닌 픽셀 점유율($<22\%$, $<2200\text{px}$) 및 $16\times 16$ 블록 점유율($\ge 60\%$) 휴리스틱을 사용하므로 **"점유율 기반(Occupancy-based) 3-Way 라우터"**로 명명.

---

### Phase 3. Windows OS 레벨 투명 캡처 프레임 디버깅 기록 (`gui_app.py`)
* **관련 커밋**: `fabc561`, `2ae36e0`
* **발생했던 2가지 실제 버그와 해결 원리**:
  1. **이슈 ① — Python 3.13 Tcl/Tk 스레드 친화성(Thread-Affinity) 충돌 (`fabc561`)**:
     - *증상*: 녹화 후 정지를 눌러도 프리뷰에 아무것도 뜨지 않음.
     - *원인*: 백그라운드 녹화 스레드(`_record_loop`) 내부에서 `_get_capture_bbox()`(`self.update_idletasks()`) 및 `self.after()`를 직접 호출해 `RuntimeError: main thread is not in main loop`가 발생하며 첫 프레임 캡처 전에 스레드가 즉시 종료됨.
     - *해결*: 모든 Tkinter 좌표 갱신과 상태 표시줄 갱신은 메인 스레드 타이머(`_poll_recording_status`)와 `queue.Queue`(`_poll_worker_queue`)로 격리하고, 백그라운드 스레드는 순수 화면 캡처만 수행하도록 분리.
  2. **이슈 ② — Windows DWM `-transparentcolor`(`WS_EX_LAYERED`)와 GDI `CAPTUREBLT`의 검은 화면 충돌 (`2ae36e0`)**:
     - *증상*: 녹화 프레임은 정상 수집되었으나 프리뷰와 저장된 GIF가 모두 순수 검은색(`RGB = [0, 0, 0]`)으로 나옴.
     - *원인*: Tkinter의 `attributes("-transparentcolor", "#010203")`는 OS 레벨에서 창 전체를 `WS_EX_LAYERED` + `LWA_COLORKEY`로 만듦. 사람 눈에는 투명하게 보이지만, Windows DWM은 컬러키가 적용된 투명 영역을 내부 비트맵에서 불투명한 검은색(`BGRA = [0, 0, 0, 255]`)으로 처리함. `mss`가 `BitBlt(..., SRCCOPY | CAPTUREBLT)`로 화면을 찍을 때 최상단(`-topmost`)에 덮여 있던 녹화 창 자신의 `[0, 0, 0, 255]` 표면을 그대로 찍어버린 것이 원인.
     - *해결*: `-transparentcolor`를 완전히 제거하고, Win32 API `CreateRectRgn` + `CombineRgn(..., RGN_DIFF)` + `SetWindowRgn`(`_apply_window_hole`)을 사용해 캡처 테두리 내부 직사각형 영역을 **OS 창 영역에서 물리적으로 도려냄(Cutout Hole)**. 추가로 `mss` → `ImageGrab(include_layered_windows=False)` → `PrintWindow(PW_RENDERFULLCONTENT)` 3중 캡처 폴백을 구축.

---

### Phase 4. 대규모 실측 실험 (20개 클립 RD 벤치마크 & 어블레이션 연구)
* **핵심 실험 결론 요약**:
  1. **전반적 경향 (20개 클립 일관성)**:
     - **PSNR (픽셀 단위 수치 오차)**: `ST-GIF v3`는 `gifski`와 비기거나 소폭 낮음. (노이즈를 의도적으로 제거하고 허용오차 내 픽셀을 유지/병합하기 때문)
     - **SSIM (구조 보존) & 시간 안정성 (Temporal Stability)**: **20개 클립 전부(20전 20승)에서 `gifski` 및 기존 인코더를 큰 폭으로 앞섬.**
     - **논문 핵심 주장(Thesis)의 정립**: 단순한 "더 작은 GIF"가 아니라, **"동일 비트레이트(용량)에서 지각 품질(구조 보존 SSIM · 시간 안정성 · 밴딩 억제)이 훨씬 우수한 시공간 안정화 GIF"**로 포지셔닝.
  2. **제3의 지각 지표 검증 (VMAF & CAMBI)**:
     - SSIM만 제시할 경우 "유리한 지표만 선택했다"는 리뷰어 반론을 막기 위해, 넷플릭스의 비디오 지각 품질 지표인 **VMAF**와 계단 현상(Banding) 지각 지표인 **CAMBI**를 전 클립(260개 설정 조합)에 대해 측정.
  3. **구성 요소별 어블레이션(Ablation Study)의 결정적 발견**:
     - **발견 1 (`coalesce_lzw_horizontal_runs` OFF 실험)**: 첫 클립에서 LZW 수평 런 병합 단계를 끄자, **파일 용량은 약 `+8%` 증가했지만 PSNR이 무려 `+1.9 dB` 상승**함. 즉, LZW 런 병합 단계가 PSNR 손실의 주원인임이 규명됨.
     - **발견 2 (`Q=100`에서의 PSNR 상한 현상)**: 허용오차 안의 미세 변화를 버리는 구조 때문에 최고 품질(`Q=100`)에서도 일부 클립의 PSNR이 약 `42 dB` 부근에서 포화(Cap)되는 현상 확인. (`map_quality_to_st_gif_params`에서 `Q=100`일 때도 `voronoi_keep_tol=2`, `lzw_run_tol=2`로 남아 있는 문제)

---

### Phase 5. 4대 선행 학술 논문(1996~2026) 심층 대조 및 이론적 해답
`docs/RESEARCH_LOG.md`에 아래 4편의 학술 논문을 인용하고, 우리 연구와의 차이점 및 Phase 4 어블레이션 문제의 해답을 연결할 것:

1. **Chiang & Po (ISSPA 1996)** — *"Lossy LZW Algorithm with Adaptive Threshold for Palettized Image Compression"*
   - **내용**: 인간 시각 체계(HVS)의 **Weber 대비 법칙**($\Delta I / I \approx 3\%$)과 $3\times 3$ 이웃 휘도 평균 편차 기반 **공간 마스킹 계수($K = m V(x) + C$)**를 결합해, LZW 사전 매칭 시 채널별 오차 $|c - \tilde{c}| \le K\Delta$를 허용하여 정지 GIF 압축률을 25~50% 개선.
   - **한계**: 단일 정지 이미지(Lena, Peppers 등)만 다루며 시간축/프레임 델타 개념이 전혀 없음. 또한 LZW 사전 테이블 내부를 매번 선형 탐색하여 연산량이 큼.
2. **Crnojević, Šenk, Trpovski (IEEE TELSIKS 2003)** — *"Lossy Lempel-Ziv Algorithm for Image Compression"*
   - **내용**: 국소 분산($\sigma_i^{2n+1}$)에 로그 비례하는 최대 허용 편차 $e_i = \frac{\log_{10}(\sigma_i^{2n+1}/a + 1)}{\log_{10}(\sigma_{\max}/a + 1)} E_{\max}$를 적용.
   - **우리 어블레이션과의 결정적 연결 고리**: 이 논문의 Section V (p.524, Fig. 5 vs Fig. 6)에서 **"국소 분산 제어 없이 이미지 전체에 고정 허용오차($E_{\max}=10$)를 적용하면, 평탄한 영역(Flat areas)에서 거친 양자화 계단(Coarse quantization)이 발생해 화질과 PSNR이 심각하게 저하된다"**는 사실을 실험적으로 증명함!
   - 즉, 우리 Phase 4 어블레이션에서 LZW 런 병합이 PSNR을 `1.9 dB` 깎아먹은 이유가 바로 **평탄 영역(낮은 국소 분산)과 복잡한 텍스처 영역(높은 국소 분산)을 구분하지 않고 고정 $\delta_{\text{LZW}}$를 일괄 적용했기 때문**임이 학술적으로 완벽히 설명됨.
3. **Yifei Wang et al. (IEEE TCSVT, Vol. 35, No. 6, June 2025, pp. 6101–6113)** — *"VivID: A Visually Improved GIF Encoding Network Design"*
   - **내용**: 딥러닝 기반 Multi-Palette Extractor(MPE) + CAMBI를 증류 학습한 Banding Scorer(BS) + Context Cluster 기반 Banding Remover(BR)를 통해 정지 GIF의 밴딩(CAMBI)과 점박이 노이즈를 동시에 줄임.
   - **한계 및 우리 연구의 포지셔닝**:
     - `VivID`는 Section III-A(p.6103)에서 *"LZW 압축은 다루지 않는다"*고 명시하여 **파일 용량 절감 기능이 전혀 없음**.
     - 무엇보다 Section IV-G-5(p.6111)에서 **"기존 방법들과 우리 방법 모두 프레임별 독립 처리(frame-by-frame)에 머물러 있으며, 동적 GIF에서 프레임 간 관계(inter-frame relationships)를 활용하는 것은 향후 연구 과제"**라고 직접 한계를 고백함.
     - **우리의 강점**: `ST-GIF`는 GPU 신경망 없이도 `VivID`가 미해결 과제로 남긴 **동적 GIF의 프레임 간 시공간 일관성 + CAMBI(밴딩) 억제 + LZW 파일 용량 대폭 절감**을 동시에 달성함.
4. **Yifei Wang et al. (ACM ICMR 2026, pp. 459–467)** — *"Neural Representations for Animated GIFs"*
   - **내용**: 4층 MLP 신경망이 시공간 좌표 $(t,x,y)$를 입력받아 팔레트 인덱스를 예측하도록 움짤마다 **50,000 에폭 과적합(Overfitting) 학습**시킨 뒤, FP16 가중치를 **`.npz` 파일**로 저장.
   - **한계 및 우리 연구의 포지셔닝**:
     - 결과물이 표준 `.gif` 파일이 아니라 **`.npz` 신경망 가중치 아카이브**이므로 웹 브라우저, 메신저, 커뮤니티 등 기존 GIF 생태계에서 전혀 열리지 않음(전용 GPU 디코더 필수).
     - $128\times 128$ 해상도 40프레임짜리 움짤 1개를 인코딩하는 데 GPU로 50,000 에폭 학습이 필요해 실시간 화면 캡처에 사용 불가능.
     - **우리의 강점**: `ST-GIF`는 **100% 표준 GIF89a 디코더 호환성**을 완벽히 지키면서, CPU에서 수 초 내에 고해상도 움짤을 실시간 인코딩함.

---

### Phase 6. 차기 알고리즘 업그레이드 설계 명세 (`ST-GIF v3.1 / v4`: HVS-Adaptive LZW & Uncapped High-Q)
Phase 4의 어블레이션 결과와 Phase 5의 논문 분석을 결합하여, 앞으로 `st_gif_codec.py`에 적용할 3가지 구체적 개선 수식을 정리할 것:

1. **국소 분산(Local Variance) + Weber 밝기 마스킹 기반 적응형 $\delta_{\text{LZW}}(x,y)$**:
   - Stage 1에서 이미 계산된 $5\times 5$ 박스 평균 $B_t(x,y)$를 재활용하여 추가 연산 없이 국소 활동도(Local Activity) $V_t(x,y) = \|\tilde{I}_t(x,y) - B_t(x,y)\|_\infty$ (또는 $3\times 3$ 평균 편차)를 산출.
   - 평탄한 그라데이션 영역($V_t(x,y) \le \tau_{\text{flat}}$)에서는 $\delta_{\text{LZW}}(x,y) = 0$으로 조여 **PSNR 1.9 dB 손실과 밴딩(CAMBI)을 원천 방지**하고, 고분산 텍스처 영역($V_t(x,y) > \tau_{\text{flat}}$)에서만 $\delta_{\text{LZW}}(x,y)$를 허용하여 LZW 압축률을 획득:
     $$\delta_{\text{LZW}}(x,y) = \text{clip}\!\left(\left\lfloor \delta_{\max} \cdot \frac{\log(1 + V_t(x,y)/\alpha)}{\log(1 + V_{\max}/\alpha)} \right\rfloor,\ 0,\ \delta_{\max}\right)$$
2. **지각 가중 색차(Perceptual Color Distance) 적용**:
   - LZW 병합 및 보로노이 히스테리시스 판정 시 단순 채널 최대차($L_\infty$) 대신 팔레트 생성에 쓰인 지각 가중치 $\mathbf{w}=(1.0, 1.15, 0.85)$ 또는 Weber 휘도 보정을 일관되게 사용하여 녹색/휘도 왜곡을 억제.
3. **고품질 구간(`Q → 100`) 무손실 수렴 보장 (PSNR 42 dB 상한 해제)**:
   - `map_quality_to_st_gif_params(quality)`에서 $Q \ge 90 \to 100$으로 갈 때 `voronoi_keep_tol`, `voronoi_gain_min`, `lzw_run_tol`, `box_gate`가 모두 `0`으로 매끄럽게 수렴하도록 설계하여, RD 곡선의 고비트레이트 구간에서 PSNR 상한(Ceiling) 없이 원본 팔레트 이론적 최대 PSNR까지 도달하도록 개선.

---

## 3. 작성 스타일 가이드 (Formatting Tips)
- 상단에 프로젝트 요약 배지와 한눈에 보는 **연구 발전 타임라인 표(Phase 1 ~ Phase 6)**를 배치할 것.
- 각 Phase마다 **[배경/문제] → [원인 분석/수식] → [해결 코드/실험 결과] → [의의]** 구조로 명확하게 서술할 것.
- 논문 집필 시 `Introduction`, `Related Work`, `Proposed Method`, `Ablation Study` 섹션에 그대로 복사해 넣을 수 있을 만큼 학술적 엄밀함과 가독성을 갖출 것.
