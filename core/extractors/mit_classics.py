"""Internet Classics Archive (classics.mit.edu) adapter.

Each work's index page (e.g. /Homer/odyssey.html) is just a table of contents,
so the generic extractor finds no text on it. But every index links a
text-only version of the whole work (odyssey.mb.txt, antigone.pl.txt, ...)
with a consistent layout:

    Provided by The Internet Classics Archive. ...
    <blank>
    Title
    By Author
    Translated by X          (optional)
    ----------------------------------------------------------------------
    BOOK I                   (or ACT/SCENE/PART/CHAPTER...)
    <hard-wrapped paragraphs separated by blank lines>
    THE END
    ----------------------------------------------------------------------
    Copyright statement: ...

We fetch that file, unwrap the hard-wrapped paragraphs, and split chapters at
the section headings. If a work has no text-only version, we fall back to
crawling its section pages in order.
"""

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from ..book import Book, Chapter
from .base import Extractor

SEPARATOR = re.compile(r"^-{20,}\s*$")
HEADING = re.compile(
    r"^(BOOK|CHAPTER|PART|ACT|SCENE|SECTION|IDYLL|ELEGY|EPISTLE|SATIRE|EKLOGE|ECLOGUE)"
    r"\s+[IVXLCDM0-9]+[A-Z .:-]*$",
    re.I,
)
THE_END = re.compile(r"^\s*THE END\s*\.?\s*$", re.I)
# section pages look like odyssey.1.i.html / nicomachaen.3.iii.html
SECTION_HREF = re.compile(r"^(?P<slug>[\w-]+)\.(?P<num>\d+)\.[ivxlcdm0-9]+\.html$", re.I)


class MitClassicsExtractor(Extractor):
    name = "Internet Classics Archive (classics.mit.edu)"

    @staticmethod
    def matches(url):
        return "classics.mit.edu" in urlsplit(url).netloc

    def scrape(self, url, fetcher, progress):
        index_url = _normalize_to_index(url)
        progress("Reading the work's table of contents…", 0, 2)
        index_html = fetcher.get(index_url)
        soup = BeautifulSoup(index_html, "html.parser")

        txt_url = _find_text_version(soup, index_url)
        if txt_url:
            progress("Fetching the text-only version…", 1, 2)
            raw = fetcher.get(txt_url)
            book = _parse_plain_text(raw, source_url=index_url)
            progress("Done", 2, 2)
            return book
        return self._crawl_sections(index_url, soup, fetcher, progress)

    def _crawl_sections(self, index_url, soup, fetcher, progress):
        """Fallback for works without a text-only download."""
        title, author, translator = _index_metadata(soup)
        links = _section_links(soup, index_url)
        if not links:
            raise RuntimeError(
                "couldn't find a text version or section pages on that "
                "classics.mit.edu page"
            )
        chapters = []
        for i, (label, page_url) in enumerate(links, 1):
            progress(f"Fetching {label}…", i, len(links))
            blocks = _parse_section_page(fetcher.get(page_url))
            if blocks:
                chapters.append(Chapter(title=label, blocks=blocks))
        if translator:
            author = f"{author} · translated by {translator}" if author else translator
        return Book(title=title, author=author, source_url=index_url, chapters=chapters)


def _normalize_to_index(url):
    """Turn a pasted section-page URL (odyssey.1.i.html) into the index URL."""
    parts = urlsplit(url)
    path = re.sub(r"([\w-]+)\.\d+\.[ivxlcdm0-9]+\.html$", r"\1.html", parts.path, flags=re.I)
    return f"https://{parts.netloc}{path}"


def _find_text_version(soup, index_url):
    for a in soup.find_all("a", href=True):
        if a["href"].lower().endswith(".txt"):
            return urljoin(index_url, a["href"])
    return None


def _index_metadata(soup):
    title = author = translator = ""
    if soup.title and soup.title.string:
        # "The Internet Classics Archive | The Odyssey by Homer"
        raw = soup.title.string.split("|")[-1].strip()
        m = re.match(r"(.+?)\s+by\s+(.+)", raw, re.I)
        if m:
            title, author = m.group(1).strip(), m.group(2).strip()
        else:
            title = raw
    body_text = soup.get_text("\n")
    m = re.search(r"^Translated by (.+)$", body_text, re.M)
    if m:
        translator = m.group(1).strip()
    return title, author, translator


