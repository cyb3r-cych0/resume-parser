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

def process_single_file(filename: str, data: bytes, model_name: str = "en_core_web_sm", use_cache: bool = True) -> Dict[str, Any]:
    """
    Process one file and return an envelope containing:
    {
      "file": filename,
      "status": "ok" or "error",
      "parsed": {...},
      "timings": {"ocr":.., "split":.., "assemble":.., "normalize":.., "confidence":..},
      "parse_time": total_seconds,
      "resume_quality_score": ..,
      "confidence_percentage": {...}
    }
    """
    start_total = time.perf_counter()
    timings = {}

    # Try model load in caller; process_single_file expects model_name but does not force load here.
    # Cache lookup (model-aware)
    if use_cache:
        try:
            h = compute_file_hash(data, model_name)
            cached = get_record_by_hash(h)
            if cached:
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
            # non-fatal: continue parsing
            pass
    try:
        # OCR / text extraction
        t0 = time.perf_counter()
        raw_text = extract_text_from_bytes(filename, data, use_magic=False)
        timings['ocr'] = time.perf_counter() - t0

        # section split
        t0 = time.perf_counter()
        sections = split_into_sections(raw_text)
        timings['split'] = time.perf_counter() - t0

        # attempt to load spaCy model if needed (lazily) for richer assembly / NER augmentation
        nlp = None
        try:
            from helpers.spacy_loader import get_spacy_model
            nlp = get_spacy_model(model_name)
        except Exception:
            # if model not available, continue — assemble_full_schema must handle nlp=None
            nlp = None

        # Assemble: prefer assemble_full_schema(raw_text, sections, nlp=nlp) if supported
        t0 = time.perf_counter()
        try:
            schema = assemble_full_schema(raw_text, sections, nlp=nlp)
        except TypeError:
            # fallback if assemble_full_schema doesn't accept nlp
            schema = assemble_full_schema(raw_text, sections)
        timings['assemble'] = time.perf_counter() - t0

        # Normalize
        t0 = time.perf_counter()
        normalized = normalize_schema(schema)
        timings['normalize'] = time.perf_counter() - t0

        # NER augmentation (non-fatal)
        try:
            from helpers.ner_utils import extract_ner_hints
            if nlp:
                ner_hints = extract_ner_hints(raw_text, nlp)
                # apply hints only if fields missing (non-destructive)
                if not normalized.get("name"):
                    name_hint = ner_hints.get("name")
                    if name_hint:
                        normalized["name"] = name_hint
                colleges = ner_hints.get("colleges", []) or ner_hints.get("orgs", [])
                if colleges:
                    if not normalized.get("ugCollegeName"):
                        normalized["ugCollegeName"] = colleges[0]
                    if not normalized.get("pgCollegeName") and len(colleges) > 1:
                        normalized["pgCollegeName"] = colleges[1]
                degrees = ner_hints.get("degrees", [])
                majors = ner_hints.get("majors", [])
                if degrees:
                    d0 = degrees[0]
                    if any(k.lower() in d0.lower() for k in ["master", "m.", "mba", "msc", "post"]):
                        if not normalized.get("pgDegree"):
                            normalized["pgDegree"] = d0
                    else:
                        if not normalized.get("ugDegree"):
                            normalized["ugDegree"] = d0
                if majors:
                    if not normalized.get("ugMajor"):
                        normalized["ugMajor"] = majors[0]
                    elif not normalized.get("pgMajor") and len(majors) > 1:
                        normalized["pgMajor"] = majors[1]
        except Exception:
            pass

        # Confidence scoring
        t0 = time.perf_counter()
        conf_bundle = confidence_scores(normalized, raw_text)
        timings['confidence'] = time.perf_counter() - t0

        resume_score = conf_bundle.get("overall_quality_score") or conf_bundle.get("overall", 0.0)
        conf_pct = conf_bundle.get("percentage_scores") if isinstance(conf_bundle, dict) else conf_bundle

        total_elapsed = time.perf_counter() - start_total

        # Save cache (best-effort)
        if use_cache:
            try:
                h = compute_file_hash(data, model_name)
                save_hash_cache(h, normalized, resume_score, conf_pct)
            except Exception:
                pass
        return {
            "file": filename,
            "status": "ok",
            "parsed": normalized,
            "timings": timings,
            "parse_time": total_elapsed,
            "resume_quality_score": resume_score,
            "confidence_percentage": conf_pct or {}
        }
    except Exception as e:
        traceback.print_exc()
        total_elapsed = time.perf_counter() - start_total
        return {"file": filename, "status": "error", "error": str(e), "parse_time": total_elapsed}
