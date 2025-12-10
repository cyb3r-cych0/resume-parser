#!/usr/bin/env python3
"""
Extracts contact info, education blocks (UG/PG/High school),
test scores, certifications, activities, work experience stubs,
and returns a JSON matching your schema.

"""
import re
from typing import Dict, Any, List, Tuple
import dateparser
import spacy
import os

# Limit torch threads to avoid CPU oversubscription during multiprocessing/batch runs.
# Set env var TORCH_THREADS to override (e.g., export TORCH_THREADS=2).
try:
    import torch
    torch.set_num_threads(max(1, int(os.getenv("TORCH_THREADS", "1"))))
except Exception:
    # torch not installed or setting failed — ignore
    pass

# lazy spaCy loader - reuses earlier approach
_NLP = None
def get_nlp():
    global _NLP
    if _NLP is not None:
        return _NLP
    """             
    try:
        _NLP = spacy.load("en_core_web_trf", disable=["parser", "textcat", "attribute_ruler", "lemmatizer"])
    except Exception:
        _NLP = spacy.load("en_core_web_sm", disable=["parser", "textcat", "attribute_ruler", "lemmatizer"])
    except Exception:
        _NLP = None
    """
    try:
        _NLP = spacy.load("en_core_web_lg", disable=["parser", "textcat", "attribute_ruler", "lemmatizer"])
    except Exception:
        _NLP = None
    return _NLP

# ---------- regexes and expanded degree/major lists ----------
EMAIL_RE = re.compile(r"[a-zA-Z0-9.+_-]+@[a-zA-Z0-9._-]+\.[a-zA-Z]+")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s\-\.])?(?:\(?\d{2,4}\)?[\s\-\.])?\d{3,4}[\s\-\.]?\d{3,4}")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
DATE_RANGE_RE = re.compile(r"(\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}\b|\b\d{4}\b)\s*[\-–—to]+\s*(\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}\b|\b\d{4}\b)", re.I)

UG_DEGREE_KEYWORDS = [
    "bachelor", "b\\.sc", "bsc", "b\\.tech", "btech", "bachelor of", "b\\.e", "b\\.eng", "bs in", "ba ", "beng",
    "b.e.", "b.s", "b.s.", "bba", "bfa", "barch"
]
PG_DEGREE_KEYWORDS = [
    "master", "m\\.sc", "msc", "mtech", "m\\.tech", "m\\.e", "mba", "ms ", "m\\.s", "m.eng", "m.e.", "mphil", "mres"
]

MAJOR_KEYWORDS = [
    "computer science", "information technology", "software engineering", "electrical engineering", "mechanical engineering",
    "civil engineering", "data science", "computer engineering", "electronics", "mathematics", "physics", "chemistry",
    "business administration", "finance", "economics", "biology", "biotechnology"
]

HS_KEYWORDS = ["high school", "secondary school", "senior secondary", "class 12", "grade 12", "higher secondary", "school"]

PERCENT_RE = re.compile(r"(?P<val>\d{1,3}(?:\.\d{1,2})?)\s?%")
GPA_RE = re.compile(r"(?P<val>\d+(\.\d+)?)(?:\s*/\s*(?P<scale>\d+(\.\d+)?))?")

def first_or_empty(lst):
    return lst[0] if lst else ""

def _shorten_for_ner(text: str, max_chars: int = 3000) -> str:
    """
    Keep only the first max_chars characters for transformer NER to avoid slow processing.
    Shortens on sentence boundary if possible.
    """
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    # try to cut at last blank-line or sentence end before max_chars
    cut = text[:max_chars]
    last_break = max(cut.rfind("\n\n"), cut.rfind(". "), cut.rfind("\n"), max_chars-1)
    return cut[:last_break+1] if last_break > 0 else cut

