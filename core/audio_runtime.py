"""Point pydub at the same bundled FFmpeg used by media preparation."""

import warnings

from imageio_ffmpeg import get_ffmpeg_exe

try:
    _ffmpeg = get_ffmpeg_exe()
except RuntimeError:
    _ffmpeg = None

# pydub checks only PATH while importing, before its converter can be assigned.
# Suppress that one misleading warning only when we have resolved a converter.
with warnings.catch_warnings():
    if _ffmpeg:
        warnings.filterwarnings(
            "ignore", message="Couldn't find ffmpeg or avconv.*",
            category=RuntimeWarning, module=r"pydub\.utils",
        )
    from pydub import AudioSegment

if _ffmpeg:
    AudioSegment.converter = _ffmpeg
