"""
VMAF (v0.6.1 and v0.6.1 NEG) for ST-GIF, gifski and FFmpeg outputs.
Re-encodes each setting (encoders are deterministic; byte size is checked against results.jsonl),
decodes + aligns to the source timeline exactly as rd_bench.evaluate does, and runs Netflix vmaf CLI on yuv444p y4m.
"""
import os, sys, json, glob, shutil, subprocess, tempfile
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rd_bench as R
from st_studio.st_gif_codec import encode_st_gif

VMAF = "/home/claude/vmaf/libvmaf/build/tools/vmaf"
OUT = "vmaf.jsonl"
CAMBI_OUT = "cambi.jsonl"  # CAMBI back-filled for rows whose VMAF was measured before CAMBI was added


def write_y4m(frames, path):
    H, W, _ = frames[0].shape
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", "30", "-i", "pipe:0", "-pix_fmt", "yuv444p", "-strict", "-1", path]
    subprocess.run(cmd, input=b"".join(np.ascontiguousarray(f).tobytes() for f in frames), check=True, capture_output=True)


def run_vmaf(ref, dist, js, need_vmaf=True):
    """VMAF (v0.6.1 + NEG) and CAMBI (libvmaf defaults, full_ref) in one pass; CAMBI only if need_vmaf is False."""
    cmd = [VMAF, "-r", ref, "-d", dist, "--threads", "1", "--json", "-o", js, "-q", "--feature", "cambi=full_ref=true"]
    if need_vmaf:
        cmd += ["--model", "path=/home/claude/vmaf/model/vmaf_v0.6.1.json:name=vmaf",
                "--model", "path=/home/claude/vmaf/model/vmaf_v0.6.1neg.json:name=vmaf_neg"]
    else:
        cmd += ["-n"]
    subprocess.run(cmd, check=True, capture_output=True)
    p = json.load(open(js))["pooled_metrics"]
    out = {"cambi": p["cambi"]["mean"], "cambi_source": p["cambi_source"]["mean"],
           "cambi_full_reference": p["cambi_full_reference"]["mean"]}
    if need_vmaf:
        out.update({"vmaf": p["vmaf"]["mean"], "vmaf_hmean": p["vmaf"]["harmonic_mean"], "vmaf_min": p["vmaf"]["min"],
                    "vmaf_neg": p["vmaf_neg"]["mean"]})
    return out


def main(k, n):
    recorded = {}
    for l in open("results.jsonl"):
        r = json.loads(l); recorded[(r["clip"], r["enc"], r["param"])] = r["bytes"]
    done = set(); has_cambi = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            r = json.loads(l); done.add((r["clip"], r["enc"], r["param"]))
            if "cambi" in r:
                has_cambi.add((r["clip"], r["enc"], r["param"]))
    if os.path.exists(CAMBI_OUT):
        for l in open(CAMBI_OUT):
            r = json.loads(l); has_cambi.add((r["clip"], r["enc"], r["param"]))
    clips = sorted(glob.glob(os.path.join(R.CLIP_DIR, "*.webp")), key=os.path.getsize)[k::n]
    for c in clips:
        name = os.path.basename(c)
        frames, durs = R.load(c)
        T = len(frames); fps = 1000.0 / max(10.0, float(np.mean(durs)))
        cfr = [int(round(1000.0 / fps))] * T
        tmp = tempfile.mkdtemp(dir="/home/claude/bench/tmp")
        ref = os.path.join(tmp, "ref.y4m"); write_y4m(frames, ref)
        jobs = [("ffmpeg_sierra2_4a", 0)] + [("gifski", q) for q in R.GIFSKI_Q] + [("st_gif", q) for q in R.ST_Q]
        png_dir = None
        for enc, p in jobs:
            if (name, enc, p) in has_cambi:
                continue
            need_vmaf = (name, enc, p) not in done
            if enc == "ffmpeg_sierra2_4a":
                b, _ = R.ffmpeg_gif(frames, durs, "sierra2_4a")
            elif enc == "gifski":
                if png_dir is None:
                    png_dir = os.path.join(tmp, "png"); os.makedirs(png_dir)
                    for i, f in enumerate(frames):
                        Image.fromarray(f).save(os.path.join(png_dir, f"{i:05d}.png"), compress_level=1)
                b, _ = R.gifski(png_dir, T, frames[0].shape[1], fps, p)
            else:
                b, _ = encode_st_gif(frames, durs, quality=p)
            dec_f, dec_d = R.decode(b)
            al = R.align(dec_f, dec_d, durs if enc == "st_gif" else cfr)
            dist = os.path.join(tmp, "dist.y4m"); write_y4m(al, dist)
            v = run_vmaf(ref, dist, os.path.join(tmp, "v.json"), need_vmaf)
            rec = {"clip": name, "enc": enc, "param": p, "bytes": len(b),
                   "bytes_match": recorded.get((name, enc, p)) == len(b)}
            rec.update(v)
            with open(OUT if need_vmaf else CAMBI_OUT, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"{name[:28]:28s} {enc:18s} {p:>3} {len(b)/1024:9.1f}KB vmaf {v.get('vmaf', float('nan')):6.2f} cambi {v['cambi']:.3f} (src {v['cambi_source']:.3f}) match={rec['bytes_match']}", flush=True)
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]))
