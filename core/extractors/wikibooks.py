"""Wikibooks (wikibooks.org) adapter.

A Wikibook is a main page (e.g. ``Python_Programming``) whose table of contents
links a series of chapter subpages (``Python_Programming/Overview``,
``.../Getting_Python``, …). This adapter reads the main page through the
MediaWiki ``action=parse`` API, collects the chapter subpages in reading order,
then fetches each one as a chapter — cleaning out MediaWiki chrome (edit links,
reference markers, navboxes) so only the prose remains.

Works on any language subdomain (en/de/fr/…). If the pasted page has no
subpages it is treated as a single-page book.
"""

import json
import re
from urllib.parse import quote, unquote, urlsplit

from bs4 import BeautifulSoup

from ..book import Book, Chapter
from .base import Extractor

# subpages that are not readable chapters
SKIP_SUFFIXES = re.compile(
    r"/(Print_version|Print_Version|Cover|Authors?|Contributors?|"
    r"Table_of_Contents|Index|Glossary/?$|About)$",
    re.I,
)
MAX_CHAPTERS = 120


class WikibooksExtractor(Extractor):
    name = "Wikibooks (wikibooks.org)"

    @staticmethod
    def matches(url):
        return "wikibooks.org" in urlsplit(url).netloc.lower()

    def scrape(self, url, fetcher, progress):
        parts = urlsplit(url)
        api = f"https://{parts.netloc}/w/api.php"
        page_title = _title_from_path(parts.path)
        if not page_title:
            raise RuntimeError("that doesn't look like a Wikibooks page URL")
        base = page_title.split("/")[0]  # the book's root page

        progress("Reading the book's table of contents…", 0, 1)
        main = _parse_page(fetcher, api, base)
        book_title = _clean(main["displaytitle"]) or base.replace("_", " ")

        subpages = _ordered_subpages(main["html"], base)
        if not subpages:
            # single-page book (or the pasted page has no chapter list)
            subpages = [page_title]

        chapters = []
        total = min(len(subpages), MAX_CHAPTERS)
        for i, sub in enumerate(subpages[:MAX_CHAPTERS], 1):
            label = _chapter_label(sub)
            progress(f"Fetching {label}…", i, total)
            try:
                page = _parse_page(fetcher, api, sub)
            except RuntimeError:
                continue  # skip a missing/renamed subpage rather than abort
            blocks = _html_to_blocks(page["html"])
            if blocks:
                chapters.append(Chapter(title=label, blocks=blocks))

        if len(subpages) > MAX_CHAPTERS:
            progress(f"(stopped at the first {MAX_CHAPTERS} chapters)", total, total)
        if not chapters:
            raise RuntimeError("no readable chapter text found on that Wikibook")
        return Book(
            title=book_title,
            author="Wikibooks contributors",
            source_url=f"https://{parts.netloc}/wiki/{base}",
            chapters=chapters,
        )


def _title_from_path(path):
    m = re.match(r"/wiki/(.+)$", path)
    if not m:
        return ""
    return unquote(m.group(1)).replace(" ", "_")


def _parse_page(fetcher, api, title):
    url = (f"{api}?action=parse&page={quote(title)}"
           f"&prop=text|displaytitle&format=json&redirects=1")
    data = json.loads(fetcher.get(url))
    if "error" in data or "parse" not in data:
        raise RuntimeError(f"Wikibooks has no page called '{title}'")
    p = data["parse"]
    return {"html": p["text"]["*"], "displaytitle": p.get("displaytitle", title)}


def _ordered_subpages(main_html, base):
    """Chapter subpages of `base`, in the main page's link order, deduped."""
    hrefs = re.findall(r'href="/wiki/([^"#?]+)"', main_html)
    seen = set()
    ordered = []
    prefix = base + "/"
    for href in hrefs:
        title = unquote(href).replace(" ", "_")
        if not title.startswith(prefix):
            continue
        if SKIP_SUFFIXES.search(title) or title in seen:
            continue
        seen.add(title)
        ordered.append(title)
    return ordered


def _chapter_label(subpage_title):
    tail = subpage_title.split("/", 1)[1] if "/" in subpage_title else subpage_title
    return tail.replace("_", " ").strip()


def _html_to_blocks(html):
    soup = BeautifulSoup(html, "html.parser")
    # strip MediaWiki chrome
    for sel in ["script", "style", "sup.reference", ".mw-editsection",
                ".noprint", ".mw-jump-link", ".toc", ".navbox", ".metadata",
                ".mw-references-wrap", ".reflist", "table.ambox", ".thumbcaption"]:
        for el in soup.select(sel):
            el.decompose()
    root = soup.select_one(".mw-parser-output") or soup

    blocks = []
    for el in root.find_all(["h2", "h3", "h4", "p", "li", "pre", "blockquote"],
                            recursive=True):
        if el.name != "pre" and el.find_parent("pre"):
            continue
        if el.name == "li" and el.find_parent(["table"]):
            continue
        keep_nl = el.name in ("pre",)
        text = _text(el, keep_nl)
        text = re.sub(r"\[\d+\]", "", text)  # leftover [1] cite markers
        if not text or len(text) < 2:
            continue
        blocks.append(text)
    return blocks


def _text(el, keep_newlines=False):
    for br in el.find_all("br"):
        br.replace_with("\n")
    text = el.get_text()
    if keep_newlines:
        lines = [ln.rstrip() for ln in text.split("\n")]
        return "\n".join(lines).strip()
    return re.sub(r"\s+", " ", text).strip()


def _clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip() if s else ""
