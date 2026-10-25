"""
Low-level GIF89a Bitstream Assembler & LZW Sub-frame Extractor.
Uses a 256-entry strictly unique bijection palette during single-frame C LZW extraction
and disables interlacing so Pillow NEVER deduplicates or scrambles palette indices 0..255.
"""

import io
import struct
import numpy as np
from PIL import Image

_BIJECTION_PALETTE_FLAT = []
for _i in range(256):
    _BIJECTION_PALETTE_FLAT.extend([_i, (_i * 73 + 19) & 0xFF, (_i * 151 + 97) & 0xFF])


def extract_gif_lzw_image_data(p_subframe: np.ndarray) -> bytes:
    """
    Encodes a 2D uint8 palette-indexed array (H, W) into a single-frame GIF using Pillow's C LZW encoder,
    and extracts the raw LZW Image Data bytes (LZW minimum code size byte + data sub-blocks + 0x00 terminator).
    """
    im = Image.fromarray(p_subframe)
    im.putpalette(_BIJECTION_PALETTE_FLAT)
    buf = io.BytesIO()
    im.save(buf, format="GIF", optimize=False, interlace=False)
    raw = buf.getvalue()

    flags = raw[10]
    pos = 13
    if flags & 0x80:
        gct_size = 3 * (1 << ((flags & 0x07) + 1))
        pos += gct_size

    n = len(raw)
    while pos < n:
        block_type = raw[pos]
        if block_type == 0x2C:
            lct_flags = raw[pos + 9]
            pos += 10
            if lct_flags & 0x80:
                lct_size = 3 * (1 << ((lct_flags & 0x07) + 1))
                pos += lct_size
            lzw_start = pos
            pos += 1
            while pos < n and raw[pos] != 0x00:
                sub_len = raw[pos]
                pos += 1 + sub_len
            pos += 1
            return raw[lzw_start:pos]
        elif block_type == 0x21:
            pos += 2
            while pos < n and raw[pos] != 0x00:
                pos += 1 + raw[pos]
            pos += 1
        elif block_type == 0x3B:
            break
        else:
            raise ValueError(f"Unexpected GIF block byte: 0x{block_type:02X} at pos {pos}")

    raise RuntimeError("Failed to find 0x2C Image Descriptor in single-frame GIF")


def assemble_gif89a(
    canvas_w: int,
    canvas_h: int,
    palette_rgb: np.ndarray,
    subframes: list[dict],
    loop_count: int = 0,
) -> bytes:
    """
    Assembles a complete, standard-compliant GIF89a animated file.
    """
    assert palette_rgb.shape == (256, 3) and palette_rgb.dtype == np.uint8
    palette_bytes = palette_rgb.tobytes()

    out = bytearray()

    # 1. Header + Logical Screen Descriptor (Global Color Table = 256 entries)
    out.extend(b"GIF89a")
    out.extend(struct.pack("<HHBBB", canvas_w, canvas_h, 0xF7, 255, 0))

    # 2. Global Color Table (768 bytes)
    out.extend(palette_bytes)

    # 3. Netscape 2.0 Application Extension for Infinite Looping
    out.extend(b"\x21\xFF\x0BNETSCAPE2.0\x03\x01")
    out.extend(struct.pack("<H", loop_count))
    out.extend(b"\x00")

    # 4. Frames (Graphic Control Extension + Image Descriptor + LZW Data)
    for sf in subframes:
        x, y, w, h = sf["x"], sf["y"], sf["w"], sf["h"]
        delay_cs = max(2, int(sf["delay_cs"]))
        trans_flag = 1 if sf.get("transparent", True) else 0
        dispose = sf.get("dispose", 1)
        trans_idx = sf.get("transparent_index", 255)

        gce_packed = ((dispose & 0x07) << 2) | trans_flag
        out.extend(struct.pack("<BBBBHB", 0x21, 0xF9, 0x04, gce_packed, delay_cs, trans_idx))
        out.extend(b"\x00")

        out.extend(struct.pack("<BHHHHB", 0x2C, x, y, w, h, 0x00))

        lzw_data = extract_gif_lzw_image_data(sf["indices"])
        out.extend(lzw_data)

    # 5. GIF Trailer
    out.extend(b"\x3B")
    return bytes(out)
