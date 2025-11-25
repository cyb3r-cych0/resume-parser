#!/usr/bin/env python3
"""
Extracts contact info, education blocks (UG/PG/High school), 
test scores, certifications, activities, work experience stubs, 
and returns a JSON matching your schema.

"""

import re
from typing import Dict, Any, List, Tuple
from datetime import datetime
import dateparser
from rapidfuzz import fuzz

EMAIL_RE = re.compile(r"[a-zA-Z0-9.+_-]+@[a-zA-Z0-9._-]+\.[a-zA-Z]+")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s\-\.])?(?:\(?\d{2,4}\)?[\s\-\.])?\d{3,4}[\s\-\.]?\d{3,4}")
URL_RE = re.compile(r"(https?://\S+|www\.\S+)")
GITHUB_RE = re.compile(r"(?:github\.com/)([A-Za-z0-9_\-]+)")
LINKEDIN_RE = re.compile(r"(?:linkedin\.com/in/|linkedin\.com/pub/)([A-Za-z0-9_\-\/]+)")

# heuristics for education degrees
UG_DEGREE_KEYWORDS = ["bachelor", "b\.sc", "bsc", "b\.tech", "btech", "bachelor of", "b\.e", "b\.eng", "bs in", "ba "]
PG_DEGREE_KEYWORDS = ["master", "m\.sc", "msc", "mtech", "m\.tech", "m\.e", "mba", "ms ", "m\.s"]
HS_KEYWORDS = ["high school", "secondary school", "senior secondary", "class 12", "grade 12", "higher secondary", "school"]

GPA_RE = re.compile(r"(?P<val>\d+(\.\d+)?)(?:\s*/\s*(?P<scale>\d+(\.\d+)?))?")
PERCENT_RE = re.compile(r"(?P<val>\d{1,3}(?:\.\d{1,2})?)\s?%")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

def first_or_empty(lst):
    return lst[0] if lst else ""

def find_emails(text: str) -> List[str]:
    return list(dict.fromkeys(EMAIL_RE.findall(text)))

def find_phones(text: str) -> List[str]:
    phones = []
    for m in PHONE_RE.finditer(text):
        p = m.group(0).strip()
        digits = re.sub(r"\D", "", p)
        if 7 <= len(digits) <= 15:
            phones.append(p)
    return list(dict.fromkeys(phones))

def find_urls(text: str) -> List[str]:
    return list(dict.fromkeys(URL_RE.findall(text)))

def find_github(text: str) -> List[str]:
    return list(dict.fromkeys(GITHUB_RE.findall(text)))

def find_linkedin(text: str) -> List[str]:
    return list(dict.fromkeys(LINKEDIN_RE.findall(text)))

def extract_name_from_top(top_text: str) -> str:
    # heuristic: first non-empty line with >1 token and contains letters (not all lower)
    for line in top_text.splitlines():
        line = line.strip()
        if not line:
            continue
        tokens = line.split()
        if len(tokens) >= 2 and any(t[0].isalpha() for t in tokens):
            # avoid lines with email/phone/URL
            if EMAIL_RE.search(line) or PHONE_RE.search(line) or URL_RE.search(line):
                continue
            # likely a name
            return line
    return ""

def parse_test_scores(text: str) -> Dict[str, str]:
    result = {"sat": "", "act": "", "gre": "", "gmat": "", "toefl": "", "ielts": ""}
    low = text.lower()
    # look for patterns like "GRE: 320" or "GRE 320/340"
    for key in result.keys():
        # fuzzy find lines containing key
        if key in low:
            m = re.search(rf"{key}\s*[:\-]?\s*(\d{{2,3}}(?:\.\d+)?)", low)
            if m:
                result[key] = m.group(1)
            else:
                # percent style
                m2 = re.search(rf"{key}.*?(\d{{2,3}}(?:\.\d+)?)", low)
                if m2:
                    result[key] = m2.group(1)
    # try generic numeric captures for TOEFL/IELTS phrases
    for score in ["toefl", "ielts"]:
        m = re.search(rf"{score}[:\s\-]*?(\d{{2,3}}(?:\.\d+)?)", low)
        if m:
            result[score] = m.group(1)
    return result

