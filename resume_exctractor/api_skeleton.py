#!/usr/bin/env python3
import io
import re
import traceback
from typing import List, Dict, Any
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# NOTE: heavy imports (pytesseract, pdfplumber, pdf2image, spacy, etc.)
# will be added into helper modules

app = FastAPI(title="Resume Extractor - Offline (Skeleton)")

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
async def parse_resume(file: UploadFile = File(...)):
    """
    High-level endpoint.
    Steps to be implemented in next files:
      1. Save/read bytes
      2. Detect type (pdf/docx/image)
      3. Extract text (pdfplumber / docx / OCR)
      4. Preprocess + section-segmentation
      5. Field extraction & normalization
      6. Return JSON matching schema
    For now this skeleton returns a minimal response so you can test the server.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")

    try:
        contents = await file.read()
        # quick sanity: size check
        if not contents or len(contents) < 4:
            raise HTTPException(status_code=422, detail="Empty or invalid file")

        # TODO: replace the block below with real pipeline call (helpers.extract_text_and_parse)
        sample_output = {
            "name": "",
            "email": "",
            "phoneNumber": "",
            "highSchoolName": "",
            "highSchoolAddress": "",
            "highSchoolGpaOrPercentage": "",
            "highSchoolGpaScale": "",
            "highSchoolBoard": "",
            "highSchoolGraduationYear": "",
            "ugCollegeName": "",
            "ugCollegeAddress": "",
            "ugCollegeGpaOrPercentage": "",
            "ugCollegeGpaScale": "",
            "ugUniversity": "",
            "ugGraduationYear": "",
            "ugDegree": "",
            "ugMajor": "",
            "pgCollegeName": "",
            "pgCollegeAddress": "",
            "pgCollegeGpaOrPercentage": "",
            "pgCollegeGpaScale": "",
            "pgUniversity": "",
            "pgGraduationYear": "",
            "pgDegree": "",
            "pgMajor": "",
            "certifications": [],
            "extraCurricularActivities": [],
            "workExperience": [],
            "researchPublications": [],
            "testScores": {"sat": "", "act": "", "gre": "", "gmat": "", "toefl": "", "ielts": ""},
            "achievements": []
        }

        return JSONResponse(content=sample_output)

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
