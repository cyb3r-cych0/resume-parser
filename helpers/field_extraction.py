#!/usr/bin/env python3
"""
Extracts contact info, education blocks (UG/PG/High school),
test scores, certifications, activities, work experience stubs,
and returns a JSON matching your schema.
Field extraction using section-aware parsing + NER hints.
Produces a dictionary matching the target schema.
"""
import re
from typing import Dict, Any, List, Optional

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_RE = re.compile(r"(\+?\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?)?\d{3,4}[\s-]?\d{3,4}")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
PERCENT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?\s?%)")
GPA_RE = re.compile(r"\b([0-4]\.\d{1,2}|[0-9]\.\d{1,2})\b")  # loose

_DEGREE_PATTERNS = [
    r"\bBachelor(?:'s)?\b", r"\bB\.?A\.?\b", r"\bB\.?S\.?\b", r"\bBSc\b", r"\bBE\b",
    r"\bMaster(?:'s)?\b", r"\bM\.?S\.?\b", r"\bMSc\b", r"\bMBA\b", r"\bPhD\b", r"\bDoctorate\b"
]
_DEGREE_RE = re.compile("|".join(_DEGREE_PATTERNS), flags=re.IGNORECASE)

_TEST_SCORE_KEYS = {
    "sat": ["sat"],
    "act": ["act"],
    "gre": ["gre"],
    "gmat": ["gmat"],
    "toefl": ["toefl"],
    "ielts": ["ielts"]
}

# helper small utilities
def _first_match(pattern: re.Pattern, text: str) -> Optional[str]:
    if not text:
        return None
    m = pattern.search(text)
    return m.group(0).strip() if m else None

def _find_all(pattern: re.Pattern, text: str) -> List[str]:
    if not text:
        return []
    return [m.group(0).strip() for m in pattern.finditer(text)]

def _parse_year_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    m = YEAR_RE.search(text)
    return m.group(0) if m else None

