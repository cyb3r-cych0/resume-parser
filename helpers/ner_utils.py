#!/usr/bin/env python3
import re
from typing import Dict, Any, List

_DEGREE_KEYWORDS = [
    r"\bBachelor(?:'s)?\b", r"\bB\.?A\.?\b", r"\bB\.?S\.?\b", r"\bBSc\b", r"\bBE\b",
    r"\bMaster(?:'s)?\b", r"\bM\.?S\.?\b", r"\bMSc\b", r"\bMBA\b", r"\bPhD\b", r"\bDoctorate\b"
]
_MAJOR_KEYWORDS = [
    "computer science", "information technology", "electrical engineering", "mechanical engineering",
    "business", "economics", "finance", "marketing", "data science", "software engineering"
]

EDU_INSTITUTION_HINTS = ["university", "college", "institute", "school", "faculty", "campus"]

def _first_entity_by_label(doc, label: str):
    for ent in doc.ents:
        if ent.label_ == label:
            return ent.text.strip()
    return None

def _all_entities_by_label(doc, label: str) -> List[str]:
    return [ent.text.strip() for ent in doc.ents if ent.label_ == label]

def _find_degree_in_text(text: str):
    for pat in _DEGREE_KEYWORDS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            # return surrounding token (short window)
            span = text[max(0, m.start()-40): m.end()+40]
            return span.strip()
    return None

def _find_major_in_text(text: str):
    for kw in _MAJOR_KEYWORDS:
        if kw in text.lower():
            return kw.title()
    # look for "Major: X" patterns
    m = re.search(r"(?:Major|Specialization|Field)\s*[:\-]\s*([A-Za-z &/]+)", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None

def extract_ner_hints(raw_text: str, nlp) -> Dict[str, Any]:
    """
    Return a compact dict of hints extracted via spaCy NER and simple regexes.
    Keys: name, orgs (list), colleges (list), degrees (list), majors (list), persons (list)
    """
    hints = {"name": None, "persons": [], "orgs": [], "colleges": [], "degrees": [], "majors": []}
    try:
        doc = nlp(raw_text)
    except Exception:
        return hints

    # persons and first person as name hint
    persons = _all_entities_by_label(doc, "PERSON")
    hints["persons"] = persons
    if persons:
        hints["name"] = persons[0]

    # orgs
    orgs = _all_entities_by_label(doc, "ORG")
    hints["orgs"] = orgs

    # attempt to find education institution lines using simple search
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    colleges = []
    for ln in lines:
        if any(k in ln.lower() for k in EDU_INSTITUTION_HINTS):
            colleges.append(ln)
    # dedupe
    hints["colleges"] = list(dict.fromkeys(colleges + orgs))[:6]

    # degrees & majors (regex / keyword scan)
    degs = []
    majors = []
    # search in lines and whole text
    for ln in lines + [raw_text]:
        d = _find_degree_in_text(ln)
        if d:
            degs.append(d)
        m = _find_major_in_text(ln)
        if m:
            majors.append(m)
    hints["degrees"] = list(dict.fromkeys(degs))[:6]
    hints["majors"] = list(dict.fromkeys(majors))[:6]
    return hints
