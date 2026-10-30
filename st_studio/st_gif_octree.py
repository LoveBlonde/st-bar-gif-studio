"""
ST-GIF Octree: ST-GIF v3 with a clip-wide octree colour codebook and per-frame tree cuts.

Builds on Roytman & Gotsman, "Dynamic Color Quantization of Video Sequences", IEEE TVCG 1995. In that paper, a cube
that persists between consecutive frames keeps its representative colour.
  1. One oct-cut tree is built for the whole clip (6-bit grid, split the node with the largest SSE until `leaves`
     leaves). Every node's representative colour is its clip-wide centroid, so a node is drawn in the same colour
     all clip long, and the clip as a whole can use more than 256 colours.
  2. For each frame, the leaves used by the pixels that frame redraws are collapsed to a cut of <= 255 nodes. That
     cut becomes the frame's GIF Local Color Table. Static pixels stay on the canvas through GIF transparency, so a
     new table never recolours them. That is why the paper's reserved entries and entry ordering are not needed here.
  3. Reused from v3: the closed-loop keep decision on the decoder canvas, LZW run coalescing and trimmed local
     colour tables.
  4. Region growth: the refresh mask is dilated vertically into touching pixels whose canvas error exceeds
     `grow_tol`. A connected area is then refreshed in one frame. Without this, the per-pixel keep decision can
     alternate row by row and leave 1-px stripes on thick lines.
Options (`oct=` dict, all optional):
  leaves (2048), motion_w (3.0), lam (1.0, extra cost for collapsing nodes of the previous cut),
  grow (4), grow_tol (11), cut ("level" | "global"), dither (True),
  keep_est ("prevcut" | "v3"): which colours the keep decision assumes a refreshed pixel would get. "prevcut" maps
  the target to the previous frame's cut, i.e. colours that can actually appear on the canvas. "v3" uses v3's
  256-colour global palette, the behaviour before 2026-10-30. That palette never matches canvas colours, so its
  "same colour -> keep" test was dead and the refresh gain was misjudged.
  Research switches for ablations: stab, keep, coalesce (all True).
"""
import time
import numpy as np
import cv2
from scipy.spatial import cKDTree

from .st_bar_webp import max_channel_u8, fast_bounding_box, estimate_game_capture_noise_sigma, stabilize_pure_u8_fast
from .gif89a_muxer import assemble_gif89a_lct
from .st_gif_codec import (BAYER_4X4, build_motion_weighted_palette_and_lut, quantize_frame_with_locked_bayer,
                           coalesce_lzw_horizontal_runs, map_quality_to_st_gif_params, frame_delays_cs,
                           resample_to_gif_rate)

OCT = {"leaves": 2048, "lam": 1.0, "motion_w": 3.0, "grow": 4, "grow_tol": 11, "cut": "level", "keep_est": "prevcut",
       "dither": True}
W8 = np.array([1.0, 1.15, 0.85], np.float32)          # channel weights for nearest-colour mapping
B = 6                      # bits per channel of the finest grid
G = 1 << B


def _code(rgb, d):
    """node code at depth d (0..B) for uint8 rgb (..., 3)."""
    s = 8 - d
    r = (rgb[..., 0].astype(np.int32) >> s); g = (rgb[..., 1].astype(np.int32) >> s); b = (rgb[..., 2].astype(np.int32) >> s)
    return (r << (2 * d)) | (g << d) | b


