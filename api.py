#!/usr/bin/env python3
"""
- Reads uploaded file bytes
- Extracts text (native PDF / DOCX / OCR fallback)
- Splits text into sections (Education/Experience/etc.)
- Extracts fields into your full schema
- Normalizes values (years, GPA) and returns optional confidence scores
- Returns final JSON
"""

import traceback
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from concurrent.futures import ProcessPoolExecutor

# helper imports (local modules)
from helpers.text_extraction import extract_text_from_bytes
from helpers.section_segmentation import split_into_sections
from helpers.field_extraction import assemble_full_schema
from helpers.normalization import normalize_schema, confidence_scores
from helpers.batch_worker import process_single_file

app = FastAPI(title="Resume Extractor - Offline (Integrated)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/parse")
async def parse_resume(file: UploadFile = File(...), include_confidence: bool = False):
    """
    Full offline parsing pipeline:
      1) extract text (pdf/docx/image) with OCR fallback
      2) split into sections
      3) extract fields into schema
      4) normalize values and optionally return confidence scores
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")

    try:
        contents = await file.read()
        if not contents or len(contents) < 4:
            raise HTTPException(status_code=422, detail="Empty or invalid file")

        # 1) text extraction (auto-detect by filename)
        raw_text = extract_text_from_bytes(file.filename or "", contents, use_magic=False)

        if not raw_text or len(raw_text.strip()) < 3:
            # allow OCR heavy fallback inside extractor; if still empty, return 422
            raise HTTPException(status_code=422, detail="Could not extract text from file. Ensure OCR prerequisites (tesseract/poppler) are installed.")

        # 2) section segmentation
        sections = split_into_sections(raw_text)

        # 3) field extraction into schema
        schema = assemble_full_schema(raw_text, sections)

        # 4) normalization
        normalized = normalize_schema(schema)

        # optional confidence scoring
        result = {"parsed": normalized}
        if include_confidence:
            result["confidence"] = confidence_scores(normalized, raw_text)

        return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
    
    
@app.post("/parse/batch")
async def parse_batch(files: list[UploadFile] = File(...)):
    """
    Parallel batch processing endpoint.
    Uses ProcessPoolExecutor to process multiple resumes in parallel.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # read all files into memory first
    payload = []
    for f in files:
        contents = await f.read()
        payload.append((f.filename or "unknown", contents))

    results = []
    # adjust workers to your CPU (OCR-heavy → keep <= #cores)
    max_workers = min(4, len(payload))

    try:
        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            futures = [
                ex.submit(process_single_file, filename, data)
                for filename, data in payload
            ]
            for fut in futures:
                results.append(fut.result())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch processing failed: {e}")

    return {"batch_count": len(results), "results": results}
