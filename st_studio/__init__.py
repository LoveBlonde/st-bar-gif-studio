"""
ST-BAR GIF Studio Core Package
Spatio-Temporal Block-Aligned Stabilization, LZW-RDO GIF89a & Animated WebP Compression Engine.
"""

from .st_gif_codec import encode_st_gif
from .st_bar_webp import encode_st_bar_webp

__all__ = ["encode_st_gif", "encode_st_bar_webp"]
