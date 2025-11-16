import io
import re
from collections import Counter
from typing import List, Optional

import pdfplumber
import docx
import uvicorn
import spacy

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ----- Load spaCy-----
# If you get an error here, run:
# python -m spacy download en_core_web_sm
nlp = spacy.load("en_core_web_sm")

app = FastAPI(title="Resume Parser API")

# Allow Streamlit (localhost:8501) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------- Regexes and helpers -------
EMAIL_RE = re.compile(r"[a-zA-Z0-9.+_-]+@[a-zA-Z0-9._-]+\.[a-zA-Z]+")
PHONE_RE = re.compile(r"(\+?\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?)?\d{3,4}[\s-]?\d{3,4}")
URL_RE = re.compile(r"(https?://\S+|www\.\S+)")
GITHUB_RE = re.compile(r"(?:github\.com/)([A-Za-z0-9_\-]+)")
LINKEDIN_RE = re.compile(r"(?:linkedin\.com/in/)([A-Za-z0-9_\-]+)")

COMMON_SKILLS = [
    "python","java","c++","c#","javascript","react","node","django","flask","sql","mongodb",
    "aws","azure","gcp","docker","kubernetes","linux","git","html","css","tensorflow","pytorch",
    "nlp","cybersecurity","penetration testing","django-rest-framework","rest","machine learning",
    "data analysis","pandas","numpy","scikit-learn","deep learning"
]

def extract_text_from_pdf_bytes(data: bytes) -> str:
    text_parts = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for p in pdf.pages:
                page_text = p.extract_text()
                if page_text:
                    text_parts.append(page_text)
    except Exception:
        # fallback: try to decode as plain text
        try:
            return data.decode(errors="ignore")
        except Exception:
            return ""
    return "\n".join(text_parts)

def extract_text_from_docx_bytes(data: bytes) -> str:
    from io import BytesIO
    try:
        doc = docx.Document(BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs]
        return "\n".join(paragraphs)
    except Exception:
        try:
            return data.decode(errors="ignore")
        except Exception:
            return ""

def extract_text_from_bytes(filename: str, data: bytes) -> str:
    fname = filename.lower()
    if fname.endswith(".pdf"):
        return extract_text_from_pdf_bytes(data)
    if fname.endswith(".docx"):
        return extract_text_from_docx_bytes(data)
    if fname.endswith(".txt"):
        try:
            return data.decode(errors="ignore")
        except Exception:
            return ""
    # fallback: try pdf then text decode
    t = extract_text_from_pdf_bytes(data)
    if t.strip():
        return t
    try:
        return data.decode(errors="ignore")
    except Exception:
        return ""

def find_emails(text: str) -> List[str]:
    return list(dict.fromkeys(EMAIL_RE.findall(text)))

def find_phones(text: str) -> List[str]:
    matches = PHONE_RE.findall(text)
    # PHONE_RE captures groups; flatten and filter
    cleaned = []
    for m in PHONE_RE.finditer(text):
        phone = m.group(0).strip()
        if len(phone) >= 7:
            cleaned.append(phone)
    return list(dict.fromkeys(cleaned))

def find_urls(text: str) -> List[str]:
    return list(dict.fromkeys(URL_RE.findall(text)))

def find_github(text: str) -> List[str]:
    return list(dict.fromkeys(GITHUB_RE.findall(text)))

def find_linkedin(text: str) -> List[str]:
    return list(dict.fromkeys(LINKEDIN_RE.findall(text)))

def find_name(text: str) -> str:
    # inspect top-of-resume chunk to avoid noise
    top_chunk = "\n".join(text.splitlines()[:40])
    doc = nlp(top_chunk[:3000])
    persons = [ent.text.strip() for ent in doc.ents if ent.label_ == "PERSON"]
    if persons:
        return persons[0]
    # fallback heuristic: first line with 2 capitalized words
    for line in top_chunk.splitlines():
        tokens = [w for w in line.split() if w]
        if 1 < len(tokens) <= 6:
            caps = sum(1 for w in tokens if w[0].isupper())
            if caps >= 1:
                return line.strip()
    return ""

def find_organizations(text: str) -> List[str]:
    doc = nlp(text)
    orgs = [ent.text.strip() for ent in doc.ents if ent.label_ in ("ORG", "COMPANY")]
    return list(dict.fromkeys(orgs))

def extract_skills(text: str) -> List[str]:
    t = text.lower()
    found = [s for s in COMMON_SKILLS if s.lower() in t]
    return found

def top_terms(text: str, n: int = 15) -> List[str]:
    words = re.findall(r"\w+", text.lower())
    common = [w for w, _ in Counter(words).most_common(200) if len(w) > 2]
    return common[:n]

# ------- API endpoint -------
@app.post("/parse")
async def parse_resume(file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    contents = await file.read()
    text = extract_text_from_bytes(file.filename or "file", contents)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from this file")
    parsed = {
        "name": find_name(text),
        "emails": find_emails(text),
        "phones": find_phones(text),
        "linkedin_handles": find_linkedin(text),
        "github_handles": find_github(text),
        "urls": find_urls(text),
        "organizations": find_organizations(text)[:20],
        "skills": extract_skills(text),
        "top_terms": top_terms(text),
        "raw_text_head": "\n".join(text.splitlines()[:40])
    }
    return JSONResponse(content=parsed)

# lightweight health
@app.get("/health")
def health():
    return {"status": "ok"}

# If run directly
if __name__ == "__main__":
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
