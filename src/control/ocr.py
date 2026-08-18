"""OCR for scanned documents — charter §5.5.

    "OCR with Arabic support and a **confidence floor**. Below it:
     `UNREADABLE — MANUAL REVIEW REQUIRED`, not evaluated, not posted.
     Never post an OCR figure below the floor. A wrong number in a
     register is worse than no number."

The Phase 0 scan is why this exists. 362 legal documents produced
**zero** guarantee expiries, LD rates, notice periods or
defects-liability dates — not because there are none, but because 47%
of them are photographs of text, rising to 81% for supplier legal
documents. §2.2 calls a forfeited claim window the most expensive
failure in this charter, and the windows were sitting in files nothing
could read.

Three rules, and the first two are the ones that make this safe:

**The floor is enforced here, not by the caller.** Below-floor text is
never returned as text. It comes back as a refusal with the measured
confidence attached, so a caller cannot accidentally treat a guess as
a reading.

**The floor is never lowered by learning** (§14.4). The system gets
better at reading; it does not get more willing to guess.

**A missing engine is reported, never worked around.** No silent
fallback to a lower-quality path, and no pretending a document had no
terms when the truth is that nothing looked at it.
"""

from dataclasses import dataclass
from pathlib import Path

# §5.5 gives no number, so this is a choice and it is deliberately
# strict: on a scanned Arabic contract, a permissive floor produces
# plausible dates that are wrong, and a wrong date in a class 2
# register alerts confidently on the wrong day. High floor means more
# UNREADABLE, which is a visible gap rather than a false record.
DEFAULT_FLOOR = 80.0
DEFAULT_LANGUAGES = ("ara", "eng")

# Rendering resolution. 300dpi is the usual floor for OCR on documents;
# below it Arabic diacritics and small print degrade badly.
DEFAULT_DPI = 300


@dataclass
class OcrResult:
    path: str
    text: str = ""
    confidence: float | None = None
    floor: float = DEFAULT_FLOOR
    accepted: bool = False
    reason: str = ""
    pages: int = 0
    engine: str = ""
    # D-14: for a client-confidential document the OCR text is dropped
    # at capture. Only the confidence and the reference survive.
    text_redacted: bool = False

    @property
    def verdict(self) -> str:
        if self.accepted:
            return "OCR_ACCEPTED"
        if self.confidence is not None:
            return "UNREADABLE — MANUAL REVIEW REQUIRED"
        return "NOT ATTEMPTED"


@dataclass
class OcrSettings:
    enabled: bool = False
    floor: float = DEFAULT_FLOOR
    languages: tuple = DEFAULT_LANGUAGES
    dpi: int = DEFAULT_DPI
    max_pages: int = 20

    @classmethod
    def from_config(cls, config: dict | None) -> "OcrSettings":
        data = (config or {}).get("ocr") or config or {}
        languages = data.get("languages") or list(DEFAULT_LANGUAGES)
        floor = float(data.get("confidence_floor", DEFAULT_FLOOR))
        return cls(
            enabled=bool(data.get("enabled", False)),
            floor=floor,
            languages=tuple(str(x) for x in languages),
            dpi=int(data.get("dpi", DEFAULT_DPI)),
            max_pages=int(data.get("max_pages", 20)),
        )


# ---- engine availability ---------------------------------------------

def engine_status() -> dict:
    """What is installed, and what each missing piece costs.

    Returned rather than raised: a machine without OCR should still run
    Phase 0 and report the gap, not halt.
    """
    status = {"ocr": False, "pdf_render": False, "languages": [], "notes": []}

    try:
        import pytesseract

        status["ocr"] = True
        try:
            status["languages"] = list(pytesseract.get_languages(config=""))
        except Exception:
            status["notes"].append(
                "tesseract is installed but its language list could not be "
                "read — Arabic support is unconfirmed")
    except Exception:
        status["notes"].append(
            "pytesseract not available. Install the Tesseract engine plus "
            "the Arabic language data, then: pip install pytesseract pillow")

    try:
        import fitz  # PyMuPDF

        _ = fitz
        status["pdf_render"] = True
    except Exception:
        status["notes"].append(
            "PyMuPDF not available, so scanned PDFs cannot be rendered for "
            "OCR: pip install pymupdf")

    if status["ocr"] and "ara" not in status["languages"]:
        status["notes"].append(
            "Arabic language data ('ara') is NOT installed. Arabic contracts "
            "would be read as noise and rejected by the floor — which is the "
            "safe direction, but they stay unreadable (§5.5)")
    return status


# ---- reading ----------------------------------------------------------

def _mean_confidence(data: dict) -> float | None:
    """Mean confidence over words tesseract actually recognised.

    Tesseract emits -1 for boxes it made no attempt at, and empty
    strings for whitespace. Averaging those in would drag a good
    reading below the floor and a bad one above it, depending only on
    layout.
    """
    confidences = []
    for value, word in zip(data.get("conf", []), data.get("text", [])):
        if not str(word).strip():
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number >= 0:
            confidences.append(number)
    if not confidences:
        return None
    return sum(confidences) / len(confidences)


