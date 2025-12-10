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
import traceback
from typing import Optional, List
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import io
import time
import os
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from helpers.batch_worker import warmup_models

# pipeline helpers (local modules)
from helpers.text_extraction import extract_text_from_bytes
from helpers.section_segmentation import split_into_sections
from helpers.field_extraction import assemble_full_schema
from helpers.normalization import normalize_schema, confidence_scores
from helpers.batch_worker import process_single_file
from helpers.db import init_db, save_parsed_result, get_record, get_raw_bytes, list_records
from helpers.db import delete_record

app = FastAPI(title="Parsely-API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# initialize DB
init_db()

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
async def parse_resume(
    file: UploadFile = File(...),
    include_confidence: bool = False,
    save: bool = Query(False),
):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    try:
        contents = await file.read()
        if not contents or len(contents) < 4:
            raise HTTPException(status_code=422, detail="Empty or invalid file")

        start_time = time.perf_counter()

        raw_text = extract_text_from_bytes(file.filename or "", contents, use_magic=False)
        if not raw_text or len(raw_text.strip()) < 3:
            raise HTTPException(
                status_code=422,
                detail="Could not extract text from file. Ensure OCR prerequisites are installed.",
            )

        sections = split_into_sections(raw_text)
        schema = assemble_full_schema(raw_text, sections)
        normalized = normalize_schema(schema)

        # optional confidence map
        confidence_map = {}
        if include_confidence:
            try:
                # confidence_map = confidence_scores(normalized, raw_text) or {}
                confidence_bundle = confidence_scores(normalized, raw_text)
                confidence_map = confidence_bundle.get("raw_scores", {})
                resume_quality = confidence_bundle.get("overall_quality_score", 0.0)
            except Exception:
                # do not fail parsing due to confidence calculation issues
                confidence_map = {}

        elapsed = time.perf_counter() - start_time

        # compute resume quality score from confidence_map (if available)
        resume_quality = 0.0
        if confidence_map:
            numeric_conf = [v for v in confidence_map.values() if isinstance(v, (int, float))]
            if numeric_conf:
                resume_quality = sum(numeric_conf) / len(numeric_conf) * 100.0

        response_payload = {
            "status": "ok",
            "file": file.filename,
            "parsed": normalized,
            "parse_time": elapsed,
            "resume_quality_score": resume_quality,
        }

        if include_confidence:
            response_payload["confidence_raw"] = confidence_bundle["raw_scores"]
            response_payload["confidence_percentage"] = confidence_bundle["percentage_scores"]

        # save to DB with raw bytes if requested
        if save:
            try:
                rec_id = save_parsed_result(
                    file.filename or "unknown",
                    normalized,
                    raw_bytes=contents,
                    status="ok",
                    source="api",
                )
                response_payload["db_id"] = rec_id
            except Exception as e:
                response_payload["db_save_error"] = str(e)
        return response_payload
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

@app.post("/parse/batch")
async def parse_batch(files: List[UploadFile] = File(...), save: bool = Query(False)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    payload = []
    for f in files:
        contents = await f.read()
        payload.append((f.filename or "unknown", contents))

    results = []

    cpu = os.cpu_count() or 2
    # use one core less than total to keep system responsive
    max_workers = min(max(1, cpu - 1), len(payload))
    # enforce an upper cap to avoid memory blowups (override with MAX_WORKERS_CAP env var)
    max_workers_cap = int(os.getenv("MAX_WORKERS_CAP", "6"))
    max_workers = min(max_workers, max_workers_cap)

    # choose ThreadPool for very small batches (avoids process spawn overhead)
    _use_thread_executor = len(payload) <= 4
    executor_cls = ThreadPoolExecutor if _use_thread_executor else ProcessPoolExecutor

    try:
        with executor_cls(max_workers=max_workers) as ex:
            start_time = time.perf_counter()
            futures = [ex.submit(process_single_file, filename, data) for filename, data in payload]
            results = []
            for fut in futures:
                r = fut.result()
                # r expected to be dict containing at least keys: file, parsed, status
                if r.get("status") == "ok":
                    if save:
                        try:
                            # find raw bytes by matching filename to payload
                            raw_bytes = next((b for n, b in payload if n == r.get("file")), None)
                            rec_id = save_parsed_result(
                                r.get("file"),
                                r.get("parsed"),
                                raw_bytes=raw_bytes,
                                status="ok",
                                source="batch",
                            )
                            r["db_id"] = rec_id
                        except Exception as e:
                            r["db_save_error"] = str(e)
                results.append(r)
            elapsed = time.perf_counter() - start_time
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch processing failed: {e}")
    return {
        "batch_count": len(results),
        "results": results,
        "parse_time": elapsed
    }

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
