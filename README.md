# Divine Comedy downloader

A standalone Python tool that downloads Dante's full *Divine Comedy* —
Inferno, Purgatorio and Paradiso — from
[Digital Dante](https://digitaldante.columbia.edu/dante/divine-comedy/).

Digital Dante is protected by **Anubis**, a proof-of-work anti-bot wall, so an
ordinary request only ever returns a "Making sure you're not a bot!" page. The
script solves that challenge in pure Python (the same short SHA-256
proof-of-work the browser would run), reuses the resulting cookie, then walks
all 100 cantos. It reads the table of contents from the site's own navigation,
so it stays correct even for odd URLs (e.g. Purgatorio 2's `purgatorio-2-2`
slug).

For each canto it saves clean, line-numbered text in three versions — the
Italian original (Petrocchi edition) plus the **Mandelbaum** and **Longfellow**
English translations.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage
```bash
python3 divine_comedy.py                      # everything (all 3 versions)
python3 divine_comedy.py --cantica inferno    # just the Inferno
python3 divine_comedy.py --versions italian   # just the Italian original
python3 divine_comedy.py --out ./books        # pick the output folder
python3 divine_comedy.py --delay 2.0          # be extra polite between requests
python3 divine_comedy.py --force              # re-fetch cantos already on disk
```

Output lands in `divine-comedy/<version>/<cantica>/<cantica>-NN.txt`, with a
combined `divine-comedy/<version>/<cantica>.txt` per cantica. Re-running skips
cantos already on disk (pass `--force` to re-fetch).

## A note on copyright
The `divine-comedy/` output folder is gitignored — the Mandelbaum and
Longfellow translations remain under copyright, so nothing is redistributed
here. Run the tool to generate your own copy for personal/scholarly use, keep
the default polite delay between requests, and respect Digital Dante's terms.
