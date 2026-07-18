"""book-downloader web app.

Paste a link, the right extractor scrapes it into a Book, then export it as a
PDF (the browser's own Save dialog asks where to put it) or plain text.

Run:  python app.py   ->  http://127.0.0.1:5060
"""

import os
import re
import threading
import uuid
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, request, send_file

from core.extractors import pick_extractor
from core.fetcher import Fetcher
from core.pdf import build_pdf
from core.textout import book_to_txt

app = Flask(__name__)

JOBS = {}
JOBS_LOCK = threading.Lock()


def _slug(title):
    s = re.sub(r"[^\w\s-]", "", title).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:60] or "book"


def _run_job(job_id, url):
    def progress(message, done=0, total=0):
        with JOBS_LOCK:
            job = JOBS[job_id]
            job["message"] = message
            job["done"] = done
            job["total"] = total

    try:
        extractor = pick_extractor(url)
        with JOBS_LOCK:
            JOBS[job_id]["extractor"] = extractor.name
        book = extractor.scrape(url, Fetcher(delay=1.0), progress)
        if not book.chapters:
            raise RuntimeError("nothing was extracted from that page")
        with JOBS_LOCK:
            job = JOBS[job_id]
            job["status"] = "done"
            job["book"] = book
            job["message"] = "Done"
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        with JOBS_LOCK:
            job = JOBS[job_id]
            job["status"] = "error"
            job["message"] = str(exc)


@app.route("/")
def index():
    return send_file(Path(__file__).parent / "index.html")


@app.route("/api/scrape", methods=["POST"])
def scrape():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "paste a link first"}), 400
    if not urlsplit(url).scheme:
        url = "https://" + url
    if urlsplit(url).scheme not in ("http", "https"):
        return jsonify({"error": "only http(s) links are supported"}), 400

    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "message": "Starting…",
            "done": 0,
            "total": 0,
            "url": url,
            "book": None,
            "extractor": "",
        }
    threading.Thread(target=_run_job, args=(job_id, url), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/job/<job_id>")
def job_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            abort(404)
        out = {
            "status": job["status"],
            "message": job["message"],
            "done": job["done"],
            "total": job["total"],
            "extractor": job["extractor"],
        }
        if job["status"] == "done":
            out["book"] = job["book"].summary()
    return jsonify(out)


def _get_book(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job or job["status"] != "done":
            abort(404)
        return job["book"]


@app.route("/api/pdf/<job_id>")
def download_pdf(job_id):
    book = _get_book(job_id)
    data = build_pdf(book)
    return send_file(
        BytesIO(data),
        mimetype="application/pdf",
        as_attachment=True,  # triggers the browser's Save dialog
        download_name=f"{_slug(book.title)}.pdf",
    )


@app.route("/api/txt/<job_id>")
def download_txt(job_id):
    book = _get_book(job_id)
    return send_file(
        BytesIO(book_to_txt(book).encode("utf-8")),
        mimetype="text/plain",
        as_attachment=True,
        download_name=f"{_slug(book.title)}.txt",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5060))
    print(f"book-downloader running on http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
