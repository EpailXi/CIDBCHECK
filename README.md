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
uvicorn main:app --app-dir backend --reload --port 8000
```

Open http://localhost:8000

## Deploy (frontend on GitHub Pages + backend on Render)

GitHub Pages can only serve the static frontend; the Python backend
(Playwright + OCR) must run on a real host. This repo is wired for
**Render (backend) + GitHub Pages (frontend)**.

### 1. Backend → Render
1. Push this repo to GitHub (done).
2. On https://render.com → **New → Web Service → Build from a repository**,
   pick `CIDBCHECK`. Render reads `render.yaml` and builds the `Dockerfile`
   (bundles tesseract, poppler, Chromium). Plan: Free.
3. When it's live, copy the service URL, e.g. `https://cidbcheck-api.onrender.com`.

### 2. Frontend → GitHub Pages
1. Edit `frontend/index.html`, find `API_BASE`, and replace
   `REPLACE-WITH-YOUR-RENDER-URL.onrender.com` with your real Render URL.
2. Commit & push. The included Action (`.github/workflows/pages.yml`)
   publishes `frontend/` to Pages automatically.
3. In the repo: **Settings → Pages → Source = GitHub Actions**.
4. Your UI is live at `https://epailxi.github.io/CIDBCHECK/`.

Notes:
- Render's free plan sleeps when idle, so the first request after a pause takes
  ~30–50s to wake. Paid plans stay warm.
- The backend needs outbound HTTPS to `cims.cidb.gov.my` (Render allows this).

### Or: one host, no Pages
Deploy just the backend on Render — it also serves the UI at its own URL
(`main.py` serves `index.html` at `/`). Skip the Pages steps entirely.

## Important notes / limitations

- The CIMS site has no CAPTCHA today but may change; the scraper selectors may
  need updating if CIDB revises the page.
- Photo comparison is intentionally advisory. Treat name/expiry/country as the
  authoritative signals.
- This tool assists a human reviewer; it does not replace official verification.
