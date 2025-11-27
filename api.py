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
from concurrent.futures import ProcessPoolExecutor
import io

# pipeline helpers (local modules)
from helpers.text_extraction import extract_text_from_bytes
from helpers.section_segmentation import split_into_sections
from helpers.field_extraction import assemble_full_schema
from helpers.normalization import normalize_schema, confidence_scores
from helpers.batch_worker import process_single_file
from helpers.db import init_db, save_parsed_result, get_record, get_raw_bytes, list_records

app = FastAPI(title="Parse API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# initialize DB
init_db()

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/parse")
async def parse_resume(file: UploadFile = File(...),
                       include_confidence: bool = False,
                       save: bool = Query(False)):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    try:
        contents = await file.read()
        if not contents or len(contents) < 4:
            raise HTTPException(status_code=422, detail="Empty or invalid file")

        raw_text = extract_text_from_bytes(file.filename or "", contents, use_magic=False)
        if not raw_text or len(raw_text.strip()) < 3:
            raise HTTPException(status_code=422, detail="Could not extract text from file. Ensure OCR prerequisites are installed.")

        sections = split_into_sections(raw_text)
        schema = assemble_full_schema(raw_text, sections)
        normalized = normalize_schema(schema)

        result = {"parsed": normalized}
        if include_confidence:
            result["confidence"] = confidence_scores(normalized, raw_text)

        # save to DB with raw bytes if requested
        if save:
            try:
                rec_id = save_parsed_result(file.filename or "unknown", normalized, raw_bytes=contents, status="ok", source="api")
                result["db_id"] = rec_id
            except Exception as e:
                result["db_save_error"] = str(e)

        return JSONResponse(content=result)

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
    max_workers = min(4, len(payload))
    try:
        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(process_single_file, filename, data) for filename, data in payload]
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch processing failed: {e}")

    return {"batch_count": len(results), "results": results}


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
            result["confidence"] = confidence_scores(normalized, raw_text)

        if save:
            new_id = save_parsed_result(rec_meta.get("filename"), normalized, raw_bytes=raw, status="ok", source=f"reparse_from_{record_id}")
            result["db_id"] = new_id

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reparse failed: {e}")