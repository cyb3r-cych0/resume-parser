#!/usr/bin/env python3
"""
Multicore OCR processing
Worker function for parallel batch processing.
Each worker runs the full pipeline on one file.
"""
import time
import hashlib
import threading
import traceback
from typing import Dict, Any

# local pipeline helpers
from helpers.section_classifier import classify_sections
from helpers.field_extraction import assemble_full_schema
from helpers.db import save_hash_cache, get_record_by_hash
from helpers.text_extraction import extract_text_from_bytes
from helpers.section_segmentation import split_into_sections
from helpers.normalization import normalize_schema, confidence_scores

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
            confidence_scores({}, "")  # warms transformers / tokenizers
        except Exception:
            pass
        _warmup_done = True

def compute_file_hash(file_bytes: bytes, model_name: str = "") -> str:
    """
    Compute SHA256 hash based on file bytes + model_name so cache is model-aware.
    """
    h = hashlib.sha256()
    h.update(file_bytes or b"")
    h.update((model_name or "").encode("utf-8"))
    return h.hexdigest()

def process_single_file(
    filename: str,
    data: bytes,
    model_name: str = "en_core_web_sm",
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Process one file and return an envelope containing:
    {
      "file": filename,
      "status": "ok" or "error",
      "parsed": {...},
      "timings": {...},
      "parse_time": float,
      "resume_quality_score": float,
      "confidence_percentage": {...},
      "saved_to_db": bool
    }
    """

    QUALITY_SAVE_THRESHOLD = 70.0

    start_total = time.perf_counter()
    timings = {}

    # -------------------------------
    # Cache lookup (model-aware)
    # -------------------------------
    if use_cache:
        try:
            h = compute_file_hash(data, model_name)
            cached = get_record_by_hash(h)
            if cached:
                return {
                    "file": filename,
                    "status": "ok",
                    "parsed": cached["parsed"],
                    "timings": {"cached": True},
                    "parse_time": 0.0,
                    "resume_quality_score": cached.get("resume_quality_score", 0.0),
                    "confidence_percentage": cached.get("confidence_percentage", {}),
                    "saved_to_db": True
                }
        except Exception:
            pass  # non-fatal

    try:
        # -------------------------------
        # OCR / text extraction
        # -------------------------------
        t0 = time.perf_counter()
        raw_text = extract_text_from_bytes(filename, data, use_magic=False)
        timings["ocr"] = time.perf_counter() - t0

        # -------------------------------
        # Section segmentation
        # -------------------------------
        t0 = time.perf_counter()
        sections = split_into_sections(raw_text)
        timings["split"] = time.perf_counter() - t0

        # -------------------------------
        # Section classification
        # -------------------------------
        try:
            section_labels = classify_sections(sections)
            canonical_sections = {}
            for raw_key, text in sections.items():
                label = section_labels.get(raw_key, "other") or "other"
                canonical_sections[label] = (
                    canonical_sections.get(label, "") + "\n\n" + (text or "")
                ).strip()
        except Exception:
            canonical_sections = sections

        # -------------------------------
        # Load spaCy (lazy)
        # -------------------------------
        try:
            from helpers.spacy_loader import get_spacy_model
            nlp = get_spacy_model(model_name)
        except Exception:
            nlp = None

        # -------------------------------
        # Semantic extraction
        # -------------------------------
        from helpers.semantic_extraction import build_final_schema

        t0 = time.perf_counter()
        try:
            semantic_res = build_final_schema(raw_text, canonical_sections, nlp=nlp)
            schema = semantic_res.get("parsed", {})
            extra_confidence = semantic_res.get("confidence_percentage", {})
            timings.update(semantic_res.get("timings", {}))
        except Exception:
            schema = assemble_full_schema(raw_text, canonical_sections, nlp=nlp)
            extra_confidence = {}

        timings["assemble"] = time.perf_counter() - t0

        # -------------------------------
        # Normalize schema
        # -------------------------------
        normalized = normalize_schema(schema)

        # -------------------------------
        # Confidence scoring (single source of truth)
        # -------------------------------
        t0 = time.perf_counter()

        if extra_confidence:
            confidence_percentage = extra_confidence
        else:
            confidence_percentage = {
                k: float(v) for k, v in confidence_scores(normalized).items()
            }

        resume_quality_score = round(
            sum(confidence_percentage.values()) / max(len(confidence_percentage), 1),
            1
        )

        timings["confidence"] = time.perf_counter() - t0

        # -------------------------------
        # Quality-gated persistence
        # -------------------------------
        saved_to_db = False
        if use_cache and resume_quality_score >= QUALITY_SAVE_THRESHOLD:
            try:
                h = compute_file_hash(data, model_name)
                save_hash_cache(
                    h,
                    normalized,
                    resume_quality_score,
                    confidence_percentage
                )
                saved_to_db = True
            except Exception:
                pass

        total_elapsed = time.perf_counter() - start_total

        return {
            "file": filename,
            "status": "ok",
            "parsed": normalized,
            "timings": timings,
            "parse_time": total_elapsed,
            "resume_quality_score": resume_quality_score,
            "confidence_percentage": confidence_percentage,
            "saved_to_db": saved_to_db
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "file": filename,
            "status": "error",
            "error": str(e),
            "parse_time": time.perf_counter() - start_total
        }
