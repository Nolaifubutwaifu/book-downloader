"""Internet Archive (archive.org) adapter.

Archive.org exposes each text item through a clean JSON metadata API
(``/metadata/<identifier>``) that lists the item's files. Full-text books
carry a ``<identifier>_djvu.txt`` file (the OCR / full text), downloadable at
``/download/<identifier>/<file>``.

Given any archive.org URL — a details page, a download link, or a bare
identifier — this adapter resolves the identifier, reads the metadata, grabs
the djvu.txt, and splits it into chapters where chapter headings are
detectable (falling back to one chapter for the whole text).

Borrow-only ("access-restricted") items are under controlled lending, so their
text is not downloadable; the adapter reports that clearly instead of failing
obscurely.
"""

import json
import re
from urllib.parse import unquote, urlsplit

from ..book import Book, Chapter
from .base import Extractor

META_BASE = "https://archive.org/metadata"
DL_BASE = "https://archive.org/download"

# archive.org paths: /details/<id>, /download/<id>/..., /stream/<id>, /embed/<id>
ID_FROM_PATH = re.compile(r"^/(?:details|download|stream|embed|metadata)/([^/]+)", re.I)

# "CHAPTER IV", "CHAP. 3", "BOOK II", optionally with a title after it.
CHAPTER_HEADING = re.compile(
    r"^\s*(CHAPTER|CHAP\.?|BOOK|PART|CANTO|LETTER)\s+"
    r"([IVXLCDM]+|\d+)\b[.:]?\s*(.*)$",
    re.I,
)
# A lone "CHAPTER" / "BOOK" line (OCR often splits the number onto the next line)
BARE_HEADING = re.compile(r"^\s*(CHAPTER|CHAP\.?|BOOK|PART|CANTO|LETTER)\s*$", re.I)
NUMBER_ONLY = re.compile(r"^\s*([IVXLCDM]+|\d+)[.:]?\s*$", re.I)


class ArchiveOrgExtractor(Extractor):
    name = "Internet Archive (archive.org)"

    @staticmethod
    def matches(url):
        return "archive.org" in urlsplit(url).netloc.lower()

    def scrape(self, url, fetcher, progress):
        identifier = _identifier_from_url(url)
        if not identifier:
            raise RuntimeError("couldn't find an archive.org item id in that link")

        progress("Reading the item's metadata…", 0, 3)
        meta = json.loads(fetcher.get(f"{META_BASE}/{identifier}"))
        m = meta.get("metadata", {})
        if not m:
            raise RuntimeError(f"archive.org has no item called '{identifier}'")

        if str(m.get("access-restricted-item", "")).lower() == "true":
            raise RuntimeError(
                f"'{m.get('title', identifier)}' is a borrow-only (lending) item, "
                "so its full text isn't downloadable. Look for an open/public-domain "
                "copy of the same book on archive.org instead."
            )

        txt_file = _pick_text_file(meta.get("files", []))
        if not txt_file:
            raise RuntimeError(
                "this archive.org item has no full-text (djvu.txt) file - it may be "
                "images/audio/video rather than a readable book"
            )

        progress("Downloading the full text…", 1, 3)
        raw = fetcher.get(f"{DL_BASE}/{identifier}/{txt_file}")
        progress("Splitting into chapters…", 2, 3)

        title = _clean(m.get("title")) or identifier
        author = _format_creator(m.get("creator"))
        chapters = _parse_djvu_text(raw)
        if not chapters:
            raise RuntimeError("the item's text file came back empty")
        progress("Done", 3, 3)
        return Book(title=title, author=author, source_url=_details_url(identifier),
                    chapters=chapters)


def _identifier_from_url(url):
    parts = urlsplit(url)
    if "archive.org" not in parts.netloc.lower():
        # allow a bare identifier pasted on its own
        bare = url.strip().strip("/")
        return bare or None
    m = ID_FROM_PATH.match(parts.path)
    if m:
        return unquote(m.group(1))
    # e.g. https://archive.org/<identifier> with nothing else
    tail = parts.path.strip("/")
    return unquote(tail.split("/")[0]) if tail else None


def _details_url(identifier):
    return f"https://archive.org/details/{identifier}"


def _pick_text_file(files):
    """Return the best full-text filename, preferring the DjVuTXT OCR file."""
    djvu = [f for f in files if f.get("format") == "DjVuTXT"]
    if djvu:
        return djvu[0]["name"]
    txts = [f for f in files if f.get("name", "").lower().endswith("_djvu.txt")]
    if txts:
        return txts[0]["name"]
    plain = [f for f in files if f.get("name", "").lower().endswith(".txt")
             and "_meta" not in f["name"].lower()]
    return plain[0]["name"] if plain else None


def _clean(s):
    return re.sub(r"\s+", " ", s).strip() if s else ""


def _format_creator(creator):
    if not creator:
        return ""
    if isinstance(creator, list):
        creator = "; ".join(creator)
    # "Austen, Jane, 1775-1817, author" -> "Austen, Jane"
    creator = re.sub(r",\s*\d{4}(-\d{0,4})?.*$", "", creator)
    creator = re.sub(r",\s*(author|editor|translator|creator)\s*$", "", creator, flags=re.I)
    return _clean(creator)


def _normalize_headings(lines):
    """Merge OCR-split headings ('CHAPTER' / 'IV' on two lines) into one line."""
    out = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if BARE_HEADING.match(cur):
            # look ahead past blank lines for a lone number
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and NUMBER_ONLY.match(lines[j]):
                out.append(f"{cur.strip()} {lines[j].strip()}")
                i = j + 1
                continue
        out.append(cur)
        i += 1
    return out


def _parse_djvu_text(raw):
    raw = raw.replace("\r\n", "\n").replace("\x0c", "\n")
    # Drop the Unicode replacement char and stray control chars that OCR leaves
    # behind (they render as tofu boxes / missing glyphs in the PDF).
    raw = raw.replace("�", "")
    raw = re.sub(r"[\x00-\x08\x0b\x0e-\x1f]", "", raw)
    lines = _normalize_headings(raw.split("\n"))

    chapters = []
    current = Chapter(title="")
    para = []

    def flush_para():
        if para:
            text = re.sub(r"\s+", " ", " ".join(para)).strip()
            if text:
                current.blocks.append(text)
            para.clear()

    def flush_chapter():
        flush_para()
        if current.blocks:
            chapters.append(Chapter(title=current.title, blocks=list(current.blocks)))
        current.blocks.clear()

    for line in lines:
        stripped = line.strip()
        heading = CHAPTER_HEADING.match(stripped)
        if heading and len(stripped) < 80:
            flush_chapter()
            kind, num, rest = heading.group(1), heading.group(2), heading.group(3)
            label = f"{kind.title().rstrip('.')} {num.upper()}"
            if rest.strip():
                label += f" — {_clean(rest)}"
            current.title = label
        elif not stripped:
            flush_para()
        else:
            para.append(stripped)
    flush_chapter()

    # No detectable chapters (common for OCR scans): keep the whole text as one.
    if len(chapters) <= 1:
        blocks = [b for c in chapters for b in c.blocks] or []
        if not blocks:
            return []
        return [Chapter(title="Full text", blocks=blocks)]

    for i, c in enumerate(chapters, 1):
        if not c.title:
            c.title = "Front matter" if i == 1 else f"Part {i}"
    return chapters
