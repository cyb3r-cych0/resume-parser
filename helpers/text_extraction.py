#!/usr/bin/env python3
"""
 - Implement PDF/DOCX/text extraction
 - OCR fallback (pdf→image + pytesseract).
"""
import io
import os
import re
import sys
import docx
import math
import pdfplumber
import pytesseract
from typing import List
from pdf2image import convert_from_bytes
from PIL import Image, ImageFilter, ImageOps
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Optional: use python-magic if installed for MIME detection
try:
    import magic
except Exception:
    magic = None

# Optional OpenCV + numpy accelerated preprocessing
try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False

# ------------------ Config / helpers ------------------
# Default DPI lowered to 200 for faster conversions; override with env var OCR_DPI if needed
OCR_DPI = int(os.getenv("OCR_DPI", "200"))

# Reduce PSM candidates to the most useful two (faster). If you want more accuracy, set env or restore list.
TESSERACT_PSM_CANDIDATES = [
    "--psm 1 --oem 3",  # Automatic page segmentation with OSD
    "--psm 3 --oem 3"   # Fully automatic page segmentation
]

# OCR_DPI = 300
OCR_LANG = "eng"  # change if you need other languages and installed tesseract langs
# Tesseract PSM modes to experiment with; default is 3 (fully automatic)
TESSERACT_CONFIG = "--psm 3 --oem 3"

def score_text_quality(text: str) -> float:
    """
    Lightweight heuristic score for OCR text quality.
    Higher is better.
    """
    if not text:
        return 0.0
    tokens = [t for t in re.split(r"\s+", text) if t]
    word_count = len(tokens)
    if word_count == 0:
        return 0.0
    alpha_tokens = [t for t in tokens if any(c.isalpha() for c in t) and len(t) > 1]
    alpha_ratio = len(alpha_tokens) / word_count
    # prefer results with reasonable alphabetic content and more words
    return alpha_ratio * math.log(1 + word_count)

def ocr_with_multiple_psm(pil_img: Image.Image, lang: str = OCR_LANG, psm_candidates: List[str] = None) -> str:
    """
    Run pytesseract on a PIL image using multiple psm configs and pick the best output by score.
    Returns the best OCR text (string).
    """
    if psm_candidates is None:
        psm_candidates = TESSERACT_PSM_CANDIDATES

    best_text = ""
    best_score = -1.0
    for cfg in psm_candidates:
        try:
            txt = pytesseract.image_to_string(pil_img, lang=lang, config=cfg)
            sc = score_text_quality(txt)
            if sc > best_score:
                best_score = sc
                best_text = txt
        except Exception:
            # if one mode errors, ignore and continue
            continue

    # fallback: if nothing produced a positive score, run default once
    if not best_text:
        try:
            best_text = pytesseract.image_to_string(pil_img, lang=lang, config=TESSERACT_CONFIG)
        except Exception:
            best_text = ""
    return best_text.strip()

def is_pdf(filename: str) -> bool:
    return filename.lower().endswith(".pdf")

def is_docx(filename: str) -> bool:
    return filename.lower().endswith(".docx") or filename.lower().endswith(".doc")

def is_image(filename: str) -> bool:
    ext = filename.lower().split(".")[-1]
    return ext in ("png", "jpg", "jpeg", "tiff", "bmp")

# ------------------ OpenCV preprocessing helpers ------------------
def deskew_and_binarize(pil_img: Image.Image) -> Image.Image:
    """
    Deskew + denoise + adaptive threshold using OpenCV.
    Returns a PIL Image (mode 'L') suitable for pytesseract.
    If OpenCV not available, raises ImportError.
    """
    if not _HAS_CV2:
        raise ImportError("OpenCV not available")

    # convert to grayscale numpy array
    arr = np.array(pil_img.convert("L"))
    # compute median blur to reduce noise
    blur = cv2.medianBlur(arr, 3)

    # estimate skew angle via Hough or minAreaRect on edges
    edges = cv2.Canny(blur, 50, 150)
    coords = np.column_stack(np.where(edges > 0))
    angle = 0.0
    if coords.shape[0] >= 10:
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]
        # adjust angle returned by minAreaRect into deskew rotation
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

    # rotate image to deskew
    (h, w) = arr.shape
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    rotated = cv2.warpAffine(arr, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    # adaptive threshold to binarize
    try:
        th = cv2.adaptiveThreshold(rotated, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 15, 9)
    except Exception:
        # fallback Otsu
        _, th = cv2.threshold(rotated, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # morphological open to remove small noise
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1,1))
    cleaned = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel)
    return Image.fromarray(cleaned)

