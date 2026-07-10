# CIDB Personnel Document Verifier

Verify whether a construction-worker document pack (passport / IMM13P permit +
CIDB registration card PDF) is authentic by comparing it against the official
**CIMS CIDB** website — the website is always the reference point.

## What it checks

Upload one or more PDFs. For each, the app:

1. Converts pages to images and reads the **MRZ** (machine-readable zone) on the
   passport/permit — deterministic, no API key — to get passport number, name and
   country; OCRs the CIDB card for the registration expiry.
2. Looks the passport up on `cims.cidb.gov.my` (Playwright drives the real form —
   there is no public JSON API; the site encrypts the query server-side).
3. Compares, using CIMS as the source of truth:
   - **Name** — fuzzy match
   - **Registration expiry** — exact date
   - **Country** — exact
   - **Passport / IMM13P** — visible characters (the site masks the middle)
   - **Photo** — *advisory*: the submitted photo has the same CIMS-style
     watermark applied, then both are normalized and compared. The website photo
     is watermarked and low-resolution, so this is a hint, not proof.
4. Returns a verdict: **LEGIT**, **MISMATCH**, or **NOT FOUND**.
   LEGIT requires name + expiry + country (and passport tail) to all match.

No AI API key required — MRZ parsing + Tesseract OCR + OpenCV only.

## Run locally

```bash
pip install -r requirements.txt
python -m playwright install chromium      # first time only
sudo apt-get install -y tesseract-ocr poppler-utils   # system deps
uvicorn backend.main:app --reload --port 8000
```

Open http://localhost:8000

## Deploy

- **Code**: this GitHub repo.
- **Runtime**: any host that allows outbound HTTPS to `cims.cidb.gov.my` and can
  run Chromium (Render, Railway, a VPS, or your own PC). Static-only hosts
  (GitHub Pages) cannot run the backend.
- A `Dockerfile` is the easiest path — it bundles tesseract, poppler and Chromium.

## Important notes / limitations

- The CIMS site has no CAPTCHA today but may change; the scraper selectors may
  need updating if CIDB revises the page.
- Photo comparison is intentionally advisory. Treat name/expiry/country as the
  authoritative signals.
- This tool assists a human reviewer; it does not replace official verification.
