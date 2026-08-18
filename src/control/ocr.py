"""OCR for scanned documents — charter §5.5.

Egyptian contracting paperwork is largely scanned, and §2.2's highest-value
dates — guarantee expiries, notice periods, LD terms — sit inside those
scans. Without OCR they are recorded as gaps forever.

THE FLOOR IS THE POINT. §5.5: below the confidence floor a document is
`UNREADABLE — MANUAL REVIEW REQUIRED`, not evaluated and not posted.
"A wrong number in a register is worse than no number." So this module
withholds text it is not confident in rather than returning a best
guess: `OcrResult.text` is None when the page mean falls below the
floor, and callers cannot post what they cannot read.

§14.4 forbids the learning engine from ever lowering the floor. Nothing
here reads a learned value; the floor arrives as an argument from the
caller and defaults to a constant.

Arabic is mandatory, not optional. UBCSIS documents mix Latin technical
terms into Arabic text (§4), so recognition runs `ara+eng` together.
An English-only engine pointed at an Arabic scan returns fluent
nonsense at plausible confidence — a fabrication where there was an
honest gap (§1.1). `available()` therefore reports unusable when the
Arabic language data is absent, rather than quietly degrading.

Processing is local. Nothing is passed to any model or external service
(§12.1.2), which is what makes this admissible for D-05 material if the
CEO ever extends that decision to cover OCR — it does not today.
"""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Tesseract reports per-word confidence on 0-100. 60 is deliberately
# conservative for mixed Arabic/Latin scans: it rejects the marginal
# page rather than admit a misread digit into a date field.
DEFAULT_CONFIDENCE_FLOOR = 60.0

LANGS = "ara+eng"

# Bound the work per document. A 200-page scanned contract would other-
# wise stall a whole-drive scan; the cap is recorded on the result so a
# truncated read is never mistaken for a complete one.
DEFAULT_MAX_PAGES = 40

# The UB-Mannheim installer's default location; a silent install does not
# put it on PATH.
_WINDOWS_DEFAULT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Rasterising at 300 dpi: below ~200 Arabic diacritics start to merge.
RENDER_DPI = 300


@dataclass
class OcrResult:
    """What OCR found, and how much of it is trustworthy.

    `text` is None when the document fell below the floor. That is not
    an error state — it is the §5.5 answer, and it must stay
    unpostable.
    """
    source: str
    text: str | None = None
    mean_confidence: float = 0.0
    words: int = 0
    pages_read: int = 0
    pages_total: int = 0
    below_floor: bool = False
    truncated: bool = False
    error: str = ""
    model: str = ""
    escalated: bool = False
    per_page_confidence: list = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.text is not None and not self.below_floor


def resolve_binary() -> str | None:
    """Locate tesseract without trusting PATH."""
    found = shutil.which("tesseract")
    if found:
        return found
    if Path(_WINDOWS_DEFAULT).is_file():
        return _WINDOWS_DEFAULT
    return None


def resolve_tessdata_model(model: str) -> str:
    """Directory for a named model set: 'fast' or 'best'.

    Measured on real UBCSIS scans, the fast models run about three times
    quicker at a few points lower confidence (72.6 vs 76.0 on the same
    contract, 1658 vs 1693 words). That trade is worth taking for the
    first pass over thousands of documents, but not for a document whose
    reading is marginal — see `ocr_document`'s escalation.
    """
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    directory = local / ("tessdata_fast" if model == "fast" else "tessdata")
    if (directory / "ara.traineddata").is_file():
        return str(directory)
    return resolve_tessdata()


def resolve_tessdata() -> str:
    """Locate the language directory without trusting TESSDATA_PREFIX.

    Language data installed under LOCALAPPDATA is invisible to any
    process that did not inherit that variable — a scheduled cycle, a
    service, a fresh shell. Relying on the environment would make
    Arabic support depend on how the process was started, which is a
    silent correctness problem rather than a loud one.
    """
    candidates = [
        os.environ.get("TESSDATA_PREFIX", ""),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "tessdata"),
        str(Path(_WINDOWS_DEFAULT).parent / "tessdata"),
    ]
    for candidate in candidates:
        if candidate and (Path(candidate) / "eng.traineddata").is_file():
            return candidate
    return ""


def available() -> tuple[bool, str]:
    """(usable, reason). Usable requires the Arabic data, per §5.5."""
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False, "pytesseract not installed"
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        return False, "pymupdf not installed (PDF rasterising)"

    binary = resolve_binary()
    if not binary:
        return False, "tesseract binary not found"

    languages = _languages(binary, resolve_tessdata())
    if "ara" not in languages:
        return False, (
            "Arabic language data missing — §5.5 requires Arabic support; "
            "running English-only over Arabic scans would fabricate text"
        )
    return True, f"tesseract with {', '.join(sorted(languages))}"


def _apply_tessdata(tessdata: str) -> None:
    """Point tesseract at the language directory via the environment.

    NOT via `--tessdata-dir` in pytesseract's config string: pytesseract
    splits that string on whitespace, so any path containing a space —
    "C:\\Users\\Lape Top Suez\\..." — arrives as several broken
    arguments and tesseract fails on every document. The environment
    variable carries spaces intact, and the subprocess inherits it.
    """
    if tessdata:
        os.environ["TESSDATA_PREFIX"] = tessdata


