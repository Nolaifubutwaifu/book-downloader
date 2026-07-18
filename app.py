#!/usr/bin/env python3
"""
app.py - Photography Outreach Manager (local web app).

Backed by local files + the Gmail API:

  * Find businesses by area (Google Places) or paste website URLs, then scrape
    each site for business name, email, Instagram and Facebook -> review ->
    save to contacts.csv
  * One click -> create a Gmail draft (or send directly, via the Send toggle)
  * contacts.csv tracks each business's status and when it was contacted, so
    already-contacted businesses are skipped

Run:
  .venv/bin/python app.py
then open http://127.0.0.1:5050
"""

import csv
import os
import random
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify

import scraper
import gmail_client
import places

CONTACTS_FILE = "contacts.csv"
TEMPLATE_FILE = "email_template.txt"
INDEX_FILE = "index.html"
FIELDS = ["business_name", "email", "url", "instagram", "facebook",
          "note", "status", "contacted_at"]
MAX_URLS_PER_BATCH = 40

# When sending a whole batch live, pause an irregular amount between each email
# (a few seconds to a few minutes) so a run doesn't look like a spam blast.
BATCH_MIN_DELAY_SECONDS = 20
BATCH_MAX_DELAY_SECONDS = 120

app = Flask(__name__)
_service = None  # lazily-created Gmail API service (auth only when first needed)