# ---------- improved name extraction ----------
def extract_name_from_top(top_text: str) -> str:
    nlp = get_nlp()
    # try spaCy PERSON extraction first
    if nlp and top_text:
        try:
            doc = nlp(_shorten_for_ner(top_text, max_chars=1000))
            persons = [ent.text.strip() for ent in doc.ents if ent.label_ == "PERSON"]
            # prefer a PERSON entity that appears near the top of the document
            if persons:
                for p in persons:
                    if len(p.split()) >= 2:
                        return p
                return persons[0]
        except Exception:
            pass

    # heuristic fallback: prefer the first non-empty line that looks like a name
    lines = [l.strip() for l in top_text.splitlines() if l.strip()]
    if not lines:
        return ""
    # common pattern: name is the first prominent line (capitalized, not containing email/phone)
    for ln in lines[:6]:
        if EMAIL_RE.search(ln) or PHONE_RE.search(ln) or len(ln) < 2:
            continue
        # prefer lines containing 2-4 tokens and title-case or ALL-CAPS
        tokens = ln.split()
        if 2 <= len(tokens) <= 5:
            # ignore lines that are headings like "Resume" or "Curriculum Vitae"
            if re.search(r"resume|curriculum vitae|cv|profile|summary", ln, re.I):
                continue
            # check capitalization quality
            cap_count = sum(1 for t in tokens if t[0].isupper())
            if cap_count >= max(1, len(tokens)//2):
                return ln
    # last resort: return first line
    return lines[0]

# ---------- improved experience date parsing ----------
def parse_date_range_from_text(text: str) -> Tuple[str, str]:
    """
    Attempt to extract the most likely start and end years from a blob of text.
    Returns (start, end) as strings (YYYY) or empty strings.
    """
    # 1) try explicit range like "June 2019 - Aug 2021" or "2018–2020"
    m = DATE_RANGE_RE.search(text)
    if m:
        a, b = m.group(1), m.group(2)
        da = dateparser.parse(a)
        db = dateparser.parse(b)
        sa = str(da.year) if da else (YEAR_RE.search(a).group(0) if YEAR_RE.search(a) else "")
        sb = str(db.year) if db else (YEAR_RE.search(b).group(0) if YEAR_RE.search(b) else "")
        return sa, sb

    # 2) try to find all 4-digit years and pick first and second
    years = YEAR_RE.findall(text)
    # YEAR_RE.findall returns tuples because of groups; fix it
    yrs = [m.group(0) if hasattr(m, "group") else (m[0] if isinstance(m, tuple) else m) for m in YEAR_RE.finditer(text)]
    if yrs:
        if len(yrs) == 1:
            return yrs[0], ""
        else:
            return yrs[0], yrs[1]
    # 3) try month+year patterns
    m2 = re.search(r"([A-Za-z]{3,9}\s*\d{4})", text)
    if m2:
        dt = dateparser.parse(m2.group(1))
        if dt:
            return str(dt.year), ""
    return "", ""

# ---------- expanded education parsing (uses degree + major keywords) ----------
def extract_gpa_and_scale(text: str) -> Tuple[str, str]:
    m = PERCENT_RE.search(text)
    if m:
        return m.group("val"), "%"
    m2 = GPA_RE.search(text)
    if m2:
        val = m2.group("val")
        scale = m2.group("scale") or ""
        if not scale:
            try:
                if float(val) <= 4.5:
                    scale = "4"
                elif float(val) <= 10:
                    scale = "10"
            except Exception:
                scale = ""
        return val, scale
    return "", ""

def parse_education_section(edu_text: str) -> Dict[str, Any]:
    out = {k: "" for k in [
        "highSchoolName","highSchoolAddress","highSchoolGpaOrPercentage","highSchoolGpaScale","highSchoolBoard","highSchoolGraduationYear",
        "ugCollegeName","ugCollegeAddress","ugCollegeGpaOrPercentage","ugCollegeGpaScale","ugUniversity","ugGraduationYear","ugDegree","ugMajor",
        "pgCollegeName","pgCollegeAddress","pgCollegeGpaOrPercentage","pgCollegeGpaScale","pgUniversity","pgGraduationYear","pgDegree","pgMajor"
    ]}
    if not edu_text:
        return out

    nlp = get_nlp()
    orgs = []
    years = []
    if nlp:
        try:
            doc = nlp(_shorten_for_ner(edu_text, max_chars=2000))
            for ent in doc.ents:
                if ent.label_ in ("ORG","GPE","FAC","INSTITUTION"):
                    orgs.append(ent.text.strip())
                if ent.label_ in ("DATE","TIME"):
                    y = re.search(r"\b(19|20)\d{2}\b", ent.text)
                    if y:
                        years.append(y.group(0))
        except Exception:
            pass

    lines = [l.strip() for l in edu_text.splitlines() if l.strip()]
    # break into blocks by blank-lines or typical separators
    blocks = []
    cur = []
    for ln in lines:
        cur.append(ln)
        if re.search(r"\b(19|20)\d{2}\b", ln) or len(cur) >= 4:
            blocks.append(" ".join(cur).strip())
            cur = []
    if cur:
        blocks.append(" ".join(cur).strip())

    for blk in blocks:
        L = blk.lower()
        gpa, scale = extract_gpa_and_scale(blk)
        start, end = parse_date_range_from_text(blk)
        # detect high school
        if any(k in L for k in HS_KEYWORDS) or "class 12" in L or "grade 12" in L:
            out["highSchoolName"] = out["highSchoolName"] or re.split(r"[,–\-—\|]", blk)[0].strip()
            out["highSchoolGpaOrPercentage"] = out["highSchoolGpaOrPercentage"] or gpa
            out["highSchoolGpaScale"] = out["highSchoolGpaScale"] or scale
            out["highSchoolGraduationYear"] = out["highSchoolGraduationYear"] or end or start or ""
            continue

        # detect postgraduate
        if any(k in L for k in PG_DEGREE_KEYWORDS) or "master" in L or "msc" in L or "mba" in L:
            out["pgCollegeName"] = out["pgCollegeName"] or blk
            out["pgDegree"] = out["pgDegree"] or next((k for k in PG_DEGREE_KEYWORDS if k in L), "")
            out["pgCollegeGpaOrPercentage"] = out["pgCollegeGpaOrPercentage"] or gpa
            out["pgCollegeGpaScale"] = out["pgCollegeGpaScale"] or scale
            out["pgGraduationYear"] = out["pgGraduationYear"] or end or start or ""
            # try to capture major
            for mj in MAJOR_KEYWORDS:
                if mj in L:
                    out["pgMajor"] = out["pgMajor"] or mj
            continue

        # detect undergraduate
        if any(k in L for k in UG_DEGREE_KEYWORDS) or "bachelor" in L or "bsc" in L or "btech" in L or "b.e" in L:
            out["ugCollegeName"] = out["ugCollegeName"] or blk
            out["ugDegree"] = out["ugDegree"] or next((k for k in UG_DEGREE_KEYWORDS if k in L), "")
            out["ugCollegeGpaOrPercentage"] = out["ugCollegeGpaOrPercentage"] or gpa
            out["ugCollegeGpaScale"] = out["ugCollegeGpaScale"] or scale
            out["ugGraduationYear"] = out["ugGraduationYear"] or end or start or ""
            for mj in MAJOR_KEYWORDS:
                if mj in L:
                    out["ugMajor"] = out["ugMajor"] or mj
            continue

        # fallback: institution mention
        if "university" in L or "college" in L or "institute" in L:
            if not out["ugCollegeName"]:
                out["ugCollegeName"] = blk
                out["ugGraduationYear"] = out["ugGraduationYear"] or end or start or ""
            elif not out["pgCollegeName"]:
                out["pgCollegeName"] = blk
                out["pgGraduationYear"] = out["pgGraduationYear"] or end or start or ""

    # fill from orgs if still empty
    if orgs:
        if not out["ugCollegeName"] and orgs:
            out["ugCollegeName"] = orgs[0]
        if not out["pgCollegeName"] and len(orgs) > 1:
            out["pgCollegeName"] = orgs[1]
    if years:
        if not out["ugGraduationYear"] and years:
            out["ugGraduationYear"] = years[0]
        if not out["pgGraduationYear"] and len(years) > 1:
            out["pgGraduationYear"] = years[1]
    return out

# ---------- experience parsing improved (uses date-range and NER) ----------
def parse_experience(text: str) -> List[Dict[str, str]]:
    entries = []
    parts = re.split(r"\n\s*\n", text.strip())
    nlp = get_nlp()
    for p in parts:
        if len(p.strip()) < 20:
            continue
        startYear, endYear = parse_date_range_from_text(p)
        org = ""
        title = ""
        if nlp:
            try:
                doc = nlp(_shorten_for_ner(p, max_chars=2000))
                orgs = [ent.text for ent in doc.ents if ent.label_ in ("ORG","FAC","INSTITUTION","GPE")]
                if orgs:
                    org = orgs[0]
                # title heuristic: best noun chunk or sentence containing role words
                for sent in doc.sents:
                    s = sent.text.lower()
                    if any(k in s for k in ["engineer","developer","manager","analyst","research","intern","consultant","officer","professor","lead","associate","architect","scientist"]):
                        title = sent.text.strip()
                        break
                if not title:
                    # fallback to first noun chunk
                    nchunks = [nc.text for nc in doc.noun_chunks]
                    if nchunks:
                        title = nchunks[0]
            except Exception:
                pass
        # fallback heuristics if NER not present
        if not org:
            first_line = p.splitlines()[0]
            cand = re.split(r"[,–\-—@]", first_line)[0]
            if re.search(r"\b(Inc|Ltd|LLC|Company|University|College|Corp|Corporation|Institute|GmbH)\b", cand, re.I):
                org = cand.strip()
            elif len(first_line.split()) <= 4 and any(w.lower() in first_line.lower() for w in ["engineer","developer","manager","analyst","intern"]):
                title = first_line.strip()

        entries.append({
            "title": title,
            "organization": org,
            "startYear": startYear,
            "endYear": endYear,
            "details": p.strip()
        })
    return entries

# ---------- other parsers (certs, pubs) remain similar ----------
def parse_certifications(text: str) -> List[str]:
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "certif" in line.lower() or "certificate" in line.lower() or "cert." in line.lower() or any(k in line.lower() for k in ["coursera","udemy","nptel","google","aws","microsoft"]):
            items.append(line)
    return items

def parse_publications(text: str) -> List[str]:
    items = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if '"' in line or "journal" in line.lower() or "conference" in line.lower() or "proceedings" in line.lower():
            items.append(line.strip())
    return items

# ---------- assemble schema ----------
def assemble_full_schema(raw_text: str, sections: Dict[str, str]) -> Dict[str, Any]:
    top = sections.get("top","") or ""
    whole = raw_text or ""
    name = extract_name_from_top(top)
    emails = EMAIL_RE.findall(whole)
    phones = [m.group(0) for m in PHONE_RE.finditer(whole)]
    edu_blob = sections.get("education") or sections.get("top","") + "\n" + sections.get("other","")
    edu_parsed = parse_education_section(edu_blob)

    out = {
        "name": name,
        "email": first_or_empty(emails),
        "phoneNumber": first_or_empty(phones),
        "highSchoolName": edu_parsed.get("highSchoolName",""),
        "highSchoolAddress": edu_parsed.get("highSchoolAddress",""),
        "highSchoolGpaOrPercentage": edu_parsed.get("highSchoolGpaOrPercentage",""),
        "highSchoolGpaScale": edu_parsed.get("highSchoolGpaScale",""),
        "highSchoolBoard": edu_parsed.get("highSchoolBoard",""),
        "highSchoolGraduationYear": edu_parsed.get("highSchoolGraduationYear",""),
        "ugCollegeName": edu_parsed.get("ugCollegeName",""),
        "ugCollegeAddress": edu_parsed.get("ugCollegeAddress",""),
        "ugCollegeGpaOrPercentage": edu_parsed.get("ugCollegeGpaOrPercentage",""),
        "ugCollegeGpaScale": edu_parsed.get("ugCollegeGpaScale",""),
        "ugUniversity": edu_parsed.get("ugUniversity",""),
        "ugGraduationYear": edu_parsed.get("ugGraduationYear",""),
        "ugDegree": edu_parsed.get("ugDegree",""),
        "ugMajor": edu_parsed.get("ugMajor",""),
        "pgCollegeName": edu_parsed.get("pgCollegeName",""),
        "pgCollegeAddress": edu_parsed.get("pgCollegeAddress",""),
        "pgCollegeGpaOrPercentage": edu_parsed.get("pgCollegeGpaOrPercentage",""),
        "pgCollegeGpaScale": edu_parsed.get("pgCollegeGpaScale",""),
        "pgUniversity": edu_parsed.get("pgUniversity",""),
        "pgGraduationYear": edu_parsed.get("pgGraduationYear",""),
        "pgDegree": edu_parsed.get("pgDegree",""),
        "pgMajor": edu_parsed.get("pgMajor",""),
        "certifications": parse_certifications(sections.get("certifications","") or sections.get("other","")),
        "extraCurricularActivities": [s.strip() for s in (sections.get("extracurricular","") or "").splitlines() if s.strip()],
        "workExperience": parse_experience(sections.get("experience","") or sections.get("other","")),
        "researchPublications": parse_publications(sections.get("publications","") or ""),
        "testScores": {},  # keep previous implementation or reuse parse_test_scores if present
        "achievements": [s.strip() for s in (sections.get("achievements","") or "").splitlines() if s.strip()],
    }
    return out
