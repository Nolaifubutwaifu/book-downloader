# book-downloader

Paste a link to a book on the web — get it back as a clean PDF.

A small local web app: it scrapes the text from a book page (Project Gutenberg,
Digital Dante, most static book sites), shows you what it found, then builds a
typeset PDF — title page, chapter bookmarks, page numbers — and your browser
asks where to save it.

## Setup (one-time)
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run it
```bash
.venv/bin/python app.py
```
Then open **http://127.0.0.1:5060** (set `PORT=8000` etc. to change the port).

1. Paste the book's link and hit **Scrape**.
2. Watch the progress bar; when it's done you'll see the title, chapter list
   and word count.
3. Click **Yes, create PDF** — the browser's Save dialog pops up asking where
   to put it. (Or download as plain `.txt` instead.)

## How it works

```
app.py                    Flask server + background scrape jobs
index.html                the browser UI
core/
  fetcher.py              polite HTTP session: throttling, retries, and an
                          Anubis proof-of-work solver for sites behind that wall
  book.py                 the neutral data model: Book -> Chapters -> text
  pdf.py                  Book -> PDF (fpdf2: title page, bookmarks, page numbers)
  textout.py              Book -> plain text
  extractors/
    base.py               adapter interface: matches / scrape
    digital_dante.py      Digital Dante (the Divine Comedy, all 100 cantos)
    mit_classics.py       Internet Classics Archive (classics.mit.edu):
                          Homer, Aristotle, Sophocles, ~440 classical works
    generic.py            fallback for any static page: strips boilerplate,
                          splits chapters at headings, trims Gutenberg license text
```

Every scraper produces a `Book`; every exporter consumes one. Supporting a new
tricky site = one new file in `core/extractors/` implementing `matches()` and
`scrape()`, added to the list in `extractors/__init__.py`. The generic
extractor handles most static sites already; JavaScript-only sites, paywalls
and logins are out of scope.

## Standalone CLI: the Divine Comedy

`divine_comedy.py` still works on its own — it downloads Dante's *Divine
Comedy* from [Digital Dante](https://digitaldante.columbia.edu/dante/divine-comedy/)
as line-numbered text files in three versions (Italian original, Mandelbaum,
Longfellow):

```bash
python3 divine_comedy.py                      # everything (all 3 versions)
python3 divine_comedy.py --cantica inferno    # just the Inferno
python3 divine_comedy.py --versions italian   # just the Italian original
```

## A note on copyright
Downloads are generated on demand for personal/scholarly use and nothing is
redistributed here (output folders are gitignored). Respect each site's terms,
keep the polite default delay between requests, and mind that many translations
are still under copyright even when the original work is public domain.
