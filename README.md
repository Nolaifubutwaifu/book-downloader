# Photography Outreach Manager

> **Sending account:** every email from this project is always sent from
> **maximilianumschaden@gmail.com**. That is the only account this toolkit uses —
> the Gmail credentials, drafts, and sent mail all belong to it. No other address
> is involved in this project.

A small local web app for sending free-shoot outreach to local businesses from your
Gmail account (**maximilianumschaden@gmail.com**). Find businesses by area,
auto-scrape their public email + Instagram + Facebook, review the list, and create a
**Gmail draft** (or send directly) for each — with built-in tracking of who you've
already contacted.

---

## Setup (one-time, ≈20–30 min)

### 1. Install Python deps
From this folder:
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Enable the Gmail API and get credentials
1. Go to https://console.cloud.google.com/ and create a project (any name).
2. In the search bar, open **Gmail API** and click **Enable**.
3. Go to **APIs & Services → OAuth consent screen**. Choose **External**, fill in
   the app name and use **maximilianumschaden@gmail.com**, and add that same
   address as a **Test user**. (Keep it in "Testing" mode — no Google review
   needed for personal use.) Always authorise as
   **maximilianumschaden@gmail.com** when the browser opens on first run — that is
   the account mail is sent from.
4. Go to **APIs & Services → Credentials → Create credentials → OAuth client ID**.
   Choose **Desktop app**. Download the JSON.
5. Rename that file to **`credentials.json`** and put it in this folder.

> `credentials.json` and the `token.json` created on first run are secrets.
> They're in `.gitignore` — never commit them.

---

## Run it
```bash
.venv/bin/python app.py
```
Then open **http://127.0.0.1:5050** (set `PORT=8000` etc. to change the port).

The first time you create a draft or send, a browser opens to authorise Gmail. The
email wording lives in `email_template.txt` and is editable right in the app.

## What it does
- **Find businesses** — enter a category + area (e.g. *cafe* in *Saint Lucia,
  Brisbane*); it pulls businesses and their websites from Google Places, then scrapes
  each site for the email + socials. *(Optional — needs a Places API key, see below.)*
- **From websites** — paste a batch of site links (one per line) and scrape those.
- **Bulk paste / Single** — add contacts from `Name, email` lines or one at a time.
- **Create draft or send** — one click puts a ready-to-send email in your **Gmail
  Drafts** to review. Flip the **Draft / Send** toggle to email immediately instead
  (drafts are the default and safer). Works per-business or for the whole "to send"
  list at once.
- **Tracking** — everything is saved to `contacts.csv` with a status
  (*To send / Drafted / Sent / Replied*) and the time each was contacted. Re-adding
  the same email is skipped, so your list never doubles up.

> The free scraper reads each site's own pages for a published email and social
> links. Some businesses hide their email behind a contact form — for those, just
> type the address into the review row before adding.

### Find businesses with Google Places (optional)

The **Find businesses** tab needs a Google Maps Platform API key. One-time setup:

1. In [Google Cloud Console](https://console.cloud.google.com/) (same project as
   your Gmail credentials), open **APIs & Services → Library**, search
   **Places API (New)**, and **Enable** it.
2. Turn on **billing**: **Billing → link a billing account** (add a card). Required
   even though normal personal use stays inside Google's free monthly tier.
3. **APIs & Services → Credentials → Create credentials → API key.** Copy the key.
   (Recommended: edit the key → **Restrict key → Places API (New)**.)
4. Paste the key into a file called **`places_api_key.txt`** in this folder
   (it's gitignored), or set the `GOOGLE_MAPS_API_KEY` environment variable.

Then restart the app. Google Places only returns name/website/phone/address — the
email always comes from scraping the business's own site, so leads with no website
(or no published email) will need the address typed in by hand.

---

## Bonus: download the Divine Comedy (`divine_comedy.py`)

A standalone side tool (unrelated to the outreach app) that downloads Dante's
full *Divine Comedy* — Inferno, Purgatorio and Paradiso — from
[Digital Dante](https://digitaldante.columbia.edu/dante/divine-comedy/).

The site is protected by **Anubis**, a proof-of-work anti-bot wall, so an
ordinary request only ever returns a "Making sure you're not a bot!" page. The
script solves that challenge in pure Python (the same short SHA-256 proof-of-work
the browser would run), reuses the resulting cookie, then walks all 100 cantos.
It reads the table of contents from the site's own navigation, so it stays
correct even for odd URLs (e.g. Purgatorio 2's `purgatorio-2-2` slug).

For each canto it saves clean, line-numbered text in three versions — the Italian
original (Petrocchi edition) plus the **Mandelbaum** and **Longfellow** English
translations:

```bash
python3 divine_comedy.py                      # everything (all 3 versions)
python3 divine_comedy.py --cantica inferno    # just the Inferno
python3 divine_comedy.py --versions italian   # just the Italian original
python3 divine_comedy.py --out ./books        # pick the output folder
```

Output lands in `divine-comedy/<version>/<cantica>/<cantica>-NN.txt`, with a
combined `divine-comedy/<version>/<cantica>.txt` per cantica. Re-running skips
cantos already on disk (pass `--force` to re-fetch). The `divine-comedy/` folder
is gitignored — the translations are still under copyright, so run the tool to
generate your own copy for personal/scholarly use and respect the site's terms.

---

## A note on the law (you're in Australia)
The Spam Act 2003 applies to commercial emails. Only email businesses whose contact
address is **publicly listed**, keep volumes modest, and honour any "unsubscribe"
reply immediately. This isn't legal advice — when in doubt, check the ACMA guidance
on commercial electronic messages.

---

## Files
| File | What it is |
|------|------------|
| `app.py` | the web app (Flask server + Gmail drafts/sends) |
| `index.html` | the browser UI |
| `scraper.py` | free website contact scraper (email + socials) |
| `divine_comedy.py` | standalone tool: downloads Dante's Divine Comedy from Digital Dante |
| `places.py` | find businesses via Google Places (New) |
| `gmail_client.py` | Gmail auth + draft creation / sending |
| `email_template.txt` | the outreach email subject + body (editable in the app) |
| `requirements.txt` | Python dependencies |
| `contacts.csv` | your business list + status (auto-created, gitignored) |
| `credentials.json` / `token.json` | your Gmail secrets (gitignored, you provide) |
| `places_api_key.txt` | your Google Places API key (gitignored, you provide) |
