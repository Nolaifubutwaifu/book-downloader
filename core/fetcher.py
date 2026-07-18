"""Polite HTTP fetching: throttling, retries, and the Anubis proof-of-work solver.

Any site protected by Anubis (a SHA-256 proof-of-work anti-bot wall, as used by
Digital Dante) only returns a "Making sure you're not a bot!" page to plain
requests. When that wall is detected, this session solves the challenge exactly
like a browser would, keeps the resulting cookie, and re-requests the page.
"""

import hashlib
import json
import re
import time
from urllib.parse import urlsplit

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
TIMEOUT = 30


class Fetcher:
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
        m = re.search(r'<script id="anubis_challenge"[^>]*>(.*?)</script>', html, re.S)
        if not m:
            return None
        data = json.loads(m.group(1))
        return data["challenge"], int(data["rules"]["difficulty"])

    def _solve(self, base, challenge, difficulty, redir):
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
            f"{base}/.within.website/x/cmd/anubis/api/pass-challenge",
            params={
                "response": digest,
                "nonce": nonce,
                "redir": redir,
                "elapsedTime": elapsed,
            },
            timeout=TIMEOUT,
        )

    def get(self, url, tries=4):
        """GET a URL and return its decoded HTML, clearing any PoW wall."""
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        last_err = None
        for attempt in range(tries):
            try:
                self._throttle()
                resp = self.session.get(url, timeout=TIMEOUT)
                resp.raise_for_status()
                if "charset" not in resp.headers.get("Content-Type", "").lower():
                    resp.encoding = resp.apparent_encoding
                chal = self._challenge(resp.text)
                if chal is None:
                    return resp.text
                self._solve(base, chal[0], chal[1], url)
                self._throttle()
                resp = self.session.get(url, timeout=TIMEOUT)
                if "charset" not in resp.headers.get("Content-Type", "").lower():
                    resp.encoding = resp.apparent_encoding
                if self._challenge(resp.text) is None:
                    return resp.text
                last_err = RuntimeError("still walled after solving the challenge")
            except requests.RequestException as exc:
                last_err = exc
            time.sleep(2 ** attempt)
        raise RuntimeError(f"failed to fetch {url}: {last_err}")
