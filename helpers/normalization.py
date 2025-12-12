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
    Takes the JSON produced by field_extraction.Compile and normalizes all fields.
    """
    # normalize name
    final_data["name"] = clean_whitespace(final_data.get("name", ""))

    # email + phone already extracted, just strip whitespace
    final_data["email"] = clean_whitespace(final_data.get("email", ""))
    final_data["phoneNumber"] = clean_whitespace(final_data.get("phoneNumber", ""))

    # normalize years
    for key in list(final_data.keys()):
        if "GraduationYear" in key or "graduationYear" in key:
            final_data[key] = normalize_year(final_data.get(key, ""))

    # normalize GPA fields
    # high school
    gpa_val, gpa_scale = normalize_gpa_or_percentage(
        final_data.get("highSchoolGpaOrPercentage", ""),
        final_data.get("highSchoolGpaScale", "")
    )
    final_data["highSchoolGpaOrPercentage"] = gpa_val
    final_data["highSchoolGpaScale"] = gpa_scale

    # undergraduate
    gpa_val, gpa_scale = normalize_gpa_or_percentage(
        final_data.get("ugCollegeGpaOrPercentage", ""),
        final_data.get("ugCollegeGpaScale", "")
    )
    final_data["ugCollegeGpaOrPercentage"] = gpa_val
    final_data["ugCollegeGpaScale"] = gpa_scale

    # postgraduate
    gpa_val, gpa_scale = normalize_gpa_or_percentage(
        final_data.get("pgCollegeGpaOrPercentage", ""),
        final_data.get("pgCollegeGpaScale", "")
    )
    final_data["pgCollegeGpaOrPercentage"] = gpa_val
    final_data["pgCollegeGpaScale"] = gpa_scale

    # clean strings in lists and nested dicts
    list_fields = [
        "certifications",
        "extraCurricularActivities",
        "workExperience",
        "researchPublications",
        "achievements",
    ]
    for lf in list_fields:
        if isinstance(final_data.get(lf), list):
            cleaned = []
            for item in final_data[lf]:
                if isinstance(item, str):
                    cleaned.append(clean_whitespace(item))
                elif isinstance(item, dict):
                    cleaned.append({k: clean_whitespace(str(v)) for k, v in item.items()})
            final_data[lf] = cleaned

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
    return 0.3

def _score_year(value: str) -> float:
    if not value:
        return 0.0
    # If year looks valid
    if YEAR_RE.search(value):
        return 0.9
    # fuzzy numeric presence
    if any(ch.isdigit() for ch in value):
        return 0.5
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
        return 0.5

def confidence_scores(final_data: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    """
    Return per-field confidence (0..1) and percentage mapping plus an overall score (0..100).
    Structure:
    {
      "<field>": 0.8,
      ...
      "percentage_scores": {"<field>": 80.0, ...},
      "overall_quality_score": 72.4
    }
    """
    scores: Dict[str, float] = {}

    # name
    scores["name"] = _score_name(final_data.get("name", ""))

    # email/phone
    scores["email"] = 1.0 if final_data.get("email") else 0.0
    scores["phoneNumber"] = 0.8 if final_data.get("phoneNumber") else 0.0

    # education year & degree confidence
    for key in final_data.keys():
        if "GraduationYear" in key or "graduationYear" in key:
            scores[key] = _score_year(final_data.get(key, ""))

    # GPA / percentage fields
    for key in final_data.keys():
        if "GpaOrPercentage" in key or "gpaOrPercentage" in key:
            scores[key] = _score_gpa(final_data.get(key, ""))

    # certifications / experience / pubs / achievements presence
    scores["certifications"] = _score_presence(final_data.get("certifications", []))
    scores["workExperience"] = _score_presence(final_data.get("workExperience", []))
    scores["researchPublications"] = _score_presence(final_data.get("researchPublications", []))
    scores["achievements"] = _score_presence(final_data.get("achievements", []))

    # degree & major presence
    scores["ugDegree"] = _score_presence(final_data.get("ugDegree", ""))
    scores["ugMajor"] = _score_presence(final_data.get("ugMajor", ""))
    scores["pgDegree"] = _score_presence(final_data.get("pgDegree", ""))
    scores["pgMajor"] = _score_presence(final_data.get("pgMajor", ""))

    # compute weighted overall score: assign weights (higher weight to name/email/experience/education)
    weight_map = {
        "name": 2.0,
        "email": 2.0,
        "phoneNumber": 1.0,
        "workExperience": 2.0,
        "certifications": 0.6,
        "researchPublications": 0.6,
        "achievements": 0.6,
        "ugDegree": 1.0,
        "ugMajor": 1.0,
        "pgDegree": 0.8,
        "pgMajor": 0.8
    }

    total_weight = 0.0
    weighted_sum = 0.0
    for k, v in scores.items():
        w = weight_map.get(k, 0.4)  # default small weight
        total_weight += w
        weighted_sum += (v * w)

    overall = (weighted_sum / total_weight) * 100.0 if total_weight > 0 else 0.0

    # percentage scores mapping for front-end friendliness
    pct_scores = {k: round(v * 100, 1) for k, v in scores.items()}

    # final bundle
    out = dict(scores)
    out["percentage_scores"] = pct_scores
    out["overall_quality_score"] = round(overall, 1)
    return out
