#!/usr/bin/env python3
"""
 - Implement PDF/DOCX/text extraction 
 - OCR fallback (pdf→image + pytesseract).

"""
import io
import os
import sys
from typing import Optional
from PIL import Image, ImageFilter, ImageOps
import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes
import docx

# Optional: use python-magic if installed for MIME detection
try:
    import magic
except Exception:
    magic = None

# ------------------ Config / helpers ------------------
OCR_DPI = 300
OCR_LANG = "eng"  # change if you need other languages and installed tesseract langs
TESSERACT_CONFIG = "--psm 3"  # automatic page segmentation

def is_pdf(filename: str) -> bool:
    return filename.lower().endswith(".pdf")

def is_docx(filename: str) -> bool:
    return filename.lower().endswith(".docx") or filename.lower().endswith(".doc")

def is_image(filename: str) -> bool:
    ext = filename.lower().split(".")[-1]
    return ext in ("png", "jpg", "jpeg", "tiff", "bmp")

# ------------------ OCR preprocessing ------------------
def preprocess_pil_image(img: Image.Image) -> Image.Image:
    # convert to grayscale
    img = img.convert("L")
    # optional: remove noise / sharpen
    img = img.filter(ImageFilter.MedianFilter(size=3))
    # increase contrast / binarize
    img = ImageOps.autocontrast(img)
    return img

# ------------------ Extraction functions ------------------
def extract_text_from_pdf_bytes(data: bytes, ocr_fallback: bool = True) -> str:
    """
    Try native text extraction with pdfplumber first.
    If that yields little/no text and ocr_fallback is True, convert pages to images and OCR.
    """
    text_parts = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
    except Exception:
        # pdfplumber failed; continue to OCR fallback if enabled
        text_parts = []

    joined = "\n".join(text_parts).strip()
    if joined and len(joined) > 50:
        return joined

    # OCR fallback
    if not ocr_fallback:
        return joined
    ocr_texts = []
    try:
        images = convert_from_bytes(data, dpi=OCR_DPI)
        for img in images:
            img = preprocess_pil_image(img)
            txt = pytesseract.image_to_string(img, lang=OCR_LANG, config=TESSERACT_CONFIG)
            ocr_texts.append(txt)
    except Exception:
        # Last resort: return whatever extracted (maybe empty)
        return joined
    return "\n".join(ocr_texts).strip()

def extract_text_from_docx_bytes(data: bytes) -> str:
    try:
        from io import BytesIO
        doc = docx.Document(BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs if p.text]
        return "\n".join(paragraphs).strip()
    except Exception:
        # fallback: try decode
        try:
            return data.decode(errors="ignore")
        except Exception:
            return ""

def extract_text_from_image_bytes(data: bytes) -> str:
    try:
        img = Image.open(io.BytesIO(data))
        img = preprocess_pil_image(img)
        text = pytesseract.image_to_string(img, lang=OCR_LANG, config=TESSERACT_CONFIG)
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
    # try PDF extraction (handles many binary PDFs)
    t = extract_text_from_pdf_bytes(data)
    if t and len(t) > 10:
        return t
    # try docx
    t = extract_text_from_docx_bytes(data)
    if t and len(t) > 10:
        return t
    # try image OCR
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
    print(txt[:10000])
    print("----END TEXT----")
