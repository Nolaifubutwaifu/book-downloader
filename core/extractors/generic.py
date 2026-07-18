"""Generic extractor: turn any mostly-static HTML page into a Book.

Strategy: strip obvious boilerplate (nav, scripts, footers), walk the body's
headings and paragraphs in document order, and split into chapters at headings.
Project Gutenberg's ``*** START/END OF ...`` license markers are trimmed
automatically so the book body comes out clean.
"""

import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from ..book import Book, Chapter
from .base import Extractor

STRIP_TAGS = [
    "script", "style", "noscript", "header", "footer", "nav", "aside",
    "form", "iframe", "svg", "button", "figure",
]
# Elements whose class marks them as page furniture, not content.
STRIP_CLASS = re.compile(r"pagenum|pageno|page-number|toc|sidebar|menu|breadcrumb", re.I)

GUT_START = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG", re.I)
GUT_END = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG", re.I)

MAX_CHAPTERS = 400


class GenericExtractor(Extractor):
    name = "generic page extractor"

    @staticmethod
    def matches(url):
        return True  # fallback: handles anything

    def scrape(self, url, fetcher, progress):
        progress("Fetching page…", 0, 3)
        html = fetcher.get(url)
        progress("Extracting text…", 1, 3)
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(STRIP_TAGS):
            tag.decompose()
        for tag in soup.find_all(class_=STRIP_CLASS):
            tag.decompose()

        title, author = _page_title_author(soup, url)
        body = soup.body or soup

        blocks = []  # ("h", text, level) or ("t", text, 0)
        for el in body.find_all(["h1", "h2", "h3", "h4", "p", "pre"]):
            if el.name != "pre" and el.find_parent("pre"):
                continue
            text = _block_text(el, keep_newlines=(el.name == "pre"))
            if not text:
                continue
            if el.name[0] == "h":
                blocks.append(("h", text, int(el.name[1])))
            else:
                blocks.append(("t", text, 0))

        blocks = _trim_gutenberg(blocks)
        progress("Splitting into chapters…", 2, 3)
        chapters = _split_chapters(blocks)
        if not chapters:
            raise RuntimeError(
                "no readable text found on that page - it may need JavaScript, "
                "a login, or a dedicated extractor"
            )
        progress("Done", 3, 3)
        return Book(title=title, author=author, source_url=url, chapters=chapters)


def _page_title_author(soup, url):
    """Best-effort title/author from <title> or the first h1."""
    raw = ""
    if soup.title and soup.title.string:
        raw = re.sub(r"\s+", " ", soup.title.string).strip()
    if not raw:
        h1 = soup.find("h1")
        raw = _block_text(h1) if h1 else urlsplit(url).netloc
    # Common patterns: "Title, by Author" / "Title | Site" / "Title - Site"
    author = ""
    m = re.match(r"(.+?),?\s+by\s+(.+)", raw, re.I)
    if m:
        raw, author = m.group(1).strip(), m.group(2).strip()
    raw = re.split(r"\s+[|–—]\s+", raw)[0].strip()
    raw = re.sub(r"^The Project Gutenberg e(Book|text) of\s*", "", raw, flags=re.I)
    return raw or urlsplit(url).netloc, author


def _block_text(el, keep_newlines=False):
    if el is None:
        return ""
    for br in el.find_all("br"):
        br.replace_with("\n")
    text = el.get_text()
    if keep_newlines or "\n" in text.strip():
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
        return "\n".join(ln for ln in lines if ln)
    return re.sub(r"\s+", " ", text).strip()


def _trim_gutenberg(blocks):
    """Cut everything outside Gutenberg's *** START / *** END markers."""
    start = next((i for i, b in enumerate(blocks) if GUT_START.search(b[1])), None)
    if start is not None:
        blocks = blocks[start + 1:]
    end = next((i for i, b in enumerate(blocks) if GUT_END.search(b[1])), None)
    if end is not None:
        blocks = blocks[:end]
    return blocks


def _split_chapters(blocks):
    """Split at headings; merge consecutive headings; drop empty chapters."""
    chapters = []
    current = Chapter(title="")
    for kind, text, _level in blocks:
        if kind == "h":
            if current.blocks:
                chapters.append(current)
                current = Chapter(title=text)
            elif current.title:
                # heading directly after heading: nested structure, merge titles
                current.title = f"{current.title} — {text}"
            else:
                current.title = text
        else:
            current.blocks.append(text)
    if current.blocks:
        chapters.append(current)

    chapters = [c for c in chapters if c.word_count() > 0]
    for i, c in enumerate(chapters, 1):
        if not c.title:
            c.title = f"Part {i}"
        c.title = c.title[:200]
    if len(chapters) > MAX_CHAPTERS:
        # keep the reader sane: merge overflow into the last chapter
        head, tail = chapters[:MAX_CHAPTERS - 1], chapters[MAX_CHAPTERS - 1:]
        merged = Chapter(title=tail[0].title)
        for c in tail:
            merged.blocks.extend([c.title] + c.blocks if c is not tail[0] else c.blocks)
        chapters = head + [merged]
    return chapters
