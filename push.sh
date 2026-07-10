#!/usr/bin/env bash
# One-command push to GitHub. Run from inside this folder:  bash push.sh
set -e
REPO="https://github.com/EpailXi/CIDBCHECK.git"

git init
git add -A
git commit -m "CIDB personnel document verifier: MRZ+OCR extraction, CIMS lookup, comparison engine, web UI"
git branch -M main
git remote remove origin 2>/dev/null || true
git remote add origin "$REPO"
git push -u origin main
echo "Done -> $REPO"