def extract_gpa_and_scale(text: str) -> Tuple[str, str]:
    # try percent first
    m = PERCENT_RE.search(text)
    if m:
        return m.group("val"), "%"
    m2 = GPA_RE.search(text)
    if m2:
        val = m2.group("val")
        scale = m2.group("scale") or ""
        # infer scale if none (common 4 or 10)
        if not scale:
            if float(val) <= 4.5:
                scale = "4"
            elif float(val) <= 10:
                scale = "10"
        return val, scale
    return "", ""

def parse_education_section(edu_text: str) -> Dict[str, Any]:
    """
    Attempt to find HS, UG, PG info within a given education section text blob.
    This is heuristic-based and tries to match lines containing a year, degree keywords, or 'school' keywords.
    """
    out = {
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
        "pgMajor": ""
    }
    if not edu_text:
        return out

    lines = [l.strip() for l in edu_text.splitlines() if l.strip()]
    # group lines into candidate blocks by blank-line separators or years
    blocks = []
    cur = []
    for ln in lines:
        cur.append(ln)
        # if line contains year, treat as block boundary sometimes
        if YEAR_RE.search(ln) and len(cur) >= 1:
            blocks.append(" ".join(cur))
            cur = []
    if cur:
        blocks.append(" ".join(cur))

    # classify blocks by fuzzy keyword presence
    for blk in blocks:
        lblk = blk.lower()
        # high school
        if any(k in lblk for k in HS_KEYWORDS) or ("class 12" in lblk) or ("grade 12" in lblk):
            # name is first part before comma or dash
            parts = re.split(r"[,–\-—\|]", blk)
            out["highSchoolName"] = out["highSchoolName"] or parts[0].strip()
            gpa, scale = extract_gpa_and_scale(blk)
            out["highSchoolGpaOrPercentage"] = out["highSchoolGpaOrPercentage"] or gpa
            out["highSchoolGpaScale"] = out["highSchoolGpaScale"] or scale
            y = YEAR_RE.search(blk)
            if y:
                out["highSchoolGraduationYear"] = y.group(0)
            # try board detection (common words)
            if "board" in lblk or "cbse" in lblk or "icse" in lblk or "state board" in lblk:
                out["highSchoolBoard"] = out["highSchoolBoard"] or blk
            continue

        # postgraduate
        if any(k in lblk for k in PG_DEGREE_KEYWORDS):
            out["pgCollegeName"] = out["pgCollegeName"] or blk
            out["pgDegree"] = out["pgDegree"] or next((k for k in PG_DEGREE_KEYWORDS if k in lblk), "")
            gpa, scale = extract_gpa_and_scale(blk)
            out["pgCollegeGpaOrPercentage"] = out["pgCollegeGpaOrPercentage"] or gpa
            out["pgCollegeGpaScale"] = out["pgCollegeGpaScale"] or scale
            y = YEAR_RE.search(blk)
            if y:
                out["pgGraduationYear"] = out["pgGraduationYear"] or y.group(0)
            continue

        # undergraduate
        if any(k in lblk for k in UG_DEGREE_KEYWORDS) or ("bachelor" in lblk) or ("bsc" in lblk) or ("btech" in lblk):
            out["ugCollegeName"] = out["ugCollegeName"] or blk
            out["ugDegree"] = out["ugDegree"] or next((k for k in UG_DEGREE_KEYWORDS if k in lblk), "")
            gpa, scale = extract_gpa_and_scale(blk)
            out["ugCollegeGpaOrPercentage"] = out["ugCollegeGpaOrPercentage"] or gpa
            out["ugCollegeGpaScale"] = out["ugCollegeGpaScale"] or scale
            y = YEAR_RE.search(blk)
            if y:
                out["ugGraduationYear"] = out["ugGraduationYear"] or y.group(0)
            continue

        # fallback: try to detect degree by presence of university/college
        if "university" in lblk or "college" in lblk:
            # assign to UG if UG empty else PG if PG empty
            if not out["ugCollegeName"]:
                out["ugCollegeName"] = blk
            elif not out["pgCollegeName"]:
                out["pgCollegeName"] = blk

    return out

