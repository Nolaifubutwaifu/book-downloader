"""
scraper.py - free website contact scraper (no API key needed).

Given a website URL, fetch the homepage (and a likely 'contact' page) and pull
out the business's published email, Instagram URL, Facebook URL, and a best-guess
business name. Only returns details that are actually present on the site -
nothing is invented.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; OutreachBot/1.0; contact scraper)"}
TIMEOUT = 12

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Addresses that are almost never a real business contact.
JUNK_DOMAINS = {"example.com", "sentry.io", "wixpress.com", "domain.com",
                "email.com", "yourdomain.com", "sentry.wixpress.com"}
JUNK_SUBSTR = ("@2x", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", "@sentry")


def _normalize(url):
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def _fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if r.ok and "html" in r.headers.get("Content-Type", "").lower():
            return r.text
    except requests.RequestException:
        pass
    return None


def _pick_email(html, site_domain):
    candidates = re.findall(r"mailto:([^\"'>?\s]+)", html, re.I)
    candidates += EMAIL_RE.findall(html)
    clean, seen = [], set()
    for e in candidates:
        e = e.strip().strip(".").lower()
        if not e or e in seen:
            continue
        seen.add(e)
        if any(s in e for s in JUNK_SUBSTR):
            continue
        if e.split("@")[-1] in JUNK_DOMAINS:
            continue
        clean.append(e)
    # Prefer an address on the site's own domain.
    for e in clean:
        if site_domain and e.split("@")[-1].endswith(site_domain):
            return e
    return clean[0] if clean else ""


def _social(soup, kind):
    bad = {
        "instagram": re.compile(r"instagram\.com/(?:p/|reel/|reels/|explore|share|accounts|$)", re.I),
        "facebook": re.compile(r"facebook\.com/(?:sharer|plugins|tr/?|dialog|login|profile\.php|groups|events|$)", re.I),
    }[kind]
    host = kind + ".com/"
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if host in href.lower() and not bad.search(href):
            return href.split("?")[0].rstrip("/")
    return ""


def _business_name(soup, fallback):
    og = soup.find("meta", attrs={"property": "og:site_name"})
    if og and og.get("content", "").strip():
        return og["content"].strip()
    if soup.title:
        title = soup.title.get_text(strip=True)
        title = re.split(r"\s*[|\-–—:•]\s*", title)[0].strip()
        if title:
            return title
    return fallback


def scrape_site(url):
    """Return {url, business_name, email, instagram, facebook, note}."""
    norm = _normalize(url)
    out = {"url": norm, "business_name": "", "email": "",
           "instagram": "", "facebook": "", "note": ""}
    if not norm:
        out["note"] = "empty URL"
        return out

    netloc = urlparse(norm).netloc.replace("www.", "")
    parts = netloc.split(".")
    base_domain = ".".join(parts[-2:]) if len(parts) >= 2 else netloc

    html = _fetch(norm)
    if not html:
        out["business_name"] = netloc
        out["note"] = "couldn't load the site"
        return out

    soup = BeautifulSoup(html, "html.parser")
    out["business_name"] = _business_name(soup, netloc)
    out["email"] = _pick_email(html, base_domain)
    out["instagram"] = _social(soup, "instagram")
    out["facebook"] = _social(soup, "facebook")

    # If no email on the homepage, try a contact/about page.
    if not out["email"]:
        target = None
        for a in soup.find_all("a", href=True):
            blob = (a.get_text() or "") + " " + a["href"]
            if re.search(r"contact|about|reach", blob, re.I):
                target = urljoin(norm, a["href"])
                break
        if target and target != norm:
            chtml = _fetch(target)
            if chtml:
                csoup = BeautifulSoup(chtml, "html.parser")
                out["email"] = _pick_email(chtml, base_domain)
                out["instagram"] = out["instagram"] or _social(csoup, "instagram")
                out["facebook"] = out["facebook"] or _social(csoup, "facebook")

    out["note"] = "found email" if out["email"] else "no public email found - add manually"
    return out


def scrape_many(urls, workers=8):
    """Scrape several URLs in parallel; results stay in the same order as urls."""
    urls = list(urls)
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(urls))) as pool:
        return list(pool.map(scrape_site, urls))
