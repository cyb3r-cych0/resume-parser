#!/usr/bin/env python3
"""
Multicore OCR processing
Worker function for parallel batch processing.
Each worker runs the full pipeline on one file.
"""

import traceback
from helpers.text_extraction import extract_text_from_bytes
from helpers.section_segmentation import split_into_sections
from helpers.field_extraction import assemble_full_schema
from helpers.normalization import normalize_schema


def process_single_file(name: str, data: bytes) -> dict:
    """
    Process ONE resume (full OCR pipeline).
    Runs inside separate processes (safe for OCR).
    """
    try:
        raw_text = extract_text_from_bytes(name, data, use_magic=False)
        if not raw_text or len(raw_text.strip()) < 3:
            return {
                "file": name,
                "status": "error",
                "error": "Could not extract text (OCR failed or invalid file).",
                "parsed": None,
            }

        sections = split_into_sections(raw_text)
        schema = assemble_full_schema(raw_text, sections)
        normalized = normalize_schema(schema)

        return {
            "file": name,
            "status": "ok",
            "parsed": normalized
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "file": name,
            "status": "exception",
            "error": str(e),
            "parsed": None
        }
