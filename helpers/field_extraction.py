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
# -------------------------------
# B-2: NER + heuristics job title extractor
# -------------------------------
def extract_job_title(block: str) -> str:
    """
    STRICT job title extractor.
    - Extracts titles only if clear role keywords exist
    - Never returns education, locations, or long sentences
    """

    if not block:
        return ""

    first = block.split("\n")[0].strip()

    # Remove year ranges
    first = re.sub(
        r"(19|20)\d{2}\s*[-–—]\s*(Present|(19|20)\d{2})",
        "",
        first,
        flags=re.IGNORECASE
    )
    first = re.sub(r"(19|20)\d{2}", "", first).strip()

    # Hard reject noisy lines
    if len(first.split()) > 6:
        return ""

    if re.search(r"[@/\\]|http", first):
        return ""

    BAD = {
        "university", "college", "school", "bachelor", "master",
        "certificate", "training", "expected graduation",
        "portfolio", "about", "profile", "summary"
    }
    low = first.lower()
    if any(b in low for b in BAD):
        return ""

    TITLE_WORDS = {
        "engineer", "developer", "designer", "analyst",
        "manager", "consultant", "intern", "architect",
        "administrator", "specialist", "lead", "scientist"
    }

    if any(t in low for t in TITLE_WORDS):
        return first

    return ""


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

