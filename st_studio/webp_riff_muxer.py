"""
Low-level RIFF WEBP Animated Bitstream Parser & Custom ANMF Muxer.
Allows full byte-level inspection and custom construction of VP8X, ANIM, and ANMF chunks.
"""

import io
import struct
from PIL import Image
import numpy as np


def write_uint24_le(val: int) -> bytes:
    return struct.pack("<I", val)[:3]


def read_uint24_le(b: bytes) -> int:
    return struct.unpack("<I", b + b"\x00")[0]


def extract_single_frame_bitstream(webp_single_bytes: bytes) -> tuple[bytes, bool]:
    if webp_single_bytes[:4] != b"RIFF" or webp_single_bytes[8:12] != b"WEBP":
        raise ValueError("Invalid single-frame WebP")

    pos = 12
    n = len(webp_single_bytes)
    out = bytearray()
    has_alpha = False

    while pos + 8 <= n:
        fourcc = webp_single_bytes[pos : pos + 4]
        sz = struct.unpack("<I", webp_single_bytes[pos + 4 : pos + 8])[0]
        chunk_total = 8 + sz + (sz & 1)
        if fourcc == b"VP8X":
            flags = webp_single_bytes[pos + 8]
            if flags & 0x10:
                has_alpha = True
        elif fourcc in (b"ALPH", b"VP8 ", b"VP8L"):
            if fourcc == b"ALPH":
                has_alpha = True
            elif fourcc == b"VP8L" and sz >= 5:
                b4 = webp_single_bytes[pos + 8 + 4]
                if b4 & 0x10:
                    has_alpha = True
            out.extend(webp_single_bytes[pos : pos + chunk_total])
        pos += chunk_total

    return bytes(out), has_alpha


def encode_subframe_payload(
    sub_img: np.ndarray,
    lossless: bool = False,
    quality: int = 80,
    method: int = 4,
    exact: bool = False,
) -> tuple[bytes, bool]:
    mode = "RGBA" if sub_img.shape[2] == 4 else "RGB"
    pil_im = Image.fromarray(sub_img, mode=mode)
    buf = io.BytesIO()
    pil_im.save(
        buf,
        format="WEBP",
        lossless=lossless,
        quality=quality,
        method=method,
        exact=exact,
    )
    return extract_single_frame_bitstream(buf.getvalue())


def build_anmf_chunk(
    x: int,
    y: int,
    w: int,
    h: int,
    duration_ms: int,
    no_blend: bool,
    dispose_bg: bool,
    frame_payload: bytes,
) -> bytes:
    assert x % 2 == 0 and y % 2 == 0, f"ANMF x ({x}) and y ({y}) must be even!"
    assert w >= 1 and h >= 1

    flags = ((1 if no_blend else 0) << 1) | (1 if dispose_bg else 0)
    anmf_header = (
        write_uint24_le(x // 2)
        + write_uint24_le(y // 2)
        + write_uint24_le(w - 1)
        + write_uint24_le(h - 1)
        + write_uint24_le(duration_ms)
        + struct.pack("<B", flags)
    )
    body = anmf_header + frame_payload
    sz = len(body)
    pad = b"\x00" if (sz & 1) else b""
    return b"ANMF" + struct.pack("<I", sz) + body + pad


def assemble_animated_webp(
    canvas_w: int,
    canvas_h: int,
    anmf_chunks: list[bytes],
    has_alpha: bool = True,
    bg_color_bgra: tuple[int, int, int, int] = (0, 0, 0, 0),
    loop_count: int = 0,
) -> bytes:
    vp8x_flags = 0x02 | (0x10 if has_alpha else 0x00)
    vp8x_payload = (
        struct.pack("<B", vp8x_flags)
        + b"\x00\x00\x00"
        + write_uint24_le(canvas_w - 1)
        + write_uint24_le(canvas_h - 1)
    )
    vp8x_chunk = b"VP8X" + struct.pack("<I", 10) + vp8x_payload

    anim_payload = struct.pack("<BBBBH", *bg_color_bgra, loop_count)
    anim_chunk = b"ANIM" + struct.pack("<I", 6) + anim_payload

    riff_body = b"WEBP" + vp8x_chunk + anim_chunk + b"".join(anmf_chunks)
    return b"RIFF" + struct.pack("<I", len(riff_body)) + riff_body
