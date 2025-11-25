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


def confidence_scores(final_data: Dict[str, Any], raw_text: str) -> Dict[str, float]:
    """
    Returns simple confidence scores (0 to 1) for certain fields.
    This is *optional*. 
    You can integrate this later into API response if needed.

    Heuristic scoring:
      name: score by number of tokens + capitalization
      email/phone: high if found by regex
      education fields: moderate if matched by pattern
    """
    scores = {}

    # name confidence
    name = final_data.get("name", "")
    if name:
        tokens = name.split()
        if len(tokens) >= 2:
            # heuristic: higher confidence for two+ capitalized tokens
            caps = sum(1 for t in tokens if t[0].isupper())
            scores["name"] = min(1.0, 0.5 + 0.1 * caps)
        else:
            scores["name"] = 0.4
    else:
        scores["name"] = 0.0

    # email confidence
    scores["email"] = 1.0 if final_data.get("email") else 0.0

    # phone confidence
    scores["phoneNumber"] = 0.8 if final_data.get("phoneNumber") else 0.0

    # years
    for key in final_data.keys():
        if "GraduationYear" in key:
            scores[key] = 0.8 if final_data[key] else 0.0

    # gpa fields
    for key in final_data.keys():
        if "GpaOrPercentage" in key:
            scores[key] = 0.7 if final_data[key] else 0.0

    return scores
