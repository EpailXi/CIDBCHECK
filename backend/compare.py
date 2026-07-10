"""Comparison engine. CIMS website is the authoritative reference.

Checks:
  - country     : exact (normalized)
  - name        : fuzzy (token set ratio)
  - expiry      : exact date match
  - photo       : watermark-normalized similarity (ADVISORY)

Verdict: LEGIT only if the authoritative fields (name, expiry, country) all pass
and the passport tail matches. Photo is reported but weighted as advisory because
the website image is watermarked and low-resolution.
"""
import re
from datetime import datetime

import cv2
import numpy as np
from difflib import SequenceMatcher

from watermark import apply_watermark, normalize

NAME_THRESHOLD = 0.85
PHOTO_THRESHOLD = 0.32


def _norm_name(s):
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z ]", "", (s or "").upper())).strip()


def name_similarity(a, b):
    ta, tb = set(_norm_name(a).split()), set(_norm_name(b).split())
    if not ta or not tb:
        return 0.0
    token = len(ta & tb) / len(ta | tb)
    seq = SequenceMatcher(None, _norm_name(a), _norm_name(b)).ratio()
    return round(max(token, seq), 3)


def _parse_date(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def dates_match(a, b):
    da, db = _parse_date(a), _parse_date(b)
    if da and db:
        return da == db
    return _norm_digits(a) == _norm_digits(b) and bool(_norm_digits(a))


def _norm_digits(s):
    return re.sub(r"\D", "", s or "")


def passport_match(submitted, website):
    """Website masks middle digits e.g. A2*****98. Compare visible chars only."""
    s = (submitted or "").upper().replace(" ", "")
    w = (website or "").upper().replace(" ", "")
    if not s or not w:
        return None
    if "*" not in w:
        return s == w
    if len(s) != len(w):
        return False
    return all(wc == "*" or wc == sc for sc, wc in zip(s, w))


def photo_similarity(submitted_face, website_face):
    """Watermark-normalized similarity in [0,1]. Advisory only."""
    if submitted_face is None or website_face is None:
        return None
    a = normalize(apply_watermark(submitted_face))  # match the website's overlay
    b = normalize(website_face)
    if a is None or b is None:
        return None

    # 1) histogram correlation
    ha = cv2.calcHist([a], [0], None, [64], [0, 256])
    hb = cv2.calcHist([b], [0], None, [64], [0, 256])
    cv2.normalize(ha, ha); cv2.normalize(hb, hb)
    hist = max(0.0, cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL))

    # 2) ORB feature match ratio (structure survives watermark better)
    orb = cv2.ORB_create(400)
    ka, da = orb.detectAndCompute(a, None)
    kb, db = orb.detectAndCompute(b, None)
    feat = 0.0
    if da is not None and db is not None and len(ka) and len(kb):
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(da, db)
        good = [m for m in matches if m.distance < 64]
        feat = len(good) / max(len(ka), len(kb))

    return round(0.5 * hist + 0.5 * min(1.0, feat * 3), 3)


def verify(submitted, website):
    """submitted: dict from extract; website: dict from cims.lookup.
    Returns full comparison report + verdict."""
    checks = {}

    checks["country"] = {
        "submitted": submitted.get("country"),
        "website": website.get("country"),
        "match": _norm_name(submitted.get("country")) == _norm_name(website.get("country"))
                 and bool(website.get("country")),
    }

    nsub = submitted.get("name")
    nweb = website.get("name")
    nsim = name_similarity(nsub, nweb)
    checks["name"] = {"submitted": nsub, "website": nweb,
                      "similarity": nsim, "match": nsim >= NAME_THRESHOLD}

    checks["expiry"] = {
        "submitted": submitted.get("cidb_expiry"),
        "website": website.get("expiry"),
        "match": dates_match(submitted.get("cidb_expiry"), website.get("expiry")),
    }

    pm = passport_match(submitted.get("passport_no"), website.get("passport_masked"))
    checks["passport"] = {"submitted": submitted.get("passport_no"),
                          "website": website.get("passport_masked"),
                          "match": pm}

    psim = photo_similarity(submitted.get("passport_face"),
                            website.get("face"))
    checks["photo"] = {"similarity": psim,
                       "match": (psim is not None and psim >= PHOTO_THRESHOLD),
                       "advisory": True}

    authoritative = [checks["name"]["match"], checks["expiry"]["match"],
                     checks["country"]["match"]]
    if pm is not None:
        authoritative.append(pm)

    if not website.get("found"):
        verdict = "NOT_FOUND"
    elif all(authoritative):
        verdict = "LEGIT"
    else:
        verdict = "MISMATCH"

    return {"verdict": verdict, "checks": checks,
            "reference": "CIMS CIDB website"}
