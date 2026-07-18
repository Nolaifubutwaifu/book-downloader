"""
divine_comedy.py - download Dante's *Divine Comedy* from Digital Dante.

Digital Dante (https://digitaldante.columbia.edu/dante/divine-comedy/) publishes
the full poem - Inferno, Purgatorio and Paradiso - with the Italian original
(Petrocchi edition) alongside the Mandelbaum and Longfellow English
translations. The site sits behind Anubis, a proof-of-work anti-bot wall, so a
plain HTTP request only ever gets a "Making sure you're not a bot!" page.

This script solves that challenge in pure Python (a short SHA-256 proof-of-work,
exactly what the browser would do), keeps the resulting auth cookie, then walks
every canto and saves clean, line-numbered text files - one per canto plus a
combined file per cantica.

Usage:
    python3 divine_comedy.py                     # all 3 cantiche, all 3 versions
    python3 divine_comedy.py --cantica inferno   # just the Inferno
    python3 divine_comedy.py --versions italian  # just the Italian original
    python3 divine_comedy.py --out ./books       # choose the output folder

Nothing is invented: every line comes straight from the page. Text is downloaded
for personal/scholarly use - please respect Digital Dante's terms and keep the
default polite delay between requests.
"""

import argparse
import copy
import hashlib
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://digitaldante.columbia.edu"
INDEX_URL = f"{BASE}/dante/divine-comedy/"
# A canto that is guaranteed to exist, used to harvest the full navigation.
SEED_URL = f"{BASE}/dante/divine-comedy/inferno/inferno-1/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
TIMEOUT = 30

CANTICHE = ("inferno", "purgatorio", "paradiso")

# tab id on the page -> (short name used for filenames, human label)
VERSIONS = {
    "tab1": ("italian", "Italian (Petrocchi edition)"),
    "tab2": ("mandelbaum", "English - Allen Mandelbaum"),
    "tab3": ("longfellow", "English - Henry Wadsworth Longfellow"),
}
VERSION_KEYS = [v[0] for v in VERSIONS.values()]


# --------------------------------------------------------------------------- #
# Anubis proof-of-work
# --------------------------------------------------------------------------- #

class AnubisSession:
    """A requests.Session that transparently clears the Anubis PoW wall."""

    def __init__(self, delay=1.0):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.delay = delay
        self._last_request = 0.0

    def _throttle(self):
        wait = self.delay - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.time()

    @staticmethod
    def _challenge(html):
        """Return (challenge, difficulty) if the page is an Anubis wall, else None."""
        m = re.search(
            r'<script id="anubis_challenge"[^>]*>(.*?)</script>', html, re.S
        )
        if not m:
            return None
        import json
        data = json.loads(m.group(1))
        return data["challenge"], int(data["rules"]["difficulty"])

    def _solve(self, challenge, difficulty, redir):
        """Brute-force the SHA-256 proof-of-work and redeem it for an auth cookie."""
        prefix = "0" * difficulty
        start = time.time()
        nonce = 0
        while True:
            digest = hashlib.sha256(f"{challenge}{nonce}".encode()).hexdigest()
            if digest.startswith(prefix):
                break
            nonce += 1
        elapsed = int((time.time() - start) * 1000)
        self.session.get(
            f"{BASE}/.within.website/x/cmd/anubis/api/pass-challenge",
            params={
                "response": digest,
                "nonce": nonce,
                "redir": redir,
                "elapsedTime": elapsed,
            },
            timeout=TIMEOUT,
        )

    def get(self, url, tries=4):
        """GET a URL, solving the PoW wall (and retrying transient errors)."""
        last_err = None
        for attempt in range(tries):
            try:
                self._throttle()
                resp = self.session.get(url, timeout=TIMEOUT)
                chal = self._challenge(resp.text)
                if chal is None:
                    return resp.text
                # Hit the wall - solve it, then re-request the real page.
                self._solve(chal[0], chal[1], url)
                self._throttle()
                resp = self.session.get(url, timeout=TIMEOUT)
                if self._challenge(resp.text) is None:
                    return resp.text
                last_err = RuntimeError("still walled after solving the challenge")
            except requests.RequestException as exc:
                last_err = exc
            time.sleep(2 ** attempt)  # 1s, 2s, 4s, 8s
        raise RuntimeError(f"failed to fetch {url}: {last_err}")


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