def ocr_image(path: Path, settings: OcrSettings, *, reader=None) -> OcrResult:
    """OCR one image. `reader` is injectable so tests need no engine."""
    path = Path(path)
    result = OcrResult(path=str(path), floor=settings.floor, engine="tesseract")

    if reader is None:
        try:
            import pytesseract
            from PIL import Image
        except Exception as e:
            result.reason = (
                f"OCR engine not available ({e}). Nothing was read, and this "
                "document is reported unreadable rather than assumed empty.")
            return result

        def reader(image_path: str, languages: str):
            with Image.open(image_path) as image:
                return pytesseract.image_to_data(
                    image, lang=languages,
                    output_type=pytesseract.Output.DICT)

    try:
        data = reader(str(path), "+".join(settings.languages))
    except Exception as e:
        result.reason = f"OCR failed: {e}"
        return result

    result.pages = 1
    text = " ".join(w for w in data.get("text", []) if str(w).strip())
    confidence = _mean_confidence(data)
    result.confidence = confidence

    if confidence is None:
        result.reason = "no words recognised"
        return result
    if confidence < settings.floor:
        # The whole point. Below-floor text is not returned at all.
        result.reason = (
            f"mean confidence {confidence:.1f} is below the §5.5 floor of "
            f"{settings.floor:.1f} — UNREADABLE, not evaluated, not posted")
        return result

    result.text = text
    result.accepted = True
    return result


def ocr_pdf(path: Path, settings: OcrSettings, *, renderer=None,
            reader=None) -> OcrResult:
    """Rasterise a text-less PDF and OCR its pages.

    Page confidences are averaged weighted by recognised words, so one
    near-blank page cannot drag a readable contract below the floor,
    and one clean cover page cannot lift a bad scan above it.
    """
    path = Path(path)
    result = OcrResult(path=str(path), floor=settings.floor, engine="tesseract")

    if renderer is None:
        try:
            import fitz
        except Exception as e:
            result.reason = (
                f"PDF rendering not available ({e}). Scanned PDFs stay "
                "unreadable rather than being reported as empty.")
            return result

        def renderer(pdf_path: str, dpi: int, max_pages: int):
            images = []
            with fitz.open(pdf_path) as document:
                for index, page in enumerate(document):
                    if index >= max_pages:
                        break
                    pixmap = page.get_pixmap(dpi=dpi)
                    images.append(pixmap.tobytes("png"))
            return images

    try:
        images = renderer(str(path), settings.dpi, settings.max_pages)
    except Exception as e:
        result.reason = f"PDF rendering failed: {e}"
        return result

    if not images:
        result.reason = "no pages rendered"
        return result

    if reader is None:
        try:
            import io

            import pytesseract
            from PIL import Image
        except Exception as e:
            result.reason = f"OCR engine not available ({e})"
            return result

        def reader(image_bytes, languages: str):
            with Image.open(io.BytesIO(image_bytes)) as image:
                return pytesseract.image_to_data(
                    image, lang=languages,
                    output_type=pytesseract.Output.DICT)

    parts: list[str] = []
    weighted, total_words = 0.0, 0
    for image in images:
        try:
            data = reader(image, "+".join(settings.languages))
        except Exception as e:
            result.reason = f"OCR failed on a page: {e}"
            return result
        words = [w for w in data.get("text", []) if str(w).strip()]
        confidence = _mean_confidence(data)
        if confidence is None or not words:
            continue
        parts.append(" ".join(words))
        weighted += confidence * len(words)
        total_words += len(words)

    result.pages = len(images)
    if not total_words:
        result.reason = "no words recognised on any page"
        return result

    confidence = weighted / total_words
    result.confidence = confidence
    if confidence < settings.floor:
        result.reason = (
            f"mean confidence {confidence:.1f} is below the §5.5 floor of "
            f"{settings.floor:.1f} — UNREADABLE, not evaluated, not posted")
        return result

    result.text = "\n".join(parts)
    result.accepted = True
    return result


def read_scanned(path: Path, settings: OcrSettings, **injected) -> OcrResult:
    """Route by file type. The only entry point callers should use."""
    suffix = Path(path).suffix.lower()
    if not settings.enabled:
        return OcrResult(path=str(path), floor=settings.floor,
                         reason="OCR not enabled (§5.5) — document unread")
    if suffix == ".pdf":
        return ocr_pdf(path, settings, **injected)
    return ocr_image(
        path, settings,
        **{k: v for k, v in injected.items() if k == "reader"})


def summarise(results: list[OcrResult]) -> dict:
    """Counts for the Phase 0 limitations report.

    `below_floor` is reported separately from `failed` on purpose: one
    means the engine read it and the reading was not trustworthy, the
    other means nothing looked at it. Collapsing them would hide which
    problem the company actually has.
    """
    accepted = [r for r in results if r.accepted]
    below = [r for r in results if not r.accepted and r.confidence is not None]
    failed = [r for r in results if not r.accepted and r.confidence is None]
    confidences = [r.confidence for r in accepted if r.confidence is not None]
    return {
        "total": len(results),
        "accepted": len(accepted),
        "below_floor": len(below),
        "not_attempted_or_failed": len(failed),
        "mean_confidence_accepted": (
            sum(confidences) / len(confidences) if confidences else None),
    }
