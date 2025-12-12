#!/usr/bin/env python3
"""
- Reads uploaded file bytes
- Extracts text (native PDF / DOCX / OCR fallback)
- Splits text into sections (Education/Experience/etc.)
- Extracts fields into your full schema
- Normalizes values (years, GPA) and returns optional confidence scores
- Returns final JSON
- Stores raw bytes in DB to re-run parsing without re-upload.
    -> /parse and /parse/batch save raw bytes when save=true
    -> GET /records/{id}/download (download original file),
    -> POST /records/{id}/reparse (re-run parsing using stored raw bytes and save new record),
"""
import os
import io
import time
import traceback
from typing import List
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

# pipeline helpers (local modules)
from helpers.db import delete_record
from helpers.batch_worker import warmup_models
from helpers.spacy_loader import ALLOWED_MODELS
from helpers.batch_worker import process_single_file
from helpers.field_extraction import assemble_full_schema
from helpers.text_extraction import extract_text_from_bytes
from helpers.section_segmentation import split_into_sections
from helpers.normalization import normalize_schema, confidence_scores
from helpers.db import init_db, save_parsed_result, get_record, get_raw_bytes, list_records, delete_hash_cache

app = FastAPI(title="Parsely-API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# initialize DB
init_db()

# prevent any library from reaching hugging face (offline-mode)
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"

# warm up model
@app.on_event("startup")
def startup_event():
    warmup_models()

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2.0"}

@app.delete("/records/{record_id}")
def api_delete_record(record_id: int):
    try:
        ok = delete_record(record_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Record not found")
        return {"status": "ok", "deleted_id": record_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")

@app.post("/parse")
async def parse_resume(file: UploadFile = File(...),
                       include_confidence: bool = False,
                       save: bool = Query(False),
                       model: str = Query("en_core_web_sm"),
                       cache: bool = Query(True)):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    if model not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"Unsupported model '{model}'. Choose one of {ALLOWED_MODELS}")
    try:
        contents = await file.read()
        if not contents or len(contents) < 4:
            raise HTTPException(status_code=422, detail="Empty or invalid file")
        # process using worker; pass cache flag
        r = process_single_file(file.filename or "uploaded", contents, model_name=model, use_cache=cache)
        if r.get("status") != "ok":
            # expose worker error to client
            raise HTTPException(status_code=422, detail=r.get("error") or "Parsing failed")
        # Save to DB if requested
        if save:
            try:
                rec_id = save_parsed_result(r.get("file"), r.get("parsed"), raw_bytes=contents, status="ok", source="api")
                r["db_id"] = rec_id
            except Exception as e:
                r["db_save_error"] = str(e)

        # prune confidence if not requested
        if not include_confidence:
            r.pop("confidence_percentage", None)
        return {
            "status": "ok",
            "file": r.get("file"),
            "parsed": r.get("parsed"),
            "timings": r.get("timings"),
            "parse_time": r.get("parse_time"),
            "resume_quality_score": r.get("resume_quality_score"),
            "confidence_percentage": r.get("confidence_percentage", {})
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

@app.post("/parse/batch")
async def parse_batch(files: List[UploadFile] = File(...),
                      save: bool = Query(False),
                      model: str = Query("en_core_web_sm"),
                      cache: bool = Query(True)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if model not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"Unsupported model '{model}'. Choose one of {ALLOWED_MODELS}")

    payload = []
    for f in files:
        contents = await f.read()
        payload.append((f.filename or "unknown", contents))

    results = []

    cpu = os.cpu_count() or 2
    max_workers = min(max(1, cpu - 1), len(payload))
    max_workers_cap = int(os.getenv("MAX_WORKERS_CAP", "6"))
    max_workers = min(max_workers, max_workers_cap)

    _use_thread_executor = len(payload) <= 4
    executor_cls = ThreadPoolExecutor if _use_thread_executor else ProcessPoolExecutor
    try:
        with executor_cls(max_workers=max_workers) as ex:
            start_time = time.perf_counter()
            # submit with model_name and cache flag
            futures = [ex.submit(process_single_file, filename, data, model, cache) for filename, data in payload]
            for fut in futures:
                r = fut.result()
                if r.get("status") == "ok":
                    if save:
                        try:
                            rec_id = save_parsed_result(r.get("file"), r.get("parsed"), raw_bytes=next((b for n,b in payload if n==r.get("file")), None), status="ok", source="batch")
                            r["db_id"] = rec_id
                        except Exception as e:
                            r["db_save_error"] = str(e)
                results.append(r)
            elapsed = time.perf_counter() - start_time
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch processing failed: {e}")

    return {"batch_count": len(results), "results": results, "parse_time": elapsed}

@app.get("/records")
def api_list_records(limit: int = 50, offset: int = 0):
    return {"count": len(list_records(limit=limit, offset=offset)), "results": list_records(limit=limit, offset=offset)}

@app.get("/records/{record_id}")
def api_get_record(record_id: int):
    rec = get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found")
    return rec

@app.get("/records/{record_id}/download")
def api_download_record_file(record_id: int):
    raw = get_raw_bytes(record_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Raw file not found for this record")
    return StreamingResponse(io.BytesIO(raw), media_type="application/octet-stream")

@app.post("/records/{record_id}/reparse")
def api_reparse_record(record_id: int, include_confidence: bool = False, save: bool = Query(True)):
    """
    Re-run parsing on the raw file bytes stored in DB for record_id.
    Saves a new record when 'save' is true and returns parsed result.
    """
    raw = get_raw_bytes(record_id)
    rec_meta = get_record(record_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="No stored raw file for this record (cannot reparse)")
    # Use the same pipeline as parse_single: extract text -> split -> assemble -> normalize
    try:
        raw_text = extract_text_from_bytes(rec_meta.get("filename", ""), raw, use_magic=False)
        if not raw_text or len(raw_text.strip()) < 3:
            raise HTTPException(status_code=422, detail="Could not extract text from stored file")

        sections = split_into_sections(raw_text)
        schema = assemble_full_schema(raw_text, sections)
        normalized = normalize_schema(schema)
        result = {"parsed": normalized}

        if include_confidence:
            try:
                result["confidence"] = confidence_scores(normalized, raw_text) or {}
            except Exception:
                result["confidence"] = {}
        if save:
            new_id = save_parsed_result(rec_meta.get("filename"), normalized, raw_bytes=raw, status="ok", source=f"reparse_from_{record_id}")
            result["db_id"] = new_id
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reparse failed: {e}")

@app.post("/save")
async def save_record(payload: dict):
    """
    Save parsed JSON to DB: expects {"filename": "...", "parsed": {...}}
    """
    try:
        filename = payload.get("filename", "unknown")
        parsed = payload.get("parsed", {})
        rec_id = save_parsed_result(filename, parsed, status="ok", source="manual_save")
        return {"status": "ok", "id": rec_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cache/clear")
def api_clear_cache():
    """
    Clear the hash cache table (used for model-aware caching).
    """
    try:
        delete_hash_cache()
        return {"status": "ok", "message": "Cache cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {e}")