def parse_certifications(text: str) -> List[str]:
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # ignore lines that are too long noise
        if len(line) > 5 and len(line) < 200:
            # simple heuristic: contains "certif" or "certificate" or "completed"
            if "certif" in line.lower() or "certificate" in line.lower() or "cert." in line.lower():
                items.append(line)
            # also capture common course provider tokens
            elif any(tok in line.lower() for tok in ["coursera", "udemy", "edx", "nptel", "google", "aws", "microsoft"]):
                items.append(line)
    return items

def parse_experience(text: str) -> List[Dict[str, str]]:
    """
    Very small heuristic parser: split by blank lines or lines with year ranges and try to capture title/org/dates.
    Returns list of {title, organization, startYear, endYear, details}
    """
    entries = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # join and split by double newlines if present
    blob = "\n".join(lines)
    parts = re.split(r"\n\s*\n", blob)
    for p in parts:
        if len(p) < 20:
            continue
        # find date range
        yrs = YEAR_RE.findall(p)
        startYear = ""
        endYear = ""
        if yrs:
            if len(yrs) == 1:
                startYear = yrs[0]
            elif len(yrs) >= 2:
                startYear = yrs[0]
                endYear = yrs[1]
        # attempt to extract organization as first capitalized phrase
        org = ""
        title = ""
        lines_p = p.splitlines()
        if len(lines_p) >= 1:
            first = lines_p[0]
            # split by comma or dash
            parts0 = re.split(r"[,–\-—@]", first)
            if parts0:
                cand = parts0[0]
                # choose cand as org if contains "Inc|Ltd|LLC|Company|University|College" else leave
                if re.search(r"\b(Inc|Ltd|LLC|Company|University|College|Corp|Corporation|Institute)\b", cand, re.I):
                    org = cand.strip()
                else:
                    # heuristics: if contains title keywords set title else org
                    if any(k in cand.lower() for k in ["engineer","developer","manager","analyst","research","intern","consultant","officer","professor"]):
                        title = cand.strip()
                    else:
                        org = cand.strip()
        entries.append({
            "title": title,
            "organization": org,
            "startYear": startYear,
            "endYear": endYear,
            "details": p
        })
    return entries

def parse_publications(text: str) -> List[str]:
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # simple filter: lines with quotes or journal/conference words
        if '"' in line or "journal" in line.lower() or "conference" in line.lower() or "proceedings" in line.lower():
            items.append(line)
    return items

def assemble_full_schema(raw_text: str, sections: Dict[str, str]) -> Dict[str, Any]:
    # contact info from top + whole doc
    top = sections.get("top", "") or ""
    whole = raw_text or ""
    name = extract_name_from_top(top)
    emails = find_emails(whole)
    phones = find_phones(whole)
    urls = find_urls(whole)
    githubs = find_github(whole)
    linkedins = find_linkedin(whole)

    # education: prefer sections.education else try top/other
    edu_blob = sections.get("education") or sections.get("top") + "\n" + sections.get("other", "")
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
        "pgCollegeGpaScale": edu_parsed.get("pgCollegeGpaOrPercentage",""),
        "pgUniversity": edu_parsed.get("pgUniversity",""),
        "pgGraduationYear": edu_parsed.get("pgGraduationYear",""),
        "pgDegree": edu_parsed.get("pgDegree",""),
        "pgMajor": edu_parsed.get("pgMajor",""),
        "certifications": parse_certifications(sections.get("certifications","") or sections.get("other","")),
        "extraCurricularActivities": [s.strip() for s in (sections.get("extracurricular","") or "").splitlines() if s.strip()],
        "workExperience": parse_experience(sections.get("experience","") or sections.get("other","")),
        "researchPublications": parse_publications(sections.get("publications","") or ""),
        "testScores": parse_test_scores(sections.get("test_scores","") or whole),
        "achievements": [s.strip() for s in (sections.get("achievements","") or "").splitlines() if s.strip()],
        # you may include metadata/confidence here in the future
    }
    return out