class OctCut:
    def __init__(self, frames, masks, leaves, motion_w):
        cnt = np.zeros(G ** 3, np.float64); sm = np.zeros((G ** 3, 3), np.float64); sq = np.zeros(G ** 3, np.float64)
        stride = max(1, len(frames) // 40)
        for t in range(0, len(frames), stride):
            f = frames[t][::2, ::2].reshape(-1, 3)
            w = np.ones(len(f))
            if masks is not None and t > 0:
                w = w + (motion_w - 1.0) * masks[t][::2, ::2].reshape(-1)
            c = _code(f, B); ff = f.astype(np.float64)
            cnt += np.bincount(c, w, G ** 3)
            for k in range(3):
                sm[:, k] += np.bincount(c, w * ff[:, k], G ** 3)
            sq += np.bincount(c, w * (ff ** 2).sum(1), G ** 3)
        # per-depth aggregates
        self.cnt, self.cen, self.sse = {}, {}, {}
        c3 = cnt.reshape(G, G, G); s3 = sm.reshape(G, G, G, 3); q3 = sq.reshape(G, G, G)
        for d in range(B + 1):
            k = G >> d
            n = c3.reshape(1 << d, k, 1 << d, k, 1 << d, k).sum((1, 3, 5)).reshape(-1)
            s = s3.reshape(1 << d, k, 1 << d, k, 1 << d, k, 3).sum((1, 3, 5)).reshape(-1, 3)
            q = q3.reshape(1 << d, k, 1 << d, k, 1 << d, k).sum((1, 3, 5)).reshape(-1)
            with np.errstate(invalid="ignore", divide="ignore"):
                cen = np.where(n[:, None] > 0, s / np.maximum(n[:, None], 1e-9), 0)
            self.cnt[d] = n; self.cen[d] = np.clip(np.round(cen), 0, 255).astype(np.uint8)
            self.sse[d] = q - (s ** 2).sum(1) / np.maximum(n, 1e-9)
        # oct-cut: split the leaf with the largest SSE until `leaves` leaves
        import heapq
        leaf = {(0, 0)}; heap = [(-self.sse[0][0], 0, 0)]
        while heap and len(leaf) < leaves:
            _, d, c = heapq.heappop(heap)
            if d >= B:
                continue
            kids = [(d + 1, (((c >> (2 * d)) * 2 + (i >> 2)) << (2 * (d + 1))) |
                     ((((c >> d) & ((1 << d) - 1)) * 2 + ((i >> 1) & 1)) << (d + 1)) |
                     (((c & ((1 << d) - 1)) * 2 + (i & 1)))) for i in range(8)]
            kids = [k for k in kids if self.cnt[k[0]][k[1]] > 0]
            if not kids:
                continue
            leaf.discard((d, c)); leaf.update(kids)
            for kd, kc in kids:
                heapq.heappush(heap, (-self.sse[kd][kc], kd, kc))
        # finest-grid cell -> leaf (depth, code); empty cells fall back to nearest populated ancestor leaf
        self.leaf_d = np.full(G ** 3, -1, np.int8)
        cells = np.arange(G ** 3)
        r = cells >> (2 * B); g = (cells >> B) & (G - 1); b = cells & (G - 1)
        for d in range(B + 1):
            s = B - d
            code_d = ((r >> s) << (2 * d)) | ((g >> s) << d) | (b >> s)
            mark = np.zeros(8 ** d, bool)
            idx = [c for (dd, c) in leaf if dd == d]
            if idx:
                mark[np.array(idx)] = True
                hit = (self.leaf_d < 0) & mark[code_d]
                self.leaf_d[hit] = d
        self.leaf_d[self.leaf_d < 0] = 0
        self.leaves = leaf

    def node_of(self, rgb, d):
        return _code(rgb, d)

    def cut_for(self, pix, w, prev_cut, lam, nmax=255):
        """pix: (N,3) uint8 colours written this frame -> cut (set of (d,code)), and per-pixel node (d, code)."""
        cell = _code(pix, B)
        ld = self.leaf_d[cell].astype(np.int32)
        nodes = {}
        for d in np.unique(ld):
            sel = ld == d
            cd = _code(pix[sel], d)
            u, cc = np.unique(cd, return_counts=True)
            for a, n in zip(u, cc):
                nodes[(int(d), int(a))] = nodes.get((int(d), int(a)), 0) + int(n)
        while len(nodes) > nmax:
            # group present nodes by parent at the deepest level present
            dmax = max(d for d, _ in nodes)
            groups = {}
            for (d, c), n in nodes.items():
                if d == dmax:
                    p = _parent(d, c)
                    groups.setdefault(p, []).append(((d, c), n))
            costs = []
            for p, ch in groups.items():
                pc = self.cen[p[0]][p[1]].astype(np.float64)
                cost = 0.0
                for (d, c), n in ch:
                    e = ((self.cen[d][c].astype(np.float64) - pc) ** 2).sum() * n
                    cost += e * (1.0 + lam if (d, c) in prev_cut else 1.0)
                costs.append((cost, p, ch))
            multi = [x for x in costs if len(x[2]) > 1]
            if multi:
                multi.sort(key=lambda x: x[0] / (len(x[2]) - 1))
                todo = multi
            else:
                todo = costs            # only single children left at this depth: lift them one level
            need = len(nodes) - nmax
            for cost, p, ch in todo:
                if need <= 0 and multi:
                    break
                tot = sum(n for _, n in ch)
                for k, _ in ch:
                    del nodes[k]
                nodes[p] = nodes.get(p, 0) + tot
                need -= len(ch) - 1
        return set(nodes)

    def cut_global(self, pix, prev_cut, lam, nmax=255):
        """Cost-ordered cut over the whole tree: repeatedly collapse the ancestor whose subtree of current nodes
        costs least per removed node (weighted squared distance between clip-wide centroids). Nodes that were in
        the previous frame's cut cost (1 + lam) more to collapse."""
        import heapq
        cell = _code(pix, B); ld = self.leaf_d[cell].astype(np.int32); nodes = {}
        for d in np.unique(ld):
            u, cc = np.unique(_code(pix[ld == d], int(d)), return_counts=True)
            for a, n in zip(u, cc):
                nodes[(int(d), int(a))] = nodes.get((int(d), int(a)), 0) + int(n)
        if len(nodes) <= nmax:
            return set(nodes)

        def anc(k):
            out = []
            while k[0] > 0:
                k = _parent(*k); out.append(k)
            return out
        desc = {}
        for k in nodes:
            for a in anc(k):
                desc.setdefault(a, set()).add(k)

        def cost(a):
            ch = desc.get(a)
            if not ch or len(ch) < 2:
                return None
            pc = self.cen[a[0]][a[1]].astype(np.float64); c = 0.0
            for k in ch:
                e = ((self.cen[k[0]][k[1]].astype(np.float64) - pc) ** 2).sum() * nodes[k]
                c += e * (1.0 + lam if k in prev_cut else 1.0)
            return c / (len(ch) - 1)
        heap = []; ver = {}
        for a in desc:
            c = cost(a)
            if c is not None:
                ver[a] = 0; heap.append((c, 0, a))
        heapq.heapify(heap)
        while len(nodes) > nmax and heap:
            c, v, a = heapq.heappop(heap)
            if ver.get(a) != v or a not in desc:
                continue
            ch = desc.pop(a)
            tot = sum(nodes.pop(k) for k in ch); nodes[a] = tot
            for k in ch:
                for b in anc(k):
                    if b in desc and b != a:
                        desc[b].discard(k)
                desc.pop(k, None)
            for b in anc(a):
                desc.setdefault(b, set()).add(a)
                c2 = cost(b); ver[b] = ver.get(b, 0) + 1
                if c2 is not None:
                    heapq.heappush(heap, (c2, ver[b], b))
        return set(nodes)

    def map_to_cut(self, pix, cut):
        """per-pixel index into the cut list (deepest cut node containing the pixel)."""
        cut_list = sorted(cut)
        pos = {k: i for i, k in enumerate(cut_list)}
        out = np.full(len(pix), -1, np.int32)
        for d in range(B, -1, -1):
            ks = [(c, pos[(dd, c)]) for (dd, c) in cut_list if dd == d]
            if not ks:
                continue
            lut = np.full(8 ** d, -1, np.int32)
            lut[np.array([k for k, _ in ks])] = np.array([i for _, i in ks])
            cd = _code(pix, d)
            m = (out < 0)
            out[m] = lut[cd[m]]
        out[out < 0] = 0
        pal = np.array([self.cen[d][c] for d, c in cut_list], np.uint8)
        return out, pal


def _parent(d, c):
    r = c >> (2 * d); g = (c >> d) & ((1 << d) - 1); b = c & ((1 << d) - 1)
    pd = d - 1
    return (pd, ((r >> 1) << (2 * pd)) | ((g >> 1) << pd) | (b >> 1))


def encode_st_gif_octree(frames, durations_ms=33, quality=75, oct=None, progress_callback=None, timing="source"):
    """Returns (gif_bytes, elapsed_ms). `timing` works as in encode_st_gif ("source" or "uniform")."""
    cfg = dict(OCT); cfg.update(oct or {})
    t0 = time.perf_counter()
    T = len(frames); H, W, _ = frames[0].shape
    if isinstance(durations_ms, int):
        durations_ms = [durations_ms] * T
    if timing == "uniform":
        durations_ms = [sum(durations_ms) / T] * T
    elif timing != "source":
        raise ValueError(f"timing must be 'source' or 'uniform', got {timing!r}")
    frames, durations_ms = resample_to_gif_rate(frames, list(durations_ms))
    T = len(frames)
    delays_cs = frame_delays_cs(durations_ms)
    if progress_callback:
        progress_callback(0.05, "1/4 노이즈 안정화 중...")
    p = map_quality_to_st_gif_params(quality, estimate_game_capture_noise_sigma(frames))
    keep_tol, gain_min, lzw_tol, dither = p["voronoi_keep_tol"], p["voronoi_gain_min"], p["lzw_run_tol"], p["dither_str"]
    stab, motion = stabilize_pure_u8_fast(frames, noise_sigma=p["eff_sigma"], anisotropic_smooth=True)
    if not cfg.get("stab", True):
        stab = [f.copy() for f in frames]
        motion = [np.ones(frames[0].shape[:2], bool)] + [max_channel_u8(cv2.absdiff(frames[t], frames[t - 1])) > 3 for t in range(1, len(frames))]
    palette = lut3d = None
    if cfg["keep_est"] == "v3":
        palette, lut3d = build_motion_weighted_palette_and_lut(stab, motion, num_colors=p["num_colors"])
    bayer = np.tile(BAYER_4X4, (H // 4 + 1, W // 4 + 1))[:H, :W]
    if progress_callback:
        progress_callback(0.25, "2/4 클립 전체 옥트리 코드북 생성 중...")
    oc = OctCut(stab, motion, cfg["leaves"], cfg["motion_w"])

    canvas = np.zeros((H, W, 3), np.uint8)
    subframes = []; prev_cut = set(); prev_tree = prev_pal = None
    stats = {"colors": []}
    for t in range(T):
        f = stab[t]
        delay_cs = delays_cs[t]
        if progress_callback and t % max(1, T // 10) == 0:
            progress_callback(0.30 + 0.65 * t / T, f"3/4 프레임별 팔레트 절단 및 델타 인코딩 중 ({t}/{T})...")
        if t == 0:
            Wm = np.ones((H, W), bool)
        else:
            drift = max_channel_u8(cv2.absdiff(f, canvas))
            active = motion[t] | (drift > max(14, keep_tol * 2))
            Wm = np.zeros((H, W), bool)
            bb = fast_bounding_box(active)
            if bb is not None:
                x0, y0, x1, y1 = bb
                tgt = f[y0:y1, x0:x1]; mot = active[y0:y1, x0:x1]; can = canvas[y0:y1, x0:x1]
                if cfg["keep_est"] == "v3":
                    nidx = quantize_frame_with_locked_bayer(tgt, lut3d, palette, bayer[y0:y1, x0:x1], dither)
                    nrgb = palette[nidx]
                else:
                    _, ii = prev_tree.query(tgt.reshape(-1, 3).astype(np.float32) * W8, k=1)
                    nrgb = prev_pal[ii].reshape(tgt.shape)
                e_old = max_channel_u8(cv2.absdiff(tgt, can)); e_new = max_channel_u8(cv2.absdiff(tgt, nrgb))
                keep = (~mot) | np.all(nrgb == can, axis=2) | (e_old <= keep_tol) | \
                       (e_old.astype(np.int16) - e_new.astype(np.int16) <= gain_min)
                if not cfg.get("keep", True):
                    keep = ~mot
                upd = ~keep
                nb = cv2.boxFilter(upd.astype(np.uint8), -1, (3, 3), normalize=False)
                keep |= upd & (nb <= 2) & (e_old <= keep_tol * 2 + 2); upd = ~keep
                if upd.shape[1] >= 4:
                    keep[:, 1:-1] |= upd[:, 1:-1] & keep[:, :-2] & keep[:, 2:] & (e_old[:, 1:-1] <= keep_tol * 2 + 2)
                    upd = ~keep
                    iso2 = (upd[:, 1:-2] & upd[:, 2:-1] & keep[:, :-3] & keep[:, 3:] &
                            (e_old[:, 1:-2] <= keep_tol * 2) & (e_old[:, 2:-1] <= keep_tol * 2))
                    keep[:, 1:-2] |= iso2; keep[:, 2:-1] |= iso2; upd = ~keep
                g = cfg.get("grow", 0)
                if g and upd.any():
                    # grow the update region into touching pixels that are visibly off (e_old > grow_tol),
                    # so a connected area is refreshed in the same frame instead of row by row
                    gtol = cfg.get("grow_tol", max(2, keep_tol // 2))
                    cand = mot & (e_old > gtol)
                    kern = np.ones((3, 1), np.uint8) if cfg.get("grow_dir", "v") == "v" else np.ones((3, 3), np.uint8)
                    for _ in range(g):
                        nxt = upd | (cv2.dilate(upd.astype(np.uint8), kern).astype(bool) & cand)
                        if nxt.sum() == upd.sum():
                            break
                        upd = nxt
                Wm[y0:y1, x0:x1] = upd
            if not Wm.any():
                subframes[-1]["delay_cs"] += delay_cs
                continue
        src = f[Wm]
        cut = oc.cut_global(src, prev_cut, cfg["lam"]) if cfg["cut"] == "global" else oc.cut_for(src, None, prev_cut, cfg["lam"])
        pal = np.array([oc.cen[d][c] for d, c in sorted(cut)], np.uint8)
        tree = cKDTree(pal.astype(np.float32) * W8)
        _, li = tree.query(src.astype(np.float32) * W8, k=1)
        if dither > 0 and cfg["dither"]:
            q = pal[li].astype(np.int16)
            qerr = np.abs(q - src.astype(np.int16)).max(1)
            off = (bayer[Wm] * dither).astype(np.float32)[:, None]
            _, ld = tree.query(np.clip(src.astype(np.float32) + off, 0, 255) * W8, k=1)
            li = np.where(qerr > 7, ld, li)
        if prev_cut:
            stats.setdefault("jac", []).append(len(cut & prev_cut) / max(1, len(cut | prev_cut)))
        prev_cut = cut; prev_tree = tree; prev_pal = pal
        stats["colors"].append(len(pal))
        idx = np.full((H, W), 255, np.uint8); idx[Wm] = li.astype(np.uint8)
        lpal = np.zeros((256, 3), np.uint8); lpal[:len(pal)] = pal
        bb2 = fast_bounding_box(Wm)
        rx0, ry0, rx1, ry1 = bb2
        raw = idx[ry0:ry1, rx0:rx1]
        co = coalesce_lzw_horizontal_runs(raw, f[ry0:ry1, rx0:rx1], lpal, max_rgb_tol=lzw_tol) if cfg.get("coalesce", True) else raw
        wm = Wm[ry0:ry1, rx0:rx1]
        co = np.where(wm & (co != 255), co, raw); co = np.where(wm, co, 255).astype(np.uint8)
        idx[ry0:ry1, rx0:rx1] = co
        canvas[Wm] = lpal[idx[Wm]]
        subframes.append({"x": rx0, "y": ry0, "w": rx1 - rx0, "h": ry1 - ry0, "indices": co, "delay_cs": delay_cs,
                          "transparent": t > 0, "dispose": 1, "palette": lpal, "n_colors": len(pal)})
    if progress_callback:
        progress_callback(0.97, "4/4 GIF89a 조립 중...")
    gif = assemble_gif89a_lct(W, H, palette, subframes, loop_count=0)   # palette None -> no global table
    encode_st_gif_octree.last_stats = {"mean_colors": float(np.mean(stats["colors"])), "frames": len(subframes), "cut_jaccard": float(np.mean(stats.get("jac", [1.0])))}
    return gif, (time.perf_counter() - t0) * 1000.0
