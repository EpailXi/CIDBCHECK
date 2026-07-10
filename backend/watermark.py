"""Apply a CIMS-style translucent watermark to the submitted photo so it can be
compared like-for-like against the CIDB website photo (which carries the overlay).
"""
import cv2
import numpy as np


def apply_watermark(face_bgr, opacity=0.35):
    """Overlay a translucent hexagon/diagonal pattern mimicking the CIMS overlay.

    We don't need CIDB's exact asset: the goal is to depress contrast and add a
    central mark the same way the website does, so both photos are degraded
    similarly before comparison.
    """
    if face_bgr is None:
        return None
    img = face_bgr.copy()
    h, w = img.shape[:2]
    overlay = np.full_like(img, 200)  # light grey wash

    # central hexagon outline (approx CIDB mark)
    cx, cy, r = w // 2, h // 2, int(min(w, h) * 0.32)
    pts = np.array([[cx + int(r * np.cos(a)), cy + int(r * np.sin(a))]
                    for a in np.linspace(0, 2 * np.pi, 7)], np.int32)
    cv2.polylines(overlay, [pts], True, (120, 150, 150), max(2, r // 12))

    # faint diagonal band
    cv2.line(overlay, (0, h), (w, 0), (150, 170, 170), max(2, w // 20))

    return cv2.addWeighted(overlay, opacity, img, 1 - opacity, 0)


def normalize(face_bgr, size=200):
    """Resize + grayscale + CLAHE so lighting/scale differences don't dominate."""
    if face_bgr is None:
        return None
    g = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (size, size))
    return cv2.createCLAHE(2.0, (8, 8)).apply(g)