def _languages(binary: str, tessdata: str) -> set[str]:
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = binary
    _apply_tessdata(tessdata)
    try:
        return set(pytesseract.get_languages(config=""))
    except Exception:
        return set()


def _ocr_one_image(image, binary: str, tessdata: str) -> tuple[str, float, int]:
    """Text, mean confidence and word count for a single PIL image."""
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = binary
    _apply_tessdata(tessdata)
    data = pytesseract.image_to_data(
        image, lang=LANGS, config="",
        output_type=pytesseract.Output.DICT,
    )
    words, confidences = [], []
    for text, conf in zip(data.get("text", []), data.get("conf", [])):
        try:
            value = float(conf)
        except (TypeError, ValueError):
            continue
        # -1 marks a region with no recognised text; averaging it in
        # would drag every sparse page below the floor.
        if value < 0 or not str(text).strip():
            continue
        words.append(str(text))
        confidences.append(value)
    if not confidences:
        return "", 0.0, 0
    mean = sum(confidences) / len(confidences)
    return " ".join(words), mean, len(words)


# A fast-model reading this close above the floor is close enough to the
# line that the slower, more accurate model is worth the time.
ESCALATION_MARGIN = 8.0


def ocr_document(path: Path, *, floor: float = DEFAULT_CONFIDENCE_FLOOR,
                 max_pages: int = DEFAULT_MAX_PAGES,
                 model: str = "fast", escalate: bool = True) -> OcrResult:
    """OCR a scanned PDF or image. Never raises; failures are recorded.

    A per-item failure must not end a whole-drive scan (§1.1, §13.2), so
    every error path returns a result carrying its own reason.

    Two-tier by default: read with the fast models, and re-read with the
    accurate ones only when the fast result lands below the floor or
    within `ESCALATION_MARGIN` of it. The bulk of documents are read
    once at three times the speed, while the marginal ones — the only
    ones where the model choice can change the verdict — get the better
    reading. This raises coverage without touching the floor, which
    §14.4 forbids lowering.
    """
    first = _ocr_pass(path, floor=floor, max_pages=max_pages, model=model)
    if not escalate or model == "best":
        return first
    if first.error and "not installed" in first.error:
        return first
    marginal = first.below_floor or first.mean_confidence < floor + ESCALATION_MARGIN
    if not marginal:
        return first
    second = _ocr_pass(path, floor=floor, max_pages=max_pages, model="best")
    second.escalated = True
    # Keep whichever reading the floor actually accepts; if both fail,
    # the more accurate model's verdict is the one to record.
    if second.usable or not first.usable:
        return second
    return first


def _ocr_pass(path: Path, *, floor: float, max_pages: int,
              model: str) -> OcrResult:
    path = Path(path)
    result = OcrResult(source=str(path), model=model)

    usable, reason = available()
    if not usable:
        result.error = reason
        return result

    binary = resolve_binary() or ""
    tessdata = resolve_tessdata_model(model)

    try:
        if path.suffix.lower() == ".pdf":
            texts, confidences, words = _read_pdf(
                path, binary, tessdata, max_pages, result)
        else:
            texts, confidences, words = _read_image(path, binary, tessdata, result)
    except Exception as e:                       # unreadable, not fatal
        result.error = f"{type(e).__name__}: {str(e)[:120]}"
        return result

    result.words = words
    result.per_page_confidence = [round(c, 1) for c in confidences]
    if not confidences:
        result.error = result.error or "no text recognised"
        result.below_floor = True
        return result

    # Weight by nothing: a page is a page. A long confident page should
    # not license a short garbled one, because the garbled page is where
    # the misread date lives.
    result.mean_confidence = round(sum(confidences) / len(confidences), 1)
    if result.mean_confidence < floor:
        result.below_floor = True
        result.text = None                       # §5.5: withheld, not guessed
    else:
        result.text = "\n".join(texts)
    return result


def _read_pdf(path: Path, binary: str, tessdata: str, max_pages: int,
              result: OcrResult):
    import pymupdf
    from PIL import Image

    texts: list[str] = []
    confidences: list[float] = []
    words = 0
    zoom = RENDER_DPI / 72.0

    with pymupdf.open(path) as document:
        result.pages_total = document.page_count
        limit = min(document.page_count, max_pages)
        result.truncated = document.page_count > limit
        for index in range(limit):
            page = document.load_page(index)
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            image = Image.frombytes(
                "RGB", (pixmap.width, pixmap.height), pixmap.samples)
            text, mean, count = _ocr_one_image(image, binary, tessdata)
            result.pages_read += 1
            if count:
                texts.append(text)
                confidences.append(mean)
                words += count
    return texts, confidences, words


def _read_image(path: Path, binary: str, tessdata: str, result: OcrResult):
    from PIL import Image

    result.pages_total = 1
    with Image.open(path) as image:
        text, mean, count = _ocr_one_image(image.convert("RGB"), binary, tessdata)
    result.pages_read = 1
    if not count:
        return [], [], 0
    return [text], [mean], count
