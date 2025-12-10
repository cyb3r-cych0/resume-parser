#!/usr/bin/env python3
"""
Multicore OCR processing
Worker function for parallel batch processing.
Each worker runs the full pipeline on one file.
"""
import time
from helpers.text_extraction import extract_text_from_bytes
from helpers.section_segmentation import split_into_sections
from helpers.field_extraction import assemble_full_schema
from helpers.normalization import normalize_schema, confidence_scores
import hashlib
import threading

_warmup_done = False
_cache_lock = threading.Lock()

def warmup_models():
    """
    Pre-load expensive components once at startup so
    the first real parse doesn't pay cold-start cost.
    Safe to call multiple times.
    """
    global _warmup_done
    with _cache_lock:
        if _warmup_done:
            return
        # Trigger lazy-loads
        try:
            from helpers.normalization import confidence_scores
            confidence_scores({}, "")  # warms transformers / tokenizers
        except Exception:
            pass
        _warmup_done = True

def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def process_single_file(filename: str, data: bytes):
    start_total = time.perf_counter()
    timings = {}

    # ---- caching layer (optional) ----
    try:
        def file_hash(d: bytes) -> str:
            return hashlib.sha256(d).hexdigest()

        h = file_hash(data)
        # try DB cache lookup (helpers/db.py function provided later)
        from helpers.db import get_record_by_hash
        cached = get_record_by_hash(h)
        if cached:
            # return cached envelope (fast-path)
            return {
                "file": filename,
                "status": "ok",
                "parsed": cached["parsed"],
                "parse_time": 0.0,
                "resume_quality_score": cached.get("resume_quality_score", 0),
                "confidence_percentage": cached.get("confidence_percentage", {}),
                "timings": {"cached": True}
            }
    except Exception:
        # any failure in cache check should not break parsing
        pass

    try:
        # OCR
        t0 = time.perf_counter()
        raw_text = extract_text_from_bytes(filename, data, use_magic=False)
        timings["ocr"] = time.perf_counter() - t0

        # Split
        t0 = time.perf_counter()
        sections = split_into_sections(raw_text)
        timings["split"] = time.perf_counter() - t0

        # Assemble
        t0 = time.perf_counter()
        schema = assemble_full_schema(raw_text, sections)
        timings["assemble"] = time.perf_counter() - t0

        # Normalize
        t0 = time.perf_counter()
        normalized = normalize_schema(schema)
        timings["normalize"] = time.perf_counter() - t0

        # Confidence
        t0 = time.perf_counter()
        conf_bundle = confidence_scores(normalized, raw_text)
        timings["confidence"] = time.perf_counter() - t0

        # Extract summary
        resume_score = conf_bundle.get("overall_quality_score", 0.0)
        conf_pct = conf_bundle.get("percentage_scores") or conf_bundle

        total = time.perf_counter() - start_total

        # Attempt to save cache (best-effort; ignore failures)
        try:
            def file_hash(d: bytes) -> str:
                return hashlib.sha256(d).hexdigest()

            h = file_hash(data)
            from helpers.db import save_hash_cache
            save_hash_cache(h, normalized, resume_score, conf_pct)
        except Exception:
            pass
        return {
            "file": filename,
            "status": "ok",
            "parsed": normalized,
            "timings": timings,
            "parse_time": total,
            "resume_quality_score": resume_score,
            "confidence_percentage": conf_pct
        }
    except Exception as e:
        return {"file": filename, "status": "error", "error": str(e)}
