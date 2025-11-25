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
"""

import re
from typing import Dict, List, Tuple
from rapidfuzz import process, fuzz

# Known canonical section keys and common variants
SECTION_KEYWORDS = {
    "education": ["education", "academic background", "academic qualifications", "qualifications", "education & training"],
    "experience": ["experience", "work experience", "professional experience", "employment history", "work history"],
    "projects": ["projects", "personal projects", "selected projects"],
    "skills": ["skills", "technical skills", "skills & tools", "languages"],
    "certifications": ["certifications", "certificates", "licenses"],
    "publications": ["publications", "research publications", "papers"],
    "achievements": ["achievements", "awards", "honors"],
    "extracurricular": ["extracurricular", "activities", "extra-curricular activities"],
    "test_scores": ["test scores", "scores", "standardized tests", "test results"],
    "summary": ["summary", "profile", "professional summary", "about me", "objective"]
}

# Flatten variants for fuzzy matching
FLAT_VARIANTS = []
for k, variants in SECTION_KEYWORDS.items():
    for v in variants:
        FLAT_VARIANTS.append((v, k))

# regex to detect a heading-like line
HEADING_RE = re.compile(r"^[A-Z \-]{3,}$")  # all-caps short headings
COLON_HEADING_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 &\-]{1,60}:$")  # "Education:", etc.
LINE_SPLIT_RE = re.compile(r"\r\n|\r|\n")

def candidate_heading(line: str) -> bool:
    line = line.strip()
    if not line:
        return False
    # obvious patterns
    if HEADING_RE.match(line):
        return True
    if COLON_HEADING_RE.match(line):
        return True
    # short lines with keyword-like characters
    if len(line) <= 40 and " " in line and line.lower().split()[0] in ("education","experience","skills","projects","certifications","summary","publications","awards","achievements","test"):
        return True
    return False

def map_heading_to_section(heading: str, score_threshold: int = 60) -> Tuple[str, int]:
    """
    Map free-form heading to a canonical section key using fuzzy matching.
    Returns (section_key, score). If none matched, returns ("other", 0).
    """
    heading_norm = heading.lower().strip().rstrip(":")
    choices = [v for v, k in FLAT_VARIANTS]
    match, score, idx = process.extractOne(heading_norm, choices, scorer=fuzz.QRatio, score_cutoff=score_threshold) or (None, 0, None)
    if match:
        # find canonical key
        for variant, key in FLAT_VARIANTS:
            if variant == match:
                return key, score
    return "other", 0

def split_into_sections(text: str, min_heading_score: int = 60) -> Dict[str, str]:
    """
    Splits raw resume text into sections.
    Returns a dict with canonical keys (education, experience, skills, etc.) and 'other' for uncategorized parts.
    """
    lines = [l.rstrip() for l in LINE_SPLIT_RE.split(text)]
    # find heading line indexes
    headings: List[Tuple[int, str]] = []
    for i, line in enumerate(lines):
        if candidate_heading(line):
            headings.append((i, line.strip()))
    # Always treat start as implicit heading "top"
    splits: List[Tuple[int, int, str]] = []  # (start_idx, end_idx, heading)
    if not headings:
        # everything is one section
        return {"other": text.strip()}

    # Build split ranges
    for idx, (line_no, heading_text) in enumerate(headings):
        start = line_no + 1  # content begins after heading line
        if idx + 1 < len(headings):
            end = headings[idx + 1][0]  # up to next heading line
        else:
            end = len(lines)
        splits.append((start, end, heading_text))

    # If there is text before the first detected heading, include it under 'top'
    first_heading_line = headings[0][0]
    result: Dict[str, List[str]] = {}
    if first_heading_line > 0:
        pre_text = "\n".join(lines[:first_heading_line]).strip()
        if pre_text:
            result.setdefault("top", []).append(pre_text)

    # Map each split to canonical key
    for start, end, heading_text in splits:
        mapped_key, score = map_heading_to_section(heading_text, score_threshold=min_heading_score)
        body = "\n".join(lines[start:end]).strip()
        if not body:
            continue
        key = mapped_key if mapped_key != "other" else "other"
        result.setdefault(key, []).append(body)

    # Join lists into single strings
    final: Dict[str, str] = {}
    for k, parts in result.items():
        final[k] = "\n\n".join(parts).strip()

    # Ensure all canonical keys exist (might be empty)
    for canonical in SECTION_KEYWORDS.keys():
        final.setdefault(canonical, "")

    # always include 'other' & 'top'
    final.setdefault("other", "")
    final.setdefault("top", "")

    return final

# CLI quick test
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python helpers/section_segmentation.py /path/to/textfile.txt")
        sys.exit(1)
    p = sys.argv[1]
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        txt = f.read()
    secs = split_into_sections(txt)
    for k, v in secs.items():
        if v:
            print("----", k.upper(), "----")
            print(v[:2000])
            print()
