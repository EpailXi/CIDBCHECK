"""Look up a construction personnel on the official CIMS CIDB website
(https://cims.cidb.gov.my/PBSearchv3/finder). This is the authoritative reference.

No public JSON lookup API exists (the passport is encrypted server-side into an
`rval` token and results render as HTML), so we drive the real form with Playwright.
"""
import re
import cv2
import numpy as np
from playwright.sync_api import sync_playwright

FINDER = "https://cims.cidb.gov.my/PBSearchv3/finder?lang=ms"
DATE_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")


def lookup(passport_no, country_name=None, is_foreign=True, timeout=45000):
    result = {"found": False, "name": None, "country": None, "expiry": None,
              "trade": None, "passport_masked": None, "face": None,
              "consignment": None, "error": None}
    try:
        with sync_playwright() as p:
            # Low-memory flags so headless Chromium fits a 512MB (free-tier) box.
            browser = p.chromium.launch(headless=True, args=[
                "--single-process", "--no-zygote", "--no-sandbox",
                "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                "--disable-gpu", "--disable-extensions",
                "--disable-background-networking", "--disable-crash-reporter",
                "--disable-features=site-per-process", "--js-flags=--max-old-space-size=256",
            ])
            page = browser.new_page(viewport={"width": 1024, "height": 768})
            page.goto(FINDER, wait_until="networkidle", timeout=timeout)

            if is_foreign:
                page.get_by_text("Personel Binaan Asing").click()
            else:
                page.get_by_text("Personel Binaan Tempatan").click()

            page.locator("input[type='search'], input.form-control").first.fill(
                passport_no)

            if is_foreign and country_name:
                # select2 backed by a real <select>; set by visible label
                sel = page.locator("select").first
                try:
                    sel.select_option(label=country_name.title())
                except Exception:
                    sel.select_option(label=country_name.upper())

            page.get_by_role("button", name=re.compile("Carian", re.I)).click()
            page.wait_for_load_state("networkidle", timeout=timeout)

            body = page.inner_text("body")
            if "tamat" not in body.lower() and "tred" not in body.lower():
                result["error"] = "No record returned"
                browser.close()
                return result

            result["found"] = True
            m = re.search(r"No Pasport\s*/\s*IMM13P\s*:\s*([A-Z0-9*]+)", body, re.I)
            if m:
                result["passport_masked"] = m.group(1)

            # name = line above 'Passport / IMM13P No'
            nm = re.search(r"\n([A-Z][A-Z .'-]{3,})\nPassport\s*/\s*IMM13P", body)
            if nm:
                result["name"] = nm.group(1).strip()

            for cty in ("BANGLADESH", "INDONESIA", "INDIA", "NEPAL", "MYANMAR",
                        "PAKISTAN", "VIETNAM", "PHILIPPINES", "CAMBODIA",
                        "SRI LANKA", "THAILAND"):
                if cty in body.upper():
                    result["country"] = cty
                    break

            em = re.search(r"(\d{2}/\d{2}/\d{4})\s*\n\s*Tarikh tamat", body)
            result["expiry"] = em.group(1) if em else (
                DATE_RE.search(body).group(1) if DATE_RE.search(body) else None)

            tm = re.search(r"([A-Z0-9]{4,6})\s+([A-Z][A-Z ]+CONSTRUCTION[A-Z ]*)",
                           body)
            if tm:
                result["trade"] = tm.group(2).strip()

            cm = re.search(r"\b([A-Z]{3,}\d{6,})\b", body)
            if cm:
                result["consignment"] = cm.group(1)

            # photo: screenshot the personnel <img>
            try:
                img_el = page.locator("img").filter(
                    has_not=page.locator("[src*='logo']")).nth(0)
                imgs = page.locator("img")
                for i in range(imgs.count()):
                    src = imgs.nth(i).get_attribute("src") or ""
                    box = imgs.nth(i).bounding_box()
                    if box and box["width"] > 120 and box["height"] > 120 \
                            and "logo" not in src.lower():
                        png = imgs.nth(i).screenshot()
                        result["face"] = cv2.imdecode(
                            np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
                        break
            except Exception:
                pass

            browser.close()
    except Exception as e:
        result["error"] = str(e)
    return result