def discover_cantos(session):
    """Return an ordered list of (cantica, number, url) for all 100 cantos.

    The list of cantos - including quirky slugs like ``purgatorio-2-2`` - is read
    straight from the site's own navigation, so it stays correct even if the URL
    scheme has exceptions.
    """
    html = session.get(SEED_URL)
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for a in soup.find_all("a", href=True):
        m = re.search(
            r"/dante/divine-comedy/(inferno|purgatorio|paradiso)/([^/\"?#]+)/?",
            a["href"],
        )
        if not m:
            continue
        cantica, slug = m.group(1), m.group(2)
        num = re.search(r"(\d+)", slug)
        if not num:
            continue
        num = int(num.group(1))
        url = urljoin(BASE, m.group(0))
        if not url.endswith("/"):
            url += "/"
        found[(cantica, num)] = url

    cantos = [
        (c, n, found[(c, n)])
        for c in CANTICHE
        for n in range(1, 40)
        if (c, n) in found
    ]
    if not cantos:
        raise RuntimeError("no canto links found - the page layout may have changed")
    return cantos


def _entry_to_lines(entry):
    """Flatten one ``.translation-entry`` into a list of verse lines.

    The Italian marks each line with ``<span class="ln">N</span>``; the English
    translations wrap each tercet in ``<p>`` with ``<br>`` between lines. Treating
    all of those as hard breaks reconstructs the verse either way.
    """
    e = copy.copy(entry)
    for br in e.find_all("br"):
        br.replace_with("\n")
    for ln in e.find_all("span", class_="ln"):
        ln.replace_with("\n")  # drop the printed number; we re-number ourselves
    for block in e.find_all(["p", "div"]):
        block.insert_before("\n")
        block.insert_after("\n")
    lines = [re.sub(r"\s+", " ", x).strip() for x in e.get_text().split("\n")]
    return [x for x in lines if x]


def parse_canto(html):
    """Return {version_key: [lines]} for every translation present on the page."""
    soup = BeautifulSoup(html, "html.parser")
    section = soup.select_one(".translation-box-1 section")
    out = {}
    if not section:
        return out
    for tab_id, (key, _label) in VERSIONS.items():
        entry = section.select_one(f".{tab_id} .translation-entry")
        if entry:
            lines = _entry_to_lines(entry)
            if lines:
                out[key] = lines
    return out


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

ROMAN = [
    "", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
    "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII", "XXIX",
    "XXX", "XXXI", "XXXII", "XXXIII", "XXXIV",
]


def _label_for(key):
    for _tab, (k, label) in VERSIONS.items():
        if k == key:
            return label
    return key


def render_canto(cantica, number, url, lines, version_key):
    """Format one canto as a numbered, human-readable text block."""
    head = f"{cantica.upper()} · CANTO {ROMAN[number] if number < len(ROMAN) else number}"
    out = [
        head,
        _label_for(version_key),
        f"Source: {url}",
        "",
    ]
    width = len(str(len(lines)))
    for i, line in enumerate(lines, 1):
        out.append(f"{str(i).rjust(width)}  {line}")
    return "\n".join(out) + "\n"