def _section_links(soup, index_url):
    seen = set()
    links = []
    for a in soup.find_all("a", href=True):
        m = SECTION_HREF.match(a["href"].strip())
        if not m or a["href"] in seen:
            continue
        seen.add(a["href"])
        label = re.sub(r"\s+", " ", a.get_text()).strip() or f"Part {m.group('num')}"
        links.append((label, urljoin(index_url, a["href"])))
    return links


def _parse_section_page(html):
    """Extract the work's text from one section page (fallback path only)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "table", "title", "head"]):
        tag.decompose()
    body = soup.body or soup
    # Successive <br><br> mark paragraph boundaries in the raw text flow.
    for br in body.find_all("br"):
        br.replace_with("\n")
    text = body.get_text()
    blocks = []
    for para in re.split(r"\n\s*\n", text):
        para = re.sub(r"\s+", " ", para).strip()
        if len(para) < 40:  # nav crumbs like "Table of Contents", "Book I"
            continue
        blocks.append(para)
    return blocks


ROMAN_NUMERAL = re.compile(r"^[IVXLCDM]+$", re.I)


def _heading_case(heading):
    """'BOOK II' -> 'Book II' (roman numerals stay uppercase)."""
    words = []
    for w in heading.split():
        words.append(w.upper() if ROMAN_NUMERAL.match(w) else w.capitalize())
    return " ".join(words)


def _parse_plain_text(raw, source_url):
    # Some archive .txt files are corrupted relics wrapped in old Google-cache
    # HTML (e.g. Sophocles' Antigone). Strip tags and cut to the real start.
    if re.search(r"<(html|table|base|body)\b", raw[:1000], re.I):
        raw = BeautifulSoup(raw, "html.parser").get_text("\n")
    marker = raw.find("Provided by The Internet Classics Archive")
    if marker > 0:
        raw = raw[marker:]
    lines = raw.replace("\r\n", "\n").split("\n")

    # ---- header: everything before the first long dashed line ----
    sep_idx = next((i for i, ln in enumerate(lines) if SEPARATOR.match(ln)), None)
    header, body = (lines[:sep_idx], lines[sep_idx + 1:]) if sep_idx is not None else ([], lines)

    title = author = translator = ""
    header_lines = [ln.strip() for ln in header if ln.strip()]
    # skip the "Provided by..." preamble (first 3 lines incl. the archive URL)
    meaningful = [ln for ln in header_lines if not ln.lower().startswith("provided by")
                  and not ln.lower().startswith("see bottom")
                  and not ln.lower().startswith("http")]
    for ln in meaningful:
        if not title:
            title = ln
        elif ln.lower().startswith("by "):
            author = ln[3:].strip()
        elif ln.lower().startswith("translated by "):
            translator = ln[len("translated by "):].strip()

    # ---- footer: cut at THE END, or at a dashed separator that introduces
    # the copyright block (dashed lines also precede every BOOK heading, so a
    # separator alone is not a terminator) ----
    cut = None
    for i, ln in enumerate(body):
        if THE_END.match(ln):
            cut = i
            break
        if SEPARATOR.match(ln):
            following = next((x.strip() for x in body[i + 1:i + 4] if x.strip()), "")
            if following.lower().startswith("copyright"):
                cut = i
                break
    if cut is not None:
        body = body[:cut]

    # ---- split into chapters at section headings, unwrap paragraphs ----
    chapters = []
    current = Chapter(title="")
    para = []

    def flush_para():
        if para:
            current.blocks.append(re.sub(r"\s+", " ", " ".join(para)).strip())
            para.clear()

    for ln in body:
        stripped = ln.strip()
        if SEPARATOR.match(stripped):
            flush_para()
            continue
        if HEADING.match(stripped) and len(stripped) < 60:
            flush_para()
            if current.blocks:
                chapters.append(current)
            current = Chapter(title=_heading_case(stripped))
        elif not stripped:
            flush_para()
        else:
            para.append(stripped)
    flush_para()
    if current.blocks:
        chapters.append(current)

    if not chapters:
        raise RuntimeError("the text version came back empty")
    for i, ch in enumerate(chapters, 1):
        if not ch.title:  # plays and single-part works have no BOOK headings
            ch.title = title if len(chapters) == 1 else f"Part {i}"
    if translator:
        author = f"{author} · translated by {translator}" if author else translator
    return Book(title=title or "Untitled", author=author,
                source_url=source_url, chapters=chapters)
