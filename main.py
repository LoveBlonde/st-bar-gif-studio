"""
ST-BAR GIF Studio — Main Entry Point (GUI & CLI).
- Run without arguments (`python main.py`) to launch the Honeycam-style Studio GUI.
- Run with `--input` (`python main.py -i clip.webp -o out.gif -q 75`) for CLI batch conversion.
"""

import argparse
import os
import sys
import numpy as np
import cv2
from PIL import Image

from st_studio import encode_st_gif, encode_st_bar_webp


def load_sequence_cli(path: str, max_frames: int = 500):
    ext = os.path.splitext(path)[1].lower()
    frames, durs = [], []
    if ext in (".webp", ".gif", ".png", ".apng"):
        im = Image.open(path)
        try:
            while len(frames) < max_frames:
                durs.append(max(15, int(im.info.get("duration", 33))))
                frames.append(np.array(im.convert("RGB")))
                im.seek(im.tell() + 1)
        except EOFError:
            pass
    else:
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        dur = max(15, int(round(1000.0 / fps)))
        while len(frames) < max_frames:
            ret, bgr = cap.read()
            if not ret:
                break
            frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            durs.append(dur)
        cap.release()
    return frames, durs


def main():
    parser = argparse.ArgumentParser(
        description="ST-BAR GIF Studio: Spatio-Temporal LZW-RDO GIF & WebP Optimizer"
    )
    parser.add_argument("-i", "--input", help="Input video/animation file (.webp, .gif, .mp4, .webm)")
    parser.add_argument("-o", "--output", help="Output file path (.gif or .webp)")
    parser.add_argument("-q", "--quality", type=int, default=75, help="Compression quality slider (1..100, default: 75)")
    args = parser.parse_args()

    if not args.input:
        from st_studio.gui_app import launch_studio
        launch_studio()
        return

    if not os.path.isfile(args.input):
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    out_path = args.output or (os.path.splitext(args.input)[0] + f"_st_q{args.quality}.gif")
    out_ext = os.path.splitext(out_path)[1].lower()

    print(f"Loading '{args.input}'...")
    frames, durs = load_sequence_cli(args.input)
    print(f"Loaded {len(frames)} frames ({frames[0].shape[1]}x{frames[0].shape[0]}). Optimizing (quality={args.quality})...")

    if out_ext == ".webp":
        blob, ms = encode_st_bar_webp(frames, durs, quality=args.quality)
    else:
        blob, ms = encode_st_gif(frames, durs, quality=args.quality)

    with open(out_path, "wb") as f:
        f.write(blob)

    in_kb = os.path.getsize(args.input) / 1024.0
    out_kb = len(blob) / 1024.0
    print(f"Done in {ms/1000.0:.2f}s! Saved '{out_path}' ({out_kb:,.1f} KB vs input {in_kb:,.1f} KB)")


if __name__ == "__main__":
    main()
