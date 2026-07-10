"""FastAPI app: upload PDF(s) -> extract -> CIMS lookup -> compare -> verdict."""
import base64
import os
import tempfile

import cv2
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import extract
import cims
import compare

app = FastAPI(title="CIDB Personnel Document Verifier")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")


def _b64(face):
    if face is None:
        return None
    ok, buf = cv2.imencode(".jpg", face)
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode() if ok else None


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(FRONTEND, "index.html")) as f:
        return f.read()


@app.post("/verify")
async def verify(files: list[UploadFile] = File(...),
                 is_foreign: bool = Form(True)):
    results = []
    for uf in files:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.write(await uf.read())
        tmp.close()
        try:
            sub = extract.extract_document(tmp.name)
            if not sub.get("passport_no"):
                results.append({"file": uf.filename, "error":
                                "Could not read passport number (MRZ) from PDF",
                                "submitted": _pub(sub)})
                continue
            web = cims.lookup(sub["passport_no"], sub.get("country"),
                              is_foreign=is_foreign)
            report = compare.verify(sub, web)
            report["file"] = uf.filename
            report["submitted"] = _pub(sub)
            report["website"] = _pubw(web)
            report["photos"] = {"submitted": _b64(sub.get("passport_face")),
                                "website": _b64(web.get("face"))}
            results.append(report)
        finally:
            os.unlink(tmp.name)
    return {"results": results}


def _pub(sub):
    return {k: sub.get(k) for k in ("passport_no", "name", "country",
                                    "cidb_expiry", "mrz_found")}


def _pubw(web):
    return {k: web.get(k) for k in ("found", "name", "country", "expiry",
                                    "trade", "passport_masked", "consignment",
                                    "error")}