def _clean(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()

# ---------------- Core extraction functions ----------------
def extract_contact_from_text(text: str) -> Dict[str, str]:
    out = {"name": "", "email": "", "phoneNumber": ""}
    if not text:
        return out
    # email
    e = _first_match(EMAIL_RE, text)
    if e:
        out["email"] = e
    # phone (prefer last longer match)
    phones = _find_all(PHONE_RE, text)
    if phones:
        # pick longest plausible
        phones.sort(key=lambda x: len(re.sub(r"\D", "", x)), reverse=True)
        out["phoneNumber"] = phones[0]
    # name: leave blank here, NER/previous stage populates if available
    return out

def extract_test_scores_from_section(text: str) -> Dict[str, str]:
    scores = {k: "" for k in _TEST_SCORE_KEYS.keys()}
    if not text:
        return scores
    for key, variants in _TEST_SCORE_KEYS.items():
        for v in variants:
            # try patterns like "SAT: 1450" or "1450 SAT"
            m = re.search(rf"{v}[^0-9]*?(\d{{2,4}})", text, flags=re.IGNORECASE)
            if m:
                scores[key] = m.group(1)
                break
    return scores

def extract_certifications_from_section(text: str) -> List[str]:
    if not text:
        return []
    # split by lines and commas, simple dedupe
    parts = re.split(r"\n|;|,|\t", text)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # skip very short tokens
        if len(p) < 4:
            continue
        # heuristics: look for "Certified", "Certification", "Certificate", "Exam"
        if re.search(r"(certif|certificate|certified|exam|course|professional)", p, flags=re.IGNORECASE):
            out.append(_clean(p))
        else:
            # if line looks like a certificate (contains uppercase words + numbers)
            if len(p.split()) <= 6 and any(ch.isdigit() for ch in p):
                out.append(_clean(p))
    return list(dict.fromkeys(out))

def extract_education_from_section(text: str) -> List[Dict[str, str]]:
    """
    Return list of education entries with fields:
    collegeName, collegeAddress (best-effort), degree, major, graduationYear, gpa/percentage
    """
    if not text:
        return []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    entries = []
    # simple heuristic: look for lines containing year or degree keywords
    buffer = []
    for ln in lines:
        buffer.append(ln)
        # flush when we see a year or degree pattern or blank line
        if YEAR_RE.search(ln) or _DEGREE_RE.search(ln):
            block = " ".join(buffer)
            entries.append(block)
            buffer = []
    # add remaining as single entry if none found
    if not entries and buffer:
        entries.append(" ".join(buffer))

    out = []
    for blk in entries:
        college = ""
        degree = ""
        major = ""
        year = ""
        gpa = ""
        # attempt email/phone unlikely here so skip
        # try to split by comma
        parts = [p.strip() for p in re.split(r",|\||-{2,}", blk) if p.strip()]
        # find degree
        dmatch = _DEGREE_RE.search(blk)
        if dmatch:
            degree = dmatch.group(0)
        # year
        y = _parse_year_from_text(blk)
        if y:
            year = y
        # gpa or percentage
        p_match = PERCENT_RE.search(blk)
        if p_match:
            gpa = p_match.group(0)
        else:
            gpa_m = GPA_RE.search(blk)
            if gpa_m:
                gpa = gpa_m.group(0)
        # find potential college (longest part with 'univ/college/institute' or fallback first part)
        college_candidates = [p for p in parts if re.search(r"(univ|college|institute|school|faculty|campus)", p, flags=re.IGNORECASE)]
        if college_candidates:
            college = college_candidates[0]
        else:
            # fallback to the first long segment
            long_parts = sorted(parts, key=lambda x: len(x), reverse=True)
            college = long_parts[0] if long_parts else parts[0] if parts else ""
        # attempt major detection in block
        m = re.search(r"(?:Major|Specialization|Field|Program)\s*[:\-]\s*([A-Za-z &/0-9]+)", blk, flags=re.IGNORECASE)
        if m:
            major = m.group(1).strip()
        else:
            # try keyword scan
            for kw in ["computer science","information technology","electrical","mechanical","business","economics","finance","data science","software"]:
                if kw in blk.lower():
                    major = kw.title()
                    break
        out.append({
            "collegeName": _clean(college),
            "collegeAddress": "",
            "degree": _clean(degree),
            "major": _clean(major),
            "graduationYear": _clean(year),
            "gpaOrPercentage": _clean(gpa),
            "gpaScale": ""
        })
    return out

def extract_experience_from_section(text: str) -> List[Dict[str, str]]:
    """
    Returns list of work experiences with basic fields: title, organization, startYear, endYear, details
    """
    if not text:
        return []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    entries = []
    # heuristic: group by blank lines or lines that start with uppercase title + company
    buffer = []
    for ln in lines:
        if re.match(r"^[A-Z][\S ]{2,80}$", ln) and buffer and len(buffer) > 0 and any(YEAR_RE.search(b) for b in buffer[-2:]):
            # likely new entry
            entries.append(" ".join(buffer))
            buffer = [ln]
        else:
            buffer.append(ln)
    if buffer:
        entries.append(" ".join(buffer))

    out = []
    for blk in entries:
        title = ""
        org = ""
        start = ""
        end = ""
        details = blk
        # try to find years
        years = YEAR_RE.findall(blk)
        if years:
            # naive: first is start, last is end
            if len(years) >= 1:
                start = years[0]
            if len(years) >= 2:
                end = years[-1]
        # try to parse "Title at Org" patterns
        m = re.search(r"^(?P<title>[\w\-/ &]{3,60})\s+at\s+(?P<org>[\w &\.\-]{3,60})", blk, flags=re.IGNORECASE)
        if m:
            title = m.group("title").strip()
            org = m.group("org").strip()
        else:
            # try split by '—' or '-' or '|' or ',' heuristics
            parts = re.split(r"—|-|\||,", blk)
            if parts:
                # assume first short part is title, second is org
                if len(parts) >= 2:
                    title = parts[0].strip()
                    org = parts[1].strip()
                else:
                    # fallback: take first 6 words as title
                    title = " ".join(parts[0].split()[:6])
        out.append({
            "title": _clean(title),
            "organization": _clean(org),
            "startYear": _clean(start),
            "endYear": _clean(end),
            "details": _clean(details)
        })
    return out

# ---------------- Top-level assembler ----------------
def assemble_full_schema(raw_text: str, sections: Dict[str, str], nlp=None) -> Dict[str, Any]:
    """
    Build the final schema (closely matching the required JSON output).
    `sections` should be the OrderedDict from split_into_sections().
    `nlp` is optional spaCy model; if provided, we may use it for NER hints.
    """
    parsed: Dict[str, Any] = {
      "name": "",
      "email": "",
      "phoneNumber": "",
      "highSchoolName": "",
      "highSchoolAddress": "",
      "highSchoolGpaOrPercentage": "",
      "highSchoolGpaScale": "",
      "highSchoolBoard": "",
      "highSchoolGraduationYear": "",
      "ugCollegeName": "",
      "ugCollegeAddress": "",
      "ugCollegeGpaOrPercentage": "",
      "ugCollegeGpaScale": "",
      "ugUniversity": "",
      "ugGraduationYear": "",
      "ugDegree": "",
      "ugMajor": "",
      "pgCollegeName": "",
      "pgCollegeAddress": "",
      "pgCollegeGpaOrPercentage": "",
      "pgCollegeGpaScale": "",
      "pgUniversity": "",
      "pgGraduationYear": "",
      "pgDegree": "",
      "pgMajor": "",
      "certifications": [],
      "extraCurricularActivities": [],
      "workExperience": [],
      "researchPublications": [],
      "testScores": {
        "sat": "",
        "act": "",
        "gre": "",
        "gmat": "",
        "toefl": "",
        "ielts": ""
      },
      "achievements": []
    }

    # 1) top header area: contact detection
    header_text = sections.get("header", "") or ""
    contact = extract_contact_from_text(raw_text)  # more robust to scan entire text for email/phone
    parsed["email"] = contact.get("email", "")
    parsed["phoneNumber"] = contact.get("phoneNumber", "")

    # populate name from NER hints or header heuristics
    if nlp:
        try:
            doc = nlp(raw_text)
            # prefer PERSON entity
            persons = [ent.text.strip() for ent in doc.ents if ent.label_ == "PERSON"]
            if persons:
                parsed["name"] = persons[0]
        except Exception:
            pass

    # 2) Education: use 'education' section if present, otherwise scan all sections for education-like content
    edu_text = sections.get("education") or ""
    if not edu_text:
        # try other keys
        for k in sections:
            if "education" in k or "academic" in k or "school" in k:
                edu_text = sections.get(k)
                break
    edu_entries = extract_education_from_section(edu_text or raw_text)
    if edu_entries:
        # map first to UG if degree contains Bachelor, else try to assign by year heuristics
        if len(edu_entries) >= 1:
            e0 = edu_entries[0]
            parsed["ugCollegeName"] = e0.get("collegeName","")
            parsed["ugCollegeAddress"] = e0.get("collegeAddress","")
            parsed["ugCollegeGpaOrPercentage"] = e0.get("gpaOrPercentage","")
            parsed["ugDegree"] = e0.get("degree","")
            parsed["ugMajor"] = e0.get("major","")
            parsed["ugGraduationYear"] = e0.get("graduationYear","")
        if len(edu_entries) >= 2:
            e1 = edu_entries[1]
            parsed["pgCollegeName"] = e1.get("collegeName","")
            parsed["pgCollegeAddress"] = e1.get("collegeAddress","")
            parsed["pgCollegeGpaOrPercentage"] = e1.get("gpaOrPercentage","")
            parsed["pgDegree"] = e1.get("degree","")
            parsed["pgMajor"] = e1.get("major","")
            parsed["pgGraduationYear"] = e1.get("graduationYear","")

    # 3) Work experience
    exp_text = sections.get("experience") or ""
    if not exp_text:
        for k in sections:
            if "experience" in k or "employment" in k or "professional" in k:
                exp_text = sections.get(k)
                break
    parsed["workExperience"] = extract_experience_from_section(exp_text or "")

    # 4) Certifications
    cert_text = sections.get("certifications") or ""
    parsed["certifications"] = extract_certifications_from_section(cert_text or "")

    # 5) test scores
    ts_text = sections.get("test_scores") or ""
    parsed["testScores"] = extract_test_scores_from_section(ts_text or raw_text)

    # 6) publications / achievements / extras
    pub_text = sections.get("publications") or ""
    if pub_text:
        parsed["researchPublications"] = [l.strip() for l in pub_text.splitlines() if l.strip()]
    ach_text = sections.get("achievements") or ""
    if ach_text:
        parsed["achievements"] = [l.strip() for l in ach_text.splitlines() if l.strip()]

    # 7) certifications fallback: scan whole text if none found
    if not parsed["certifications"]:
        parsed["certifications"] = extract_certifications_from_section(raw_text)

    # 8) final cleaning: ensure strings, basic normalization left to normalization.py
    for k in list(parsed.keys()):
        if isinstance(parsed[k], str):
            parsed[k] = _clean(parsed[k])
    return parsed
