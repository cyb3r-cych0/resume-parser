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
from typing import Dict, List
from collections import defaultdict

# Lazy import for sentence-transformers
_MODEL = None
_EMBEDDINGS = None
_CANONICAL_HEADINGS = {
    "education": ["education", "academic", "academic background", "education and qualifications", "education & qualifications", "education & training"],
    "experience": ["experience", "work experience", "professional experience", "employment history", "work history"],
    "skills": ["skills", "technical skills", "skills & technologies", "key skills"],
    "certifications": ["certifications", "certificates", "professional certifications"],
    "publications": ["publications", "research", "papers", "research publications"],
    "achievements": ["achievements", "awards", "honors", "distinctions"],
    "extracurricular": ["extracurricular", "extra-curricular", "activities", "interests", "extracurricular activities"],
    "test_scores": ["test scores", "scores", "standardized tests", "exams"],
    "summary": ["summary", "profile", "professional summary", "objective", "career objective"],
    "contact": ["contact", "contact information", "personal details"]
}

def _init_embedding_model():
    global _MODEL, _EMBEDDINGS, _CANONICAL_LABELS
    if _MODEL is not None:
        return
    try:
        from sentence_transformers import SentenceTransformer, util
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        # precompute canonical heading embeddings
        all_canonical = []
        for k, variants in _CANONICAL_HEADINGS.items():
            # store canonical label + some variants
            all_canonical.append(("__label__"+k, " ; ".join(variants)))
        texts = [t for (_, t) in all_canonical]
        _EMBEDDINGS = _MODEL.encode(texts, convert_to_tensor=True)
        _CANONICAL_LABELS = [lbl for (lbl, _) in all_canonical]
        # store labels on the model too for later lookup
        _MODEL._labels = _CANONICAL_LABELS
    except Exception:
        _MODEL = None
        _EMBEDDINGS = None
        _CANONICAL_LABELS = []

def _score_and_label_heading(heading_text: str):
    """
    Returns canonical label (e.g., 'education') and similarity score.
    If model not available, returns (None, 0.0).
    """
    _init_embedding_model()
    if not _MODEL:
        return None, 0.0
    from sentence_transformers import util
    q_emb = _MODEL.encode(heading_text, convert_to_tensor=True)
    sims = util.cos_sim(q_emb, _EMBEDDINGS)  # shape (1, N)
    best_idx = int(sims.argmax())
    best_score = float(sims[0][best_idx])
    label_token = _MODEL._labels[best_idx]
    label = label_token.replace("__label__", "")
    return label, best_score

# --- regex based fallback heading detection (older approach) ---
HEADING_KEYS = {
    "education": r"(education|academic|qualification|degree)",
    "experience": r"(experience|employment|work history|professional experience)",
    "skills": r"(skills|technical skills|competenc)",
    "certifications": r"(certif|certificate)",
    "publications": r"(publication|paper|journal|conference)",
    "achievements": r"(award|achievement|honor|distinction)",
    "extracurricular": r"(extracurricular|activities|interests)",
    "test_scores": r"(toefl|ielts|gre|gmat|sat|act|test score|scores)",
    "summary": r"(summary|objective|profile)",
    "contact": r"(contact|personal details|address|phone)"
}

HEADING_RE = re.compile(r"^[A-Z][A-Za-z\s\&\-]{2,60}$")

def split_into_sections(text: str) -> Dict[str, str]:
    """
    Splits raw text into sections. Uses embedding-based heading classification when available.
    Returns dict keyed by canonical sections and a 'top' / 'other' fallback.
    """
    if not text or not text.strip():
        return {}

    lines = [ln.rstrip() for ln in text.splitlines()]
    # merge into paragraphs by blank-line separation for candidate headings
    paragraphs = []
    cur = []
    for ln in lines:
        if ln.strip() == "":
            if cur:
                paragraphs.append("\n".join(cur).strip())
                cur = []
        else:
            cur.append(ln)
    if cur:
        paragraphs.append("\n".join(cur).strip())

    # Candidate headings detection: a paragraph that's short (<=6 words) and either matches heading regex
    candidates = []
    for i, p in enumerate(paragraphs):
        words = p.split()
        lowp = p.lower()
        if len(words) <= 6 and len(p) <= 60:
            # treat as heading candidate
            # check heading pattern OR any canonical heading keyword (iterating the list variants)
            if HEADING_RE.match(p) or any(k in lowp for variants in _CANONICAL_HEADINGS.values() for k in variants):
                candidates.append((i, p))

    # If no candidates, fallback: try line-level heading detection (short uppercase-ish lines)
    if not candidates:
        for i, p in enumerate(paragraphs):
            first_line = p.splitlines()[0]
            if HEADING_RE.match(first_line):
                candidates.append((i, first_line))

    # classify each candidate
    sections = defaultdict(list)
    assigned_indices = set()
    for idx, heading in candidates:
        label, score = _score_and_label_heading(heading)
        if label and score >= 0.45:
            # strong semantic match
            sections[label].append(idx)
            assigned_indices.add(idx)
        else:
            # regex fallback: check HEADING_KEYS
            low = heading.lower()
            found = False
            for k, r in HEADING_KEYS.items():
                if re.search(r, low):
                    sections[k].append(idx)
                    assigned_indices.add(idx)
                    found = True
                    break
            if not found:
                # leave unassigned for 'other'
                pass

    # Now build section text by gathering paragraphs between headings
    result = {}
    # create a mapping from index to canonical section label (first label if multiple)
    idx2label = {}
    for label, idxs in sections.items():
        for i in idxs:
            idx2label[i] = label

    # If we have any headings, walk through paragraphs and aggregate content into sections
    if idx2label:
        current_label = "top"
        for i, p in enumerate(paragraphs):
            if i in idx2label:
                current_label = idx2label[i]
                # initialize if first time
                result.setdefault(current_label, "")
                # remove heading from body (we'll not include heading text as content)
                continue
            result.setdefault(current_label, "")
            # append paragraph content
            result[current_label] = (result[current_label] + "\n\n" + p).strip()
    else:
        # fallback: naive split into top + other
        joined = "\n\n".join(paragraphs)
        # try to split by keywords for education/experience
        low = joined.lower()
        if "education" in low:
            # split around 'education'
            parts = re.split(r"(education|experience|skills|certif|publications|achievement)", joined, flags=re.I)
            # naive assign: before first keyword -> top; rest go to other
            result["top"] = parts[0].strip()
            result["other"] = "\n".join(parts[1:]).strip()
        else:
            result["top"] = joined

    # ensure all canonical keys exist (empty if not found)
    for k in _CANONICAL_HEADINGS.keys():
        result.setdefault(k, "")

    # always include 'top' and 'other'
    result.setdefault("top", "")
    result.setdefault("other", "")
    return result
