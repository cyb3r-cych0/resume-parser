#!/usr/bin/env python3
"""
Simple layout/heading detector and section splitter.
Detects headings and split the raw text into:
 - Education /
 - Experience /
 - Certifications /
 - Tests /

Returns a normalized dict you’ll use for field extraction.

Usage:
  from helpers.section_segmentation import split_into_sections
  sections = split_into_sections(raw_text)
  print(sections['education'])

Section segmentation with embedding-based heading classification.
Graceful fallback to regex heading detection if sentence-transformers not installed.
"""

import re
from collections import OrderedDict
from difflib import SequenceMatcher

# Optional embedding support: only used if sentence-transformers is installed and available locally.
try:
    from sentence_transformers import SentenceTransformer
    _SENTENCE_EMBED_MODEL = SentenceTransformer("models/all-MiniLM-L6-v2", local_files_only=True)
    _USE_EMBED = True
except Exception:
    _SENTENCE_EMBED_MODEL = None
    _USE_EMBED = False

# canonical headings map (expand as needed)
_CANONICAL_HEADINGS = {
    "contact": ["contact", "contact information", "personal info", "contact details"],
    "summary": ["summary", "professional summary", "profile", "about me", "career summary"],
    "education": ["education", "academic background", "educational background", "education & qualifications"],
    "experience": ["experience", "work experience", "professional experience", "employment history", "experience & roles"],
    "skills": ["skills", "technical skills", "key skills", "competencies"],
    "projects": ["projects", "relevant projects"],
    "certifications": ["certifications", "certificates", "licenses"],
    "publications": ["publications", "research", "papers"],
    "achievements": ["achievements", "honors", "awards"],
    "extracurricular": ["extra curricular", "extracurricular activities", "activities"],
    "test_scores": ["test scores", "exams", "scores"],
    "languages": ["languages", "language proficiency"],
    "interests": ["interests", "hobbies"]
}

# Flatten canonical variants for quick lookup
_CANON_FLAT = {v: k for k, variants in _CANONICAL_HEADINGS.items() for v in variants}

def _clean_line(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s

def _fuzzy_score(a: str, b: str) -> float:
    # normalized ratio 0..1
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def _best_heading_match(candidate: str, threshold=0.75):
    """
    Returns canonical key name (e.g., 'education') if candidate matches any known heading,
    otherwise returns None. Tries exact / substring / fuzzy / embedding (if available).
    """
    if not candidate:
        return None
    c = candidate.lower()
    # exact or contains
    for variant, key in _CANON_FLAT.items():
        if variant in c or c in variant:
            return key

    # fuzzy compare against variants
    best = (None, 0.0)
    for variant, key in _CANON_FLAT.items():
        score = _fuzzy_score(c, variant)
        if score > best[1]:
            best = (key, score)
            if score >= threshold:
                return key

    # fallback to embedding similarity if available
    if _USE_EMBED and len(candidate.split()) <= 6:  # short headings only
        try:
            cand_emb = _SENTENCE_EMBED_MODEL.encode([candidate], convert_to_numpy=True)[0]
            # compare against each canonical phrase (compute embeddings lazily)
            # build cache on module-level to avoid repeated computations
            if not hasattr(_best_heading_match, "_emb_cache"):
                _best_heading_match._emb_cache = {}
                for variant in _CANON_FLAT.keys():
                    _best_heading_match._emb_cache[variant] = _SENTENCE_EMBED_MODEL.encode([variant], convert_to_numpy=True)[0]
            best_emb = (None, -1.0)
            for variant, emb in _best_heading_match._emb_cache.items():
                # cosine similarity
                import numpy as _np
                sim = float((_np.dot(cand_emb, emb) / (_np.linalg.norm(cand_emb) * _np.linalg.norm(emb) + 1e-12)))
                if sim > best_emb[1]:
                    best_emb = (_CANON_FLAT[variant], sim)
            if best_emb[1] > 0.62:
                return best_emb[0]
        except Exception:
            pass

    # no good match
    return None

def split_into_sections(text: str) -> OrderedDict:
    """
    Improved section splitter:
    - Only treats SHORT lines as candidate headings
    - Rejects lines containing emails, URLs, phone numbers
    - Avoids pushing degree/program sentences into Education headings
    """
    if not text or not text.strip():
        return OrderedDict()

    lines = [_clean_line(l) for l in text.splitlines()]
    lines = [l for l in lines if l]

    sections = OrderedDict()
    current = "header"
    sections[current] = []

    EMAIL_RE = re.compile(r"\S+@\S+")
    URL_RE = re.compile(r"https?://\S+")
    PHONE_RE = re.compile(r"\+?\d[\d\- ]{6,}")

    for line in lines:
        wc = len(line.split())
        is_caps = (line.isupper() and wc <= 8)
        is_short = wc <= 5 and len(line) < 45
        has_colon = line.endswith(":")
        is_bullet = re.match(r"^[-•*]\s+", line)

        looks_heading = (is_caps or is_short or has_colon) and not is_bullet

        # Reject noisy headings
        if looks_heading:
            if EMAIL_RE.search(line) or URL_RE.search(line) or PHONE_RE.search(line):
                looks_heading = False
            if wc > 5:  # too long = not a heading
                looks_heading = False

        if looks_heading:
            cand = line.rstrip(":").strip()
            mapped = _best_heading_match(cand)

            # Accept canonical matches
            if mapped:
                current = mapped
                sections.setdefault(current, [])
                continue

            # If unknown heading → accept only if super short
            if wc <= 3:
                current = cand.lower()
                sections.setdefault(current, [])
                continue

        # Otherwise → content
        sections.setdefault(current, []).append(line)

    out = OrderedDict()
    for k, v in sections.items():
        out[k] = "\n".join(v).strip()
    return out
