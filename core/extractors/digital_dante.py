"""Digital Dante adapter: wraps the standalone divine_comedy.py logic.

Produces the Divine Comedy as a Book (one chapter per canto). Uses the
Mandelbaum English translation when present, falling back to the Italian
original, then Longfellow.
"""

from ..book import Book, Chapter
from .base import Extractor

VERSION_PREFERENCE = ["mandelbaum", "italian", "longfellow"]

ROMAN = [
    "", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
    "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII", "XXIX",
    "XXX", "XXXI", "XXXII", "XXXIII", "XXXIV",
]


class DigitalDanteExtractor(Extractor):
    name = "Digital Dante (Divine Comedy)"

    @staticmethod
    def matches(url):
        return "digitaldante.columbia.edu" in url

    def scrape(self, url, fetcher, progress):
        # Imported lazily so the web app starts even if the CLI script moves.
        from divine_comedy import discover_cantos, parse_canto

        progress("Clearing the anti-bot wall and reading the table of contents…", 0, 1)
        # divine_comedy's helpers expect an object with .get(url) -> html;
        # core.fetcher.Fetcher satisfies that (and solves Anubis itself).
        cantos = discover_cantos(fetcher)
        chapters = []
        for i, (cantica, number, canto_url) in enumerate(cantos, 1):
            progress(f"Fetching {cantica.capitalize()} {number}…", i, len(cantos))
            per_version = parse_canto(fetcher.get(canto_url))
            lines = next(
                (per_version[v] for v in VERSION_PREFERENCE if per_version.get(v)),
                None,
            )
            if not lines:
                continue
            roman = ROMAN[number] if number < len(ROMAN) else str(number)
            chapters.append(
                Chapter(
                    title=f"{cantica.capitalize()} · Canto {roman}",
                    blocks=lines,
                    verse=True,
                )
            )
        return Book(
            title="The Divine Comedy",
            author="Dante Alighieri",
            source_url=url,
            chapters=chapters,
        )