def ensure_pil_mode(img: Image.Image) -> Image.Image:
    if img.mode != "RGB" and img.mode != "L":
        return img.convert("RGB")
    return img

# ------------------ OCR preprocessing ------------------
def preprocess_pil_image(img: Image.Image) -> Image.Image:
    """
    Preprocess a PIL image for OCR.
    Tries OpenCV deskew + binarize if available, else falls back to PIL filters.
    Returns a grayscale PIL Image.
    """
    img = ensure_pil_mode(img)
    # try OpenCV pipeline for best results
    if _HAS_CV2:
        try:
            out = deskew_and_binarize(img)
            return out
        except Exception:
            # fallback to PIL-based if something goes wrong
            pass

    # PIL fallback: convert to grayscale, median denoise, autocontrast
    img = img.convert("L")
    img = img.filter(ImageFilter.MedianFilter(size=3))
    img = ImageOps.autocontrast(img)
    return img

def extract_text_from_pdf_bytes(data: bytes, ocr_fallback: bool = True) -> str:
    """
    Try native text extraction with pdfplumber first.
    If that yields little/no text and ocr_fallback is True, convert pages to images and OCR.
    Uses multi-PSM selection per page.
    """
    text_parts = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
    except Exception:
        text_parts = []

    joined = "\n".join(text_parts).strip()
    if joined and len(joined) > 50:
        return joined
    if not ocr_fallback:
        return joined

    # OCR fallback with multi-psm per page
    ocr_texts = []
    try:
        images = convert_from_bytes(data, dpi=OCR_DPI)
        for img in images:
            img = preprocess_pil_image(img)
            # try multiple PSM configs and pick the best
            txt = ocr_with_multiple_psm(img)
            ocr_texts.append(txt)
    except Exception:
        # if conversion fails, return whatever we had
        return joined
    return "\n".join(ocr_texts).strip()

def extract_text_from_docx_bytes(data: bytes) -> str:
    try:
        from io import BytesIO
        doc = docx.Document(BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs if p.text]
        return "\n".join(paragraphs).strip()
    except Exception:
        try:
            return data.decode(errors="ignore")
        except Exception:
            return ""

def extract_text_from_image_bytes(data: bytes) -> str:
    try:
        img = Image.open(io.BytesIO(data))
        img = preprocess_pil_image(img)
        # choose best PSM result for this image
        text = ocr_with_multiple_psm(img)
        return text.strip()
    except Exception:
        try:
            return data.decode(errors="ignore")
        except Exception:
            return ""

def extract_text_from_bytes(filename: str, data: bytes, use_magic: bool = True) -> str:
    """
    Master function: detect type and extract text.
    """
    # try magic if available and requested
    if magic and use_magic:
        try:
            m = magic.from_buffer(data, mime=True)
            if m and "pdf" in m:
                return extract_text_from_pdf_bytes(data)
            if m and ("word" in m or "msword" in m):
                return extract_text_from_docx_bytes(data)
            if m and ("jpeg" in m or "png" in m or "tiff" in m):
                return extract_text_from_image_bytes(data)
        except Exception:
            pass

    # fallback to extension detection
    if filename:
        if is_pdf(filename):
            return extract_text_from_pdf_bytes(data)
        if is_docx(filename):
            return extract_text_from_docx_bytes(data)
        if is_image(filename):
            return extract_text_from_image_bytes(data)

    # last resorts
    t = extract_text_from_pdf_bytes(data)
    if t and len(t) > 10:
        return t
    t = extract_text_from_docx_bytes(data)
    if t and len(t) > 10:
        return t
    return extract_text_from_image_bytes(data)

# ------------------ CLI quick-test ------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python helpers/text_extraction.py /path/to/file")
        sys.exit(1)
    path = sys.argv[1]
    with open(path, "rb") as f:
        b = f.read()
    print("Extracting:", path)
    txt = extract_text_from_bytes(os.path.basename(path), b, use_magic=False)
    print("----BEGIN TEXT----")
    print(txt[:20000])
    print("----END TEXT----")
