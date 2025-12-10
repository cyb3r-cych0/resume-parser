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
    Takes the JSON produced by field_extraction.compile_schema()
    and normalizes all fields.
    """

    # normalize name
    final_data["name"] = clean_whitespace(final_data.get("name", ""))

    # email + phone already extracted, just strip whitespace
    final_data["email"] = clean_whitespace(final_data.get("email", ""))
    final_data["phoneNumber"] = clean_whitespace(final_data.get("phoneNumber", ""))

    # normalize years
    for key in final_data.keys():
        if "GraduationYear" in key:
            final_data[key] = normalize_year(final_data[key])

    # normalize GPA fields
    # high school
    gpa_val, gpa_scale = normalize_gpa_or_percentage(
        final_data.get("highSchoolGpaOrPercentage",""),
        final_data.get("highSchoolGpaScale","")
    )
    final_data["highSchoolGpaOrPercentage"] = gpa_val
    final_data["highSchoolGpaScale"] = gpa_scale

    # undergraduate
    gpa_val, gpa_scale = normalize_gpa_or_percentage(
        final_data.get("ugCollegeGpaOrPercentage",""),
        final_data.get("ugCollegeGpaScale","")
    )
    final_data["ugCollegeGpaOrPercentage"] = gpa_val
    final_data["ugCollegeGpaScale"] = gpa_scale

    # postgraduate
    gpa_val, gpa_scale = normalize_gpa_or_percentage(
        final_data.get("pgCollegeGpaOrPercentage",""),
        final_data.get("pgCollegeGpaScale","")
    )
    final_data["pgCollegeGpaOrPercentage"] = gpa_val
    final_data["pgCollegeGpaScale"] = gpa_scale

    # clean strings in lists
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
                    # clean all dict values
                    cleaned.append({k: clean_whitespace(str(v)) for k, v in item.items()})
            final_data[lf] = cleaned
    return final_data

def confidence_scores(final_data: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    """
    Returns:
        {
            "raw_scores": {field: 0–1},
            "percentage_scores": {field: 0–100},
            "overall_quality_score": float (0–100)
        }
    The score system is intentionally simple:
    - 1.0  → Very confident extraction
    - 0.7  → Reasonable confidence (pattern matched)
    - 0.4  → Weak confidence (minimal detection)
    - 0.0  → Missing
    """
    scores = {}
    # ---- NAME ----
    name = final_data.get("name", "")
    if name:
        tokens = name.split()
        caps = sum(1 for t in tokens if t and t[0].isupper())
        if len(tokens) >= 2:
            scores["name"] = min(1.0, 0.5 + (caps * 0.15))
        else:
            scores["name"] = 0.4
    else:
        scores["name"] = 0.0

    # ---- EMAIL ----
    scores["email"] = 1.0 if final_data.get("email") else 0.0

    # ---- PHONE ----
    scores["phoneNumber"] = 0.9 if final_data.get("phoneNumber") else 0.0

    # ---- EDUCATION YEARS ----
    for key in final_data.keys():
        if "GraduationYear" in key:
            scores[key] = 0.8 if final_data[key] else 0.0

    # ---- GPA ----
    for key in final_data.keys():
        if "GpaOrPercentage" in key:
            scores[key] = 0.75 if final_data[key] else 0.0

    # ---- DEGREES / MAJORS (UG & PG) ----
    academic_keys = ["ugDegree", "ugMajor", "pgDegree", "pgMajor"]
    for k in academic_keys:
        scores[k] = 0.85 if final_data.get(k) else 0.0

    # ---- COLLEGE / UNIVERSITY NAMES ----
    org_fields = ["ugCollegeName", "pgCollegeName", "ugUniversity", "pgUniversity"]
    for k in org_fields:
        scores[k] = 0.9 if final_data.get(k) else 0.0

    # ---- WORK EXPERIENCE ----
    # Each block gets averaged internally
    exp_list = final_data.get("workExperience", [])
    if exp_list:
        exp_scores = []
        for entry in exp_list:
            local_score = 0
            if entry.get("title"): local_score += 0.35
            if entry.get("organization"): local_score += 0.35
            if entry.get("startYear"): local_score += 0.15
            if entry.get("endYear"): local_score += 0.15
            exp_scores.append(min(1.0, local_score))
        scores["workExperience"] = sum(exp_scores) / len(exp_scores)
    else:
        scores["workExperience"] = 0.0

    # ---- CERTIFICATIONS, ACHIEVEMENTS, PUBLICATIONS ----
    list_fields = ["certifications", "achievements", "researchPublications"]
    for lf in list_fields:
        arr = final_data.get(lf, [])
        if arr:
            # more items → higher confidence, capped at 1.0
            scores[lf] = min(1.0, 0.4 + 0.15 * len(arr))
        else:
            scores[lf] = 0.0

    # ----- Convert to percentages -----
    percentage_scores = {k: round(v * 100, 1) for k, v in scores.items()}

    # ----- Overall quality score -----
    numeric_vals = [v for v in scores.values() if isinstance(v, float)]
    overall_quality = (sum(numeric_vals) / len(numeric_vals) * 100) if numeric_vals else 0.0

    return {
        "raw_scores": scores,
        "percentage_scores": percentage_scores,
        "overall_quality_score": round(overall_quality, 2),
    }
