#!/usr/bin/env python3
"""
Normalization utilities:
- Clean whitespace
- Standardize GPA formats
- Normalize dates/years
- Provide confidence scoring hooks (simple heuristic)

Used after field extraction and before returning final JSON.
"""
import re
import dateparser
from typing import Dict, Any

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

def _valid_name(v: str) -> bool:
    return bool(v) and 2 <= len(v.split()) <= 4 and v.replace(" ", "").isalpha()

def _valid_college(v: str) -> bool:
    return bool(v) and re.search(r"(university|college|institute|school)", v.lower())

def _valid_degree(v: str) -> bool:
    return bool(v) and re.search(r"(bachelor|master|b\.sc|m\.sc|b\.tech|m\.tech|phd)", v.lower())

def _valid_work_block(w: dict) -> bool:
    return bool(w.get("organization") or w.get("title")) and bool(w.get("startYear"))

def _valid_cert(v: str) -> bool:
    return bool(v) and re.search(r"(certificat|certified|training)", v.lower())


def _clean_entity_text(s: str) -> str:
    if not s:
        return ""
    # drop emails, phones, urls
    s = re.sub(r"\S+@\S+", "", s)
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"\+?\d[\d\s\-()/]{6,}", "", s)

    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()

    # hard length cap (prevents paragraphs)
    if len(s.split()) > 10:
        return ""
    return s


