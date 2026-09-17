"""A font that prints Hindi, and the switch that makes it print Hindi correctly.

Glyphs are not enough. Devanagari is a shaped script: the vowel sign in "कि"
is written before the consonant it follows in speech, and "क्ष" is one
conjunct, not three characters. Without a shaping engine ReportLab lays the
characters out in storage order, so "जोखिम" prints as "जोखमि" and conjuncts
fall apart with a visible halant — readable to nobody, and on a consent form,
a form the patient cannot be said to have understood.

Measured on this server on 2026-09-13: ReportLab 4.2.5 printed broken Hindi
with or without uharfbuzz; ReportLab 5.0.1 with uharfbuzz and `shaping` on
prints it correctly in both FreeSans and Lohit Devanagari.
"""
from importlib.util import find_spec
from pathlib import Path
from typing import Dict, Optional, Tuple

from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

#: Shaping needs both the engine and a ReportLab that knows how to use it.
SHAPING: bool = find_spec("uharfbuzz") is not None and "shaping" in ParagraphStyle.defaults

#: Keyword arguments for canvas.drawString and friends. Empty on an old
#: ReportLab, whose draw calls reject a `shaping` argument outright.
SHAPE: Dict[str, bool] = {"shaping": True} if SHAPING else {}

_CANDIDATES = [
    # FreeSans has a real bold face; Lohit does not.
    ("/usr/share/fonts/truetype/freefont/FreeSans.ttf",
     "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
    ("/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
     "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf"),
]

_registered: Optional[Tuple[str, str]] = None


def devanagari_fonts() -> Tuple[str, str]:
    """Register once and return (regular, bold). Helvetica if no font is installed."""
    global _registered
    if _registered is not None:
        return _registered
    for regular, bold in _CANDIDATES:
        if not Path(regular).exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont("SatyaDeva", regular))
            pdfmetrics.registerFont(TTFont("SatyaDeva-Bold", bold if Path(bold).exists() else regular))
            pdfmetrics.registerFontFamily("SatyaDeva", normal="SatyaDeva", bold="SatyaDeva-Bold",
                                          italic="SatyaDeva", boldItalic="SatyaDeva-Bold")
        except Exception:  # noqa: BLE001 - try the next candidate
            continue
        _registered = ("SatyaDeva", "SatyaDeva-Bold")
        return _registered
    _registered = ("Helvetica", "Helvetica-Bold")
    return _registered


def can_print_hindi() -> bool:
    return SHAPING and devanagari_fonts()[0] != "Helvetica"
