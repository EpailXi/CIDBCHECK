"""Look up a construction personnel on the official CIMS CIDB system.

Instead of driving the website with a browser (heavy, needs Chromium, OOMs on
small hosts), we call the same JSON web-service the site's own front-end uses:

  GET /PBSearchv3/dataservice.asmx/searchTred   ?searchvalue=<passport>&country=<code>
      -> [{PersonId, TredCode, TredDescription}]         (trade + proves record exists)
  GET /PBSearchv3/dataservice.asmx/searchHistory?searchvalue=<passport>&country=<code>&lang=ms
      -> [{Cardstart, Cardend, RegProcessDescription}]    (Cardend = registration expiry)
  GET /pbimage/<code><passport>-1.jpg                     (the registration photo)
  GET /PBSearchv3/dataservice.asmx/GetNat                 (country name -> code map)

All are token-auth'd with the public tokens the site ships (tokenid/tokenpass=cims).
CIMS remains the reference point. The personnel *name* is only rendered on the
server-side result page (behind an encrypted token) and is not exposed by the
JSON API, so name is reported as unavailable and the verdict leans on record
existence + expiry + photo + country.
"""
import cv2
import numpy as np
import httpx

BASE = "https://cims.cidb.gov.my/PBSearchv3/dataservice.asmx"
IMG = "https://cims.cidb.gov.my/pbimage"
TOK = {"tokenid": "cims", "tokenpass": "cims"}

_NAT_CACHE = {}

# fallback map (name -> CIMS CountryCode) if GetNat is unreachable
_FALLBACK = {"BANGLADESH": "BGL", "INDONESIA": "IND", "INDIA": "INA",
             "NEPAL": "NEP", "MYANMAR": "MYA", "PAKISTAN": "PAK",
             "VIETNAM": "VIE", "PHILIPPINES": "PHI", "CAMBODIA": "CAM",
             "SRI LANKA": "SRI", "THAILAND": "THA"}


def _client():
    return httpx.Client(timeout=30, headers={"User-Agent": "Mozilla/5.0"},
                        verify=True)


def _country_code(name, client):
    if not name:
        return None
    key = name.strip().upper()
    if not _NAT_CACHE:
        try:
            r = client.get(f"{BASE}/GetNat", params=TOK)
            for row in (r.json().get("data") or r.json()):
                _NAT_CACHE[row["Countryname"].strip().upper()] = row["CountryCode"]
        except Exception:
            _NAT_CACHE.update(_FALLBACK)
    if key in _NAT_CACHE:
        return _NAT_CACHE[key]
    for cname, code in _NAT_CACHE.items():          # partial match
        if key in cname or cname in key:
            return code
    return _FALLBACK.get(key)


def _rows(resp):
    try:
        j = resp.json()
        return j.get("data", j) if isinstance(j, dict) else j
    except Exception:
        return []


def lookup(passport_no, country_name=None, is_foreign=True, timeout=30):
    result = {"found": False, "name": None, "country": country_name,
              "expiry": None, "trade": None, "passport_masked": None,
              "face": None, "consignment": None, "error": None}
    if not passport_no:
        result["error"] = "No passport number"
        return result
    try:
        with _client() as c:
            ct = _country_code(country_name, c) if is_foreign else "MYS"
            if not ct:
                result["error"] = f"Unknown country code for '{country_name}'"
                return result
            result["country_code"] = ct
            q = {**TOK, "searchvalue": passport_no, "country": ct}

            tred = _rows(c.get(f"{BASE}/searchTred", params=q))
            hist = _rows(c.get(f"{BASE}/searchHistory",
                               params={**q, "lang": "ms"}))

            result["found"] = bool(tred or hist)
            if not result["found"]:
                result["error"] = "No record in CIMS for this passport/country"
                return result

            if tred:
                result["trade"] = ", ".join(
                    sorted({r.get("TredDescription", "").strip()
                            for r in tred if r.get("TredDescription")}))
            # expiry = latest Cardend
            ends = [r.get("Cardend") for r in hist if r.get("Cardend")]
            if ends:
                result["expiry"] = _latest_date(ends)

            # masked passport, mirroring the site's display (first 2 + last 2)
            p = passport_no.upper()
            if len(p) > 4:
                result["passport_masked"] = p[:2] + "*" * (len(p) - 4) + p[-2:]

            # photo
            try:
                pr = c.get(f"{IMG}/{ct}{passport_no}-1.jpg")
                if pr.status_code == 200 and pr.content:
                    arr = np.frombuffer(pr.content, np.uint8)
                    result["face"] = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            except Exception:
                pass
    except Exception as e:
        result["error"] = str(e)
    return result


def _latest_date(strings):
    from datetime import datetime
    best, best_s = None, strings[0]
    for s in strings:
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                d = datetime.strptime(s.strip(), fmt)
                if best is None or d > best:
                    best, best_s = d, s.strip()
                break
            except ValueError:
                continue
    return best_s