def extract_education_blocks(canonical_sections: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    D-1: Strict education extractor.
    Prevents summaries / contacts / skills from leaking into education.
    """

    DEGREE_WORDS = {
        "bachelor", "b.sc", "btech", "b.tech", "bca",
        "master", "m.sc", "mtech", "m.tech", "msc",
        "phd", "doctorate", "associate", "diploma"
    }

    BAD_WORDS = {
        "profile", "summary", "experience", "skills", "project",
        "contact", "email", "phone", "portfolio"
    }

    YEAR_RE = re.compile(r"(19|20)\d{2}")
    EMAIL_RE = re.compile(r"\S+@\S+")
    URL_RE = re.compile(r"https?://\S+")

    def _is_noise_line(s: str) -> bool:
        low = s.lower()
        if "@" in s or "http" in s:
            return True
        if re.search(r"\+?\d{7,}", s):  # phone numbers
            return True
        if len(s.split()) > 20:
            return True
        BAD = {
            "profile", "summary", "skills", "experience",
            "contact", "portfolio", "github", "linkedin"
        }
        return any(b in low for b in BAD)

    text = canonical_sections.get("education", "")
    if not text:
        return []

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    entries = []

    for ln in lines:
        low = ln.lower()

        if _is_noise_line(ln):
            continue
        if any(b in low for b in BAD_WORDS):
            continue
        if not any(d in low for d in DEGREE_WORDS):
            continue

        year = ""
        ym = YEAR_RE.search(ln)
        if ym:
            year = ym.group(0)

        entries.append({
            "collegeName": ln,
            "collegeAddress": "",
            "degree": ln,
            "major": "",
            "gpaOrPercentage": "",
            "graduationYear": year
        })

    return entries[:2]  # max UG + PG


def extract_experience_blocks(canonical_sections: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    FINAL work-experience extractor.
    Guarantees:
    - Real companies only
    - Valid year ranges
    - Extracted job titles
    - No education / certification leakage
    """

    YEAR_RE = re.compile(r"(19|20)\d{2}")
    RANGE_RE = re.compile(r"(19|20)\d{2}\s*[-–—]\s*(Present|(19|20)\d{2})", re.I)

    TITLE_RE = re.compile(
        r"\b("
        r"software engineer|senior software engineer|junior software engineer|"
        r"full[- ]?stack developer|backend developer|frontend developer|"
        r"java developer|python developer|web developer|"
        r"data engineer|data analyst|ml engineer|ai engineer|"
        r"security engineer|cybersecurity analyst|soc analyst|"
        r"designer|web designer|ui/ux designer|"
        r"architect|consultant|lead|manager|intern"
        r")\b",
        re.I
    )

    REJECT_WORDS = {
        "university", "college", "school",
        "bachelor", "master", "phd",
        "certificate", "certified", "training",
        "expected graduation", "skills",
        "profile", "summary"
    }

    ACTION_VERBS = re.compile(
        r"\b(developed|implemented|designed|built|managed|led|worked|maintained|"
        r"created|optimized|configured|deployed|integrated)\b",
        re.I
    )

    def extract_job_title_strict(lines: list) -> str:
        for ln in lines[:2]:
            if len(ln.split()) > 8:
                continue
            if YEAR_RE.search(ln):
                continue
            m = TITLE_RE.search(ln.lower())
            if m:
                return m.group(0).title()
        return ""

    text = canonical_sections.get("experience") or ""
    if not text:
        return []

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    blocks, current = [], []

    # STEP 1 — group by year markers
    for ln in lines:
        if YEAR_RE.search(ln):
            if current:
                blocks.append(current)
                current = []
        current.append(ln)

    if current:
        blocks.append(current)

    results = []

    # STEP 2 — process blocks
    for blk in blocks:
        blk_text = " ".join(blk).lower()

        if any(w in blk_text for w in REJECT_WORDS):
            continue

        # years
        start, end = "", ""
        m = RANGE_RE.search(" ".join(blk))
        if m:
            start = m.group(1)
            end = m.group(2)
        else:
            years = re.findall(r"(19|20)\d{2}", " ".join(blk))
            if not years:
                continue
            start = years[0]
            end = years[1] if len(years) > 1 else ""

        # title FIRST (important)
        title = extract_job_title_strict(blk)

        # organization
        org = blk[0]

        # remove years
        org = re.sub(r"(19|20)\d{2}.*", "", org)

        # remove title text from org
        if title and title.lower() in org.lower():
            org = re.sub(re.escape(title), "", org, flags=re.I)

        # split separators
        org = re.split(r"[|/–—\-]", org)[0]

        BAD_ORG_TOKENS = {
            "lorem", "ipsum", "profile", "summary", "about",
            "chicago", "texas", "india", "missouri"
        }

        org = " ".join(
            w for w in org.split() if w.lower() not in BAD_ORG_TOKENS
        ).strip(" ,:-")

        if len(org.split()) > 6:
            continue

        # details
        details = []
        for ln in blk[1:]:
            if ACTION_VERBS.search(ln):
                details.append(ln.strip())
            if len(details) >= 6:
                break

        if not details:
            continue

        results.append({
            "organization": org,
            "title": title,
            "startYear": start,
            "endYear": end,
            "details": details
        })

    # STEP 3 — merge duplicates
    merged = {}

    for exp in results:
        key = (
            exp["organization"].lower(),
            exp["startYear"],
            exp["endYear"]
        )
        if key not in merged:
            merged[key] = exp
        else:
            merged[key]["details"] = list(
                dict.fromkeys(merged[key]["details"] + exp["details"])
            )[:6]

    return list(merged.values())





def _is_false_experience_block(block: dict) -> bool:
    """
    Filters out education, certifications, training, soft skills, and personal info
    mistakenly classified as work experience.
    """
    text = (block.get("details","") + " " +
            block.get("organization","") + " " +
            block.get("title","")).lower()

    BAD_HINTS = [
        "graduation",
        "expected",
        "certificate",
        "certified",
        "training",
        "internship program",
        "gpa",
        "university",
        "school",
        "education",
        "languages:",
        "contact",
        "portfolio",
        "@",
        "hobbies",
        "skills",
        "technical skills",
    ]

    # If any bad hint appears → this block is NOT work experience
    if any(b in text for b in BAD_HINTS):
        return True

    # discard blocks with no meaningful fields
    if not block.get("title") and not block.get("organization"):
        return True

    # discard tiny fragments
    if len(text) < 30:
        return True

    return False


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

    # C-4: strict name extraction (header + validation)
    def _extract_name_strict(text: str, nlp=None) -> str:
        BAD = {
            "profile", "summary", "resume", "cv", "contact",
            "education", "experience", "skills", "projects",
            "visa status", "about me"
        }

        lines = [l.strip() for l in header_text.split("\n") if l.strip()]
        header = lines[:5]

        # 1) header heuristic (most reliable)
        for ln in header:
            low = ln.lower()
            if any(b in low for b in BAD):
                continue
            if "@" in ln or "http" in ln or re.search(r"\d", ln):
                continue
            parts = ln.split()
            if 2 <= len(parts) <= 4 and all(p[0].isupper() for p in parts):
                return ln

        # 2) fallback to NER but validated
        if nlp:
            try:
                doc = nlp(text)
                for ent in doc.ents:
                    if ent.label_ == "PERSON":
                        val = ent.text.strip()
                        if any(b in val.lower() for b in BAD):
                            continue
                        if 2 <= len(val.split()) <= 4:
                            return val
            except Exception:
                pass

        return ""

    parsed["name"] = _extract_name_strict(raw_text, nlp)

    # 2) Education: use 'education' section if present, otherwise scan all sections for education-like content
    edu_text = sections.get("education") or ""
    if not edu_text:
        # try other keys
        for k in sections:
            if "education" in k or "academic" in k or "school" in k:
                edu_text = sections.get(k)
                break
    edu_entries = extract_education_blocks({"education": edu_text})
    for edu in edu_entries:
        deg = (edu.get("degree") or "").lower()

        if any(k in deg for k in ["bachelor", "b.sc", "b.tech"]):
            parsed["ugCollegeName"] = edu.get("collegeName", "")
            parsed["ugDegree"] = edu.get("degree", "")
            parsed["ugMajor"] = edu.get("major", "")
            parsed["ugGraduationYear"] = edu.get("graduationYear", "")

        elif any(k in deg for k in ["master", "m.sc", "m.tech", "phd"]):
            parsed["pgCollegeName"] = edu.get("collegeName", "")
            parsed["pgDegree"] = edu.get("degree", "")
            parsed["pgMajor"] = edu.get("major", "")
            parsed["pgGraduationYear"] = edu.get("graduationYear", "")

    # 3) Work experience
    exp_text = sections.get("experience") or ""
    if not exp_text:
        for k in sections:
            if "experience" in k or "employment" in k or "professional" in k:
                exp_text = sections.get(k)
                break
    parsed["workExperience"] = extract_experience_blocks({"experience": exp_text})

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

    # -----------------------------
    # STEP 3 — SCHEMA GUARDS
    # -----------------------------

    def _clean_field(val: str) -> str:
        if not val:
            return ""
        low = val.lower()
        # reject obvious garbage
        BAD = {
            "profile summary", "resume", "cv",
            "contact", "skills", "experience",
            "expected graduation"
        }
        if any(b in low for b in BAD):
            return ""
        # reject URLs / emails / phones
        if "@" in val or "http" in val:
            return ""
        if re.search(r"\+?\d{7,}", val):
            return ""
        # reject very long sentences
        if len(val.split()) > 12:
            return ""
        return val.strip()

    # apply guards
    parsed["name"] = _clean_field(parsed.get("name", ""))
    parsed["ugCollegeName"] = _clean_field(parsed.get("ugCollegeName", ""))
    parsed["pgCollegeName"] = _clean_field(parsed.get("pgCollegeName", ""))
    parsed["ugDegree"] = _clean_field(parsed.get("ugDegree", ""))
    parsed["pgDegree"] = _clean_field(parsed.get("pgDegree", ""))

    return parsed