def write_outputs(out_dir, results, versions):
    """Write per-canto files and a combined file per cantica, for each version.

    ``results`` is an ordered list of (cantica, number, url, {version: lines}).
    """
    out_dir = Path(out_dir)
    written = 0
    for version in versions:
        combined = {c: [] for c in CANTICHE}
        for cantica, number, url, per_version in results:
            lines = per_version.get(version)
            if not lines:
                continue
            block = render_canto(cantica, number, url, lines, version)
            canto_dir = out_dir / version / cantica
            canto_dir.mkdir(parents=True, exist_ok=True)
            (canto_dir / f"{cantica}-{number:02d}.txt").write_text(
                block, encoding="utf-8"
            )
            combined[cantica].append(block)
            written += 1
        # One file per cantica containing every canto in reading order.
        for cantica in CANTICHE:
            if combined[cantica]:
                (out_dir / version / f"{cantica}.txt").write_text(
                    "\n\n".join(combined[cantica]), encoding="utf-8"
                )
    return written


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Download Dante's Divine Comedy from Digital Dante."
    )
    ap.add_argument(
        "--out", default="divine-comedy",
        help="output folder (default: ./divine-comedy)",
    )
    ap.add_argument(
        "--cantica", choices=CANTICHE, action="append",
        help="limit to one or more cantiche (default: all three)",
    )
    ap.add_argument(
        "--versions", default="all",
        help="comma-separated: italian,mandelbaum,longfellow or 'all' (default)",
    )
    ap.add_argument(
        "--delay", type=float, default=1.0,
        help="seconds to wait between requests (default: 1.0)",
    )
    ap.add_argument(
        "--force", action="store_true",
        help="re-download cantos even if their file already exists",
    )
    args = ap.parse_args(argv)

    if args.versions.strip().lower() == "all":
        versions = list(VERSION_KEYS)
    else:
        versions = [v.strip().lower() for v in args.versions.split(",") if v.strip()]
        bad = [v for v in versions if v not in VERSION_KEYS]
        if bad:
            ap.error(f"unknown version(s): {', '.join(bad)}. "
                     f"choose from {', '.join(VERSION_KEYS)}")

    wanted_cantiche = set(args.cantica) if args.cantica else set(CANTICHE)
    out_dir = Path(args.out)

    session = AnubisSession(delay=args.delay)
    print("Clearing the anti-bot wall and reading the table of contents...")
    cantos = [c for c in discover_cantos(session) if c[0] in wanted_cantiche]
    print(f"Found {len(cantos)} cantos across "
          f"{', '.join(sorted(wanted_cantiche))}.\n")

    results = []
    for idx, (cantica, number, url) in enumerate(cantos, 1):
        # Resume support: skip cantos whose files already exist for every version.
        if not args.force:
            existing = [
                (out_dir / v / cantica / f"{cantica}-{number:02d}.txt").exists()
                for v in versions
            ]
            if all(existing):
                print(f"[{idx:>3}/{len(cantos)}] {cantica} {number:>2}  "
                      f"(already downloaded, skipping)")
                # Marked empty here; _reload_skipped() loads it back from disk so
                # the combined per-cantica files still come out complete.
                results.append((cantica, number, url, {}))
                continue
        try:
            html = session.get(url)
            per_version = parse_canto(html)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"[{idx:>3}/{len(cantos)}] {cantica} {number:>2}  "
                  f"ERROR: {exc}")
            continue
        got = [v for v in versions if per_version.get(v)]
        missing = [v for v in versions if not per_version.get(v)]
        note = f"{len(per_version.get(versions[0], []))} lines" if got else "no text found"
        flag = "" if not missing else f"  (missing: {', '.join(missing)})"
        print(f"[{idx:>3}/{len(cantos)}] {cantica} {number:>2}  {note}{flag}")
        results.append((cantica, number, url, per_version))

    # When resuming, some entries have empty dicts; reload them from disk so the
    # combined per-cantica files are rebuilt in full.
    results = _reload_skipped(out_dir, results, versions)

    written = write_outputs(out_dir, results, versions)
    print(f"\nDone. Wrote/updated {written} canto files under {out_dir}/")
    for v in versions:
        print(f"  {out_dir}/{v}/  ->  {_label_for(v)}")
    return 0


def _reload_skipped(out_dir, results, versions):
    """Fill in text for cantos that were skipped, by reading their saved files."""
    out_dir = Path(out_dir)
    rebuilt = []
    for cantica, number, url, per_version in results:
        if per_version:
            rebuilt.append((cantica, number, url, per_version))
            continue
        loaded = {}
        for v in versions:
            p = out_dir / v / cantica / f"{cantica}-{number:02d}.txt"
            if p.exists():
                body = p.read_text(encoding="utf-8").splitlines()
                lines = [re.sub(r"^\s*\d+\s{2}", "", ln) for ln in body[4:] if ln.strip()]
                if lines:
                    loaded[v] = lines
        rebuilt.append((cantica, number, url, loaded))
    return rebuilt


if __name__ == "__main__":
    sys.exit(main())
