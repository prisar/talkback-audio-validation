from __future__ import annotations

import re
from pathlib import Path

from .comparison import VisualResult
from .parsing import FieldType


class OcrUnavailable(RuntimeError):
    pass


def parse_displayed(text: str, field_type: FieldType):
    """Turn a rendered string into a typed value. No model involved."""
    if text is None:
        return None
    raw = text.strip()
    if not raw:
        return None
    if field_type is FieldType.PERCENTAGE:
        match = re.search(r"(\d{1,3})\s*%", raw)
        if not match:
            match = re.fullmatch(r"\s*(\d{1,3})\s*", raw)
        if not match:
            return None
        value = int(match.group(1))
        return value if 0 <= value <= 100 else None
    if field_type is FieldType.SIGNED_LEVEL:
        match = re.search(r"-?\d+", raw)
        return int(match.group()) if match else None
    if field_type is FieldType.ENUM_STATE:
        return raw.lower()
    return raw


def crop_region(screenshot: str | Path, bounds, out_path: str | Path) -> Path:
    """Crop the value region and save it. Shared by the OCR and the
    screenshot-to-model reading paths so neither duplicates the cropping."""
    from PIL import Image

    image = Image.open(screenshot)
    x1, y1, x2, y2 = bounds
    pad = 6
    box = (
        max(0, x1 - pad),
        max(0, y1 - pad),
        min(image.width, x2 + pad),
        min(image.height, y2 + pad),
    )
    crop = image.crop(box)
    crop = crop.resize((crop.width * 3, crop.height * 3))
    crop.save(out_path)
    return Path(out_path)


def crop_and_ocr(screenshot: str | Path, bounds, out_path: str | Path | None = None) -> str:
    """Crop the value region and OCR it. Raises OcrUnavailable if tesseract is absent."""
    try:
        import pytesseract
    except ImportError as exc:
        raise OcrUnavailable(str(exc)) from exc

    crop_path = Path(out_path) if out_path else Path(screenshot).with_suffix(".crop.png")
    crop = crop_region(screenshot, bounds, crop_path)
    try:
        from PIL import Image

        return pytesseract.image_to_string(Image.open(crop), config="--psm 7").strip()
    except Exception as exc:
        raise OcrUnavailable(str(exc)) from exc


def build_visual_result(
    field_type: FieldType,
    text_node: str | None = None,
    ocr_text: str | None = None,
    ocr_error: str | None = None,
    dumpsys_value=None,
) -> VisualResult:
    """Resolve the on-screen value from independent channels.

    OCR and the rendered text node are peers. dumpsys is corroboration and is
    never promoted to reference.
    """
    channels: dict = {}
    references: dict = {}

    if text_node is not None:
        value = parse_displayed(text_node, field_type)
        channels["text_node"] = {"raw": text_node, "value": value}
        if value is not None:
            references["text_node"] = value

    if ocr_error:
        channels["ocr"] = {"raw": None, "value": None, "error": ocr_error}
    elif ocr_text is not None:
        value = parse_displayed(ocr_text, field_type)
        channels["ocr"] = {"raw": ocr_text, "value": value}
        if value is not None:
            references["ocr"] = value

    if dumpsys_value is not None:
        channels["dumpsys"] = {"raw": dumpsys_value, "value": dumpsys_value}

    if not references:
        return VisualResult(
            value=None,
            channels=channels,
            readable=False,
            note="no reference channel produced a value",
        )

    distinct = {v for v in references.values()}
    if len(distinct) > 1:
        return VisualResult(
            value=None,
            channels=channels,
            readable=True,
            disagreement=True,
            note=f"reference channels disagree: {references}",
        )

    value = next(iter(distinct))
    note = ""
    if dumpsys_value is not None and dumpsys_value != value:
        note = (
            f"dumpsys reports {dumpsys_value} while the screen shows {value}; "
            "recorded as diagnostic signal, not an error"
        )
    return VisualResult(value=value, channels=channels, readable=True, note=note)
