"""Extract identity fields from uploaded PDF pages.

Zero external API. Strategy:
  1. PDF -> page PNGs (pdftoppm).
  2. Parse MRZ (TD3 passport / permit) deterministically -> passport no, country, name, DOB.
  3. OCR each page (tesseract) to locate CIDB card fields (expiry, name, country).
  4. Detect/crop the largest face on passport + CIDB pages as the reference photos.
"""
import os
import re
import subprocess
import tempfile
import cv2
import numpy as np
import pytesseract

MRZ_LINE = re.compile(r"[A-Z0-9<]{28,44}")


def pdf_to_images(pdf_path, dpi=200):
    out_dir = tempfile.mkdtemp(prefix="cidb_")
    prefix = os.path.join(out_dir, "page")
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), pdf_path, prefix],
                   check=True)
    return sorted(
        os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.endswith(".png"))


def _ocr(img_path):
    img = cv2.imread(img_path)
    if img is None:
        return "", None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    txt = pytesseract.image_to_string(gray)
    return txt, img


# ---------------- MRZ ----------------

DATA_LINE = re.compile(r"([A-Z0-9<]{9})\d?([A-Z]{3})\d")
NAME_LINE = re.compile(r"(?:^[A-Z]{1,2}<?|<)([A-Z]{3})([A-Z<]+<<[A-Z<]+)")


def parse_mrz(text):
    """Parse TD3-style MRZ, tolerant of OCR noise. Returns dict or None."""
    lines = [re.sub(r"[^A-Z0-9<]", "", l.upper().replace(" ", ""))
             for l in text.splitlines()]
    lines = [l for l in lines if len(l) >= 12]

    passport_no = country = name = None
    for l in lines:
        if len(l) < 28:  # real MRZ lines span the full document width
            continue
        for m in DATA_LINE.finditer(l):
            pno, cc = m.group(1).replace("<", ""), m.group(2)
            if cc in COUNTRY and re.match(r"^[A-Z]{1,2}\d", pno):
                passport_no, country = pno, cc
                break
        if passport_no:
            break

    for l in lines:
        # name line: <country><SURNAME<<GIVEN NAMES>
        idx = l.find((country or "") + "") if country else -1
        m = re.search(r"([A-Z]{3})([A-Z]+<<[A-Z<]+)", l)
        if m and (country is None or m.group(1) == country):
            after = m.group(2)
            segs = re.split(r"<<+", after)
            surname = segs[0].replace("<", " ").strip()
            given = segs[1].replace("<", " ").strip() if len(segs) > 1 else ""
            cand = f"{given} {surname}".strip()
            if len(cand) >= 4:
                name = cand
                if country is None:
                    country = m.group(1)
                break

    if passport_no and country:
        return {"passport_no": passport_no, "country_code": country,
                "name": name, "source": "MRZ"}
    return None


COUNTRY = {"BGD": "BANGLADESH", "IDN": "INDONESIA", "IND": "INDIA",
           "NPL": "NEPAL", "MMR": "MYANMAR", "PAK": "PAKISTAN",
           "LKA": "SRI LANKA", "VNM": "VIETNAM", "PHL": "PHILIPPINES",
           "THA": "THAILAND", "KHM": "CAMBODIA", "MYS": "MALAYSIA"}

# ---------------- CIDB card fields ----------------

DATE_RE = re.compile(r"(\d{2})[/\-.](\d{2})[/\-.](\d{4})")


def parse_cidb(text):
    """Pull CIDB registration expiry, name, country from OCR text."""
    out = {}
    up = text.upper()
    # expiry: line containing TAMAT (expiry) -> nearest date
    for line in text.splitlines():
        if "TAMAT" in line.upper():
            d = DATE_RE.search(line)
            if d:
                out["expiry"] = f"{d.group(1)}/{d.group(2)}/{d.group(3)}"
                break
    if "expiry" not in out:
        d = DATE_RE.search(text)
        if d:
            out["expiry"] = f"{d.group(1)}/{d.group(2)}/{d.group(3)}"
    # name after "NAMA PERSONEL"
    m = re.search(r"NAMA\s+PERSONEL\s*[:\-]?\s*([A-Z][A-Z ]{3,})", up)
    if m:
        out["name"] = m.group(1).strip()
    # country
    for code, cty in COUNTRY.items():
        if cty in up:
            out["country"] = cty
            break
    return out


# ---------------- Face crop ----------------

_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def largest_face(img, pad=0.35):
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = _CASCADE.detectMultiScale(gray, 1.1, 4, minSize=(60, 60))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    px, py = int(w * pad), int(h * pad)
    x0, y0 = max(0, x - px), max(0, y - py)
    x1, y1 = min(img.shape[1], x + w + px), min(img.shape[0], y + h + py)
    return img[y0:y1, x0:x1]


def extract_document(pdf_path):
    """Full extraction. Returns dict of submitted-doc fields + face crops (BGR)."""
    pages = pdf_to_images(pdf_path)
    full_text = []
    mrz = None
    cidb = {}
    passport_face = None
    cidb_face = None
    for p in pages:
        txt, img = _ocr(p)
        full_text.append(txt)
        if mrz is None:
            mrz = parse_mrz(txt)
        if not cidb.get("expiry") and ("CIDB" in txt.upper() or "PERSONEL BINAAN" in txt.upper()):
            cidb = {**parse_cidb(txt), **cidb} if cidb else parse_cidb(txt)
            if cidb_face is None:
                cidb_face = largest_face(img)
        if passport_face is None and img is not None:
            f = largest_face(img)
            if f is not None:
                passport_face = f
    joined = "\n".join(full_text)
    if not cidb:
        cidb = parse_cidb(joined)

    passport_no = (mrz or {}).get("passport_no")
    country_code = (mrz or {}).get("country_code")
    country = COUNTRY.get(country_code, cidb.get("country"))
    name = (mrz or {}).get("name") or cidb.get("name")

    return {
        "passport_no": passport_no,
        "name": name,
        "country": country,
        "country_code": country_code,
        "cidb_expiry": cidb.get("expiry"),
        "cidb_name": cidb.get("name"),
        "mrz_found": mrz is not None,
        "passport_face": passport_face,
        "cidb_face": cidb_face if cidb_face is not None else passport_face,
        "raw_text": joined,
    }