def clean_whitespace(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def normalize_year(year_str: str) -> str:
    """
    Normalize graduation year into YYYY.
    If parsing fails or empty, return "".
    """
    if not year_str:
        return ""
    # Try direct regex match
    m = YEAR_RE.search(year_str)
    if m:
        return m.group(0)

    # Try dateparser on general input
    dt = dateparser.parse(year_str)
    if dt:
        return str(dt.year)
    return ""

def normalize_gpa_or_percentage(value: str, scale: str) -> (str, str):
    """
    Normalize GPA and scale.
    If it's percentage, keep scale = '%'.
    If GPA missing scale, infer.
    """
    if not value:
        return "", ""

    # Percentage case
    if "%" in scale or "%" in value:
        value = value.replace("%", "").strip()
        try:
            float(value)
            return value, "%"
        except Exception:
            return value, "%"

    # GPA case
    try:
        v = float(value)
    except Exception:
        return value, scale

    # If no scale, infer from typical ranges
    if not scale:
        if v <= 4.5:
            scale = "4"
        elif v <= 10:
            scale = "10"
        else:
            scale = ""
    return value, scale

def normalize_schema(final_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Takes the JSON produced by the parser and normalizes all fields.
    This function is SAFE, schema-locked, and UI/DB resistant.
    """

    # ----------------------------
    # 1) Basic scalar normalization
    # ----------------------------
    final_data["name"] = clean_whitespace(final_data.get("name", ""))
    final_data["email"] = clean_whitespace(final_data.get("email", ""))
    final_data["phoneNumber"] = clean_whitespace(final_data.get("phoneNumber", ""))

    # ----------------------------
    # 2) Normalize graduation years
    # ----------------------------
    for key in list(final_data.keys()):
        if "GraduationYear" in key or "graduationYear" in key:
            final_data[key] = normalize_year(final_data.get(key, ""))

    # ----------------------------
    # 3) GPA normalization
    # ----------------------------
    gpa_val, gpa_scale = normalize_gpa_or_percentage(
        final_data.get("highSchoolGpaOrPercentage", ""),
        final_data.get("highSchoolGpaScale", "")
    )
    final_data["highSchoolGpaOrPercentage"] = gpa_val
    final_data["highSchoolGpaScale"] = gpa_scale

    gpa_val, gpa_scale = normalize_gpa_or_percentage(
        final_data.get("ugCollegeGpaOrPercentage", ""),
        final_data.get("ugCollegeGpaScale", "")
    )
    final_data["ugCollegeGpaOrPercentage"] = gpa_val
    final_data["ugCollegeGpaScale"] = gpa_scale

    gpa_val, gpa_scale = normalize_gpa_or_percentage(
        final_data.get("pgCollegeGpaOrPercentage", ""),
        final_data.get("pgCollegeGpaScale", "")
    )
    final_data["pgCollegeGpaOrPercentage"] = gpa_val
    final_data["pgCollegeGpaScale"] = gpa_scale

    # ----------------------------
    # 4) Clean list fields
    # ----------------------------
    LIST_FIELDS = [
        "certifications",
        "extraCurricularActivities",
        "workExperience",
        "researchPublications",
        "achievements",
    ]

    for lf in LIST_FIELDS:
        if not isinstance(final_data.get(lf), list):
            final_data[lf] = []
            continue

        cleaned_list = []
        for item in final_data[lf]:
            if isinstance(item, str):
                cleaned_list.append(clean_whitespace(item))
            elif isinstance(item, dict):
                cleaned_list.append({
                    k: clean_whitespace(str(v)) for k, v in item.items()
                })
        final_data[lf] = cleaned_list

    # ----------------------------
    # 5) HARD sanitize education fields
    # ----------------------------
    for k in [
        "ugCollegeName", "ugDegree", "ugMajor",
        "pgCollegeName", "pgDegree", "pgMajor"
    ]:
        final_data[k] = _clean_entity_text(final_data.get(k, ""))

    # ----------------------------
    # 6) HARD sanitize work experience
    # ----------------------------
    cleaned_exp = []

    for w in final_data.get("workExperience", []):
        if not isinstance(w, dict):
            continue

        org = _clean_entity_text(w.get("organization", ""))
        title = _clean_entity_text(w.get("title", ""))
        start = normalize_year(w.get("startYear", ""))
        end = normalize_year(w.get("endYear", ""))
        details = w.get("details", [])

        # must have org or title + at least one year
        if not (org or title):
            continue
        if not (start or end):
            continue

        if not isinstance(details, list):
            details = []

        cleaned_exp.append({
            "organization": org,
            "title": title,
            "startYear": start,
            "endYear": end,
            "details": details
        })

    final_data["workExperience"] = cleaned_exp

    # ----------------------------
    # 7) FINAL schema guard (CRITICAL)
    # ----------------------------
    DEFAULT_LIST_FIELDS = [
        "certifications",
        "extraCurricularActivities",
        "workExperience",
        "researchPublications",
        "achievements"
    ]

    for f in DEFAULT_LIST_FIELDS:
        if f not in final_data or not isinstance(final_data[f], list):
            final_data[f] = []

    DEFAULT_STR_FIELDS = [
        "name", "email", "phoneNumber",
        "ugCollegeName", "ugDegree", "ugMajor",
        "pgCollegeName", "pgDegree", "pgMajor"
    ]

    for f in DEFAULT_STR_FIELDS:
        if f not in final_data or not isinstance(final_data[f], str):
            final_data[f] = ""

    return final_data


# ------------------ Confidence scoring (field-aware) ------------------
def _score_presence(value) -> float:
    """
    Base presence score: 1.0 if non-empty, otherwise 0.
    For lists/dicts we consider non-empty as present.
    """
    if value is None:
        return 0.0
    if isinstance(value, list):
        return 1.0 if len(value) > 0 else 0.0
    if isinstance(value, dict):
        return 1.0 if any(v for v in value.values()) else 0.0
    if isinstance(value, str):
        return 1.0 if value.strip() else 0.0
    return 0.0

def _score_name(name: str) -> float:
    if not name:
        return 0.0
    tokens = name.split()
    if len(tokens) >= 2:
        caps = sum(1 for t in tokens if t and t[0].isupper())
        return min(1.0, 0.5 + 0.12 * caps)
    return 0.5

def _score_year(value: str) -> float:
    if not value:
        return 0.0
    # If year looks valid
    if YEAR_RE.search(value):
        return 1.0
    # fuzzy numeric presence
    if any(ch.isdigit() for ch in value):
        return 0.8
    return 0.0

def _score_gpa(value: str) -> float:
    if not value:
        return 0.0
    try:
        v = float(re.sub(r"[^\d\.]", "", value))
        # heuristic: if in % range (0-100) map to 0..1
        if v > 10:
            return min(1.0, v / 100.0)
        # else assume 0..4 or 0..10
        return min(1.0, v / 4.0) if v <= 4.5 else min(1.0, v / 10.0)
    except Exception:
        return 0.8

def confidence_scores(parsed: Dict[str, Any]) -> Dict[str, float]:
    """
    Return per-field confidence (0..1) and percentage mapping plus an overall score (0..100).
    Structure:
    """
    confidence = {}

    def score_text(val: str) -> float:
        if not val:
            return 0.0
        words = len(val.split())
        if words >= 6:
            return 100.0
        if words >= 3:
            return 90.0
        return 80.0

    def score_list(items: list, min_items=1, good_items=3) -> float:
        if not items:
            return 0.0
        count = len(items)
        if count >= good_items:
            return 100.0
        if count >= min_items:
            return 90.0
        return 80.0

    # --- scalar fields ---
    confidence["name"] = score_text(parsed.get("name", ""))
    confidence["email"] = 100.0 if parsed.get("email") else 0.0
    confidence["phoneNumber"] = 100.0 if parsed.get("phoneNumber") else 0.0

    # --- education ---
    confidence["ugDegree"] = score_text(parsed.get("ugDegree", ""))
    confidence["ugMajor"] = score_text(parsed.get("ugMajor", ""))
    confidence["pgDegree"] = score_text(parsed.get("pgDegree", ""))
    confidence["pgMajor"] = score_text(parsed.get("pgMajor", ""))

    # --- experience ---
    exp = parsed.get("workExperience", [])
    confidence["workExperience"] = score_list(exp, min_items=1, good_items=2)

    # --- certifications ---
    certs = parsed.get("certifications", [])
    confidence["certifications"] = score_list(certs, min_items=1, good_items=2)

    # --- achievements ---
    ach = parsed.get("achievements", [])
    confidence["achievements"] = score_list(ach, min_items=1, good_items=2)

    # --- publications ---
    pubs = parsed.get("researchPublications", [])
    confidence["researchPublications"] = score_list(pubs, min_items=1, good_items=2)

    return confidence

def finalize_schema(final_data: dict, confidence: dict | None = None):
    """
    D-4: Final guardrails.
    - Remove empty lists / empty strings
    - Clamp confidence to valid keys only
    """
    # drop empty string fields
    for k in list(final_data.keys()):
        if final_data[k] == "" or final_data[k] == []:
            continue  # keep schema shape stable

    # confidence cleanup
    if confidence is not None:
        valid_keys = set(final_data.keys())
        confidence = {
            k: v for k, v in confidence.items()
            if k in valid_keys and isinstance(v, (int, float))
        }
        return final_data, confidence

    return final_data, None