# --- contacts.csv store -------------------------------------------------------
def load_contacts():
    if not Path(CONTACTS_FILE).exists():
        return []
    with open(CONTACTS_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in FIELDS:
            r.setdefault(k, "")
    return rows


def save_contacts(rows):
    with open(CONTACTS_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def find(rows, email):
    email = (email or "").strip().lower()
    for r in rows:
        if r.get("email", "").strip().lower() == email:
            return r
    return None


# --- email template -----------------------------------------------------------
def load_template():
    if not Path(TEMPLATE_FILE).exists():
        return "", ""
    lines = Path(TEMPLATE_FILE).read_text(encoding="utf-8").splitlines()
    subject, start = "", 0
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
            start = i + 1
            break
    body = "\n".join(lines[start:]).lstrip("\n").rstrip()
    return subject, body


def save_template(subject, body):
    Path(TEMPLATE_FILE).write_text(f"Subject: {subject}\n\n{body}\n", encoding="utf-8")


# --- Gmail (lazy) -------------------------------------------------------------
def gmail():
    global _service
    if _service is None:
        _service = gmail_client.get_service()
    return _service


# --- routes -------------------------------------------------------------------
@app.route("/")
def index():
    html = Path(INDEX_FILE).read_text(encoding="utf-8")
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.get("/api/contacts")
def api_contacts():
    return jsonify(load_contacts())


@app.get("/api/template")
def api_get_template():
    subject, body = load_template()
    return jsonify({"subject": subject, "body": body})


@app.post("/api/template")
def api_set_template():
    d = request.get_json(force=True) or {}
    save_template((d.get("subject") or "").strip(), (d.get("body") or "").rstrip())
    subject, body = load_template()
    return jsonify({"subject": subject, "body": body})


@app.post("/api/scrape")
def api_scrape():
    d = request.get_json(force=True) or {}
    urls = d.get("urls", [])
    if isinstance(urls, str):
        urls = urls.splitlines()
    cleaned, seen = [], set()
    for u in urls:
        u = (u or "").strip()
        if not u or u.lower() in seen:
            continue
        seen.add(u.lower())
        cleaned.append(u)
        if len(cleaned) >= MAX_URLS_PER_BATCH:
            break
    return jsonify(scraper.scrape_many(cleaned))


@app.post("/api/find")
def api_find():
    """Find businesses via Google Places, then scrape each site for an email."""
    d = request.get_json(force=True) or {}
    try:
        businesses = places.search_businesses(
            d.get("category", ""), d.get("area", ""), d.get("max_results", 20)
        )
    except Exception as e:  # noqa: BLE001 - surface config errors to the UI
        return jsonify({"error": str(e)}), 400

    scraped = scraper.scrape_many([b.get("url", "") for b in businesses])
    results = []
    for b, s in zip(businesses, scraped):
        s = s or {}
        note = " · ".join(x for x in [b.get("address", ""), b.get("phone", "")] if x)
        results.append({
            "url": b.get("url", "") or s.get("url", ""),
            "business_name": b.get("business_name") or s.get("business_name", ""),
            "email": s.get("email", ""),
            "instagram": s.get("instagram", ""),
            "facebook": s.get("facebook", ""),
            "note": note or s.get("note", ""),
        })
    return jsonify(results)


@app.post("/api/contacts")
def api_add_contacts():
    d = request.get_json(force=True) or {}
    rows = load_contacts()
    added, skipped = 0, 0
    for c in d.get("contacts", []):
        email = (c.get("email") or "").strip()
        if not email:
            skipped += 1
            continue
        if find(rows, email):
            skipped += 1  # dedup by email
            continue
        rows.insert(0, {
            "business_name": (c.get("business_name") or "").strip() or "(no name)",
            "email": email,
            "url": (c.get("url") or "").strip(),
            "instagram": (c.get("instagram") or "").strip(),
            "facebook": (c.get("facebook") or "").strip(),
            "note": (c.get("note") or "").strip(),
            "status": "to_send",
            "contacted_at": "",
        })
        added += 1
    save_contacts(rows)
    return jsonify({"added": added, "skipped": skipped, "contacts": rows})


@app.post("/api/status")
def api_status():
    d = request.get_json(force=True) or {}
    rows = load_contacts()
    r = find(rows, d.get("email"))
    if not r:
        return jsonify({"error": "not found"}), 404
    r["status"] = d.get("status", r["status"])
    save_contacts(rows)
    return jsonify(r)


@app.post("/api/delete")
def api_delete():
    d = request.get_json(force=True) or {}
    email = (d.get("email") or "").strip().lower()
    rows = [r for r in load_contacts() if r.get("email", "").strip().lower() != email]
    save_contacts(rows)
    return jsonify({"ok": True})


@app.post("/api/draft")
def api_draft():
    d = request.get_json(force=True) or {}
    send = bool(d.get("send"))
    rows = load_contacts()
    r = find(rows, d.get("email"))
    if not r:
        return jsonify({"error": "not found"}), 404
    subject, body = load_template()
    try:
        svc = gmail()
        if send:
            gmail_client.send_message(svc, r["email"], subject, body)
        else:
            gmail_client.create_draft(svc, r["email"], subject, body)
    except Exception as e:  # noqa: BLE001 - surface to the UI
        return jsonify({"error": str(e)}), 500
    r["status"] = "sent" if send else "drafted"
    r["contacted_at"] = datetime.now().isoformat(timespec="seconds")
    save_contacts(rows)
    return jsonify({"ok": True, "contact": r})


@app.post("/api/draft-all")
def api_draft_all():
    d = request.get_json(force=True) or {}
    send = bool(d.get("send"))
    rows = load_contacts()
    subject, body = load_template()
    done, errors = 0, []
    try:
        svc = gmail()
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500
    targets = [r for r in rows if r.get("status") == "to_send" and r.get("email")]
    for i, r in enumerate(targets):
        try:
            if send:
                gmail_client.send_message(svc, r["email"], subject, body)
                r["status"] = "sent"
            else:
                gmail_client.create_draft(svc, r["email"], subject, body)
                r["status"] = "drafted"
            r["contacted_at"] = datetime.now().isoformat(timespec="seconds")
            done += 1
            if send and i < len(targets) - 1:
                # Irregular gap so a batch doesn't look like a spam blast.
                time.sleep(random.uniform(BATCH_MIN_DELAY_SECONDS,
                                          BATCH_MAX_DELAY_SECONDS))
        except Exception as e:  # noqa: BLE001
            errors.append({"email": r["email"], "error": str(e)})
    save_contacts(rows)
    return jsonify({"done": done, "errors": errors, "contacts": rows})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    print(f"Photography Outreach Manager  ->  http://127.0.0.1:{port}")
    print("(The first time you create a draft, a browser opens to authorise Gmail.)")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
