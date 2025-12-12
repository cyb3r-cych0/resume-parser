# Resume Parser

A comprehensive, fully offline end-to-end resume parsing and extraction system.

Supports multiple resume formats: PDF, DOCX, TXT, as well as scanned images like JPG, PNG, and TIFF.

All OCR and NLP operations run locally with zero cloud dependencies.

## Features

- **Fully Offline Extraction**:
  - Works on PDFs, DOCX, TXT, JPG, PNG, TIFF files.
  - Local OCR and natural language processing, no cloud.
- **Advanced OCR Support**:
  - Automatic fallback to OCR when native text extraction fails.
  - Uses Tesseract OCR and Poppler for PDF image processing.
  - Includes pre-processing pipeline: grayscale, noise reduction, auto-contrast, binarization.
- **Format-Aware Text Extraction**:
  - Native PDF parsing with pdfplumber.
  - DOCX parsing using python-docx.
  - OCR-based text extraction from images (pytesseract).
  - Auto type detection via filename or python-magic.
- **Intelligent Section Segmentation**:
  - Logical text splitting via heading detection and fuzzy matching (RapidFuzz).
  - Supports sections like Education, Experience, Skills, Certifications, Publications, Achievements, Extracurricular Activities, Test Scores, Summary/Objective, and fallback Other.
- **Comprehensive Academic Data Extraction**:
  - Extracts High School, Undergraduate, Postgraduate details.
  - Fields like institution, address heuristic, GPA or percentage with scale, board/university, graduation year, degree, and major.
- **Detailed Work Experience Extraction**:
  - Splits experience entries and extracts job title, organization, date ranges, and experience details.
- **Certifications & Achievements Extraction**:
  - Detects certificates, awards, and short achievements from text.
- **Research Publications Extraction**:
  - Uses heuristics to detect academic publications (quotes, journal keywords).
- **Standardized Test Score Extraction**:
  - Captures SAT, ACT, GRE, GMAT, TOEFL, IELTS scores.
- **Advanced Normalization Layer**:
  - Cleans whitespace, normalizes GPA scales (auto-inferred), percentages, graduation years, and lists (activities, achievements, certifications).
- **Confidence Scoring (Optional)**:
  - Provides confidence values (0–1) for various extracted fields such as name, email, phone, education years, GPA.
- **Streamlit Client**:
  - Full offline UI for:
    - Single resume upload
    - Bulk multi-file upload
    - Parsed JSON display and download
    - Backend health check
    - Editable API URL
- **Bulk Upload Support**:
  - Sequential multiple file uploads with per-resume results and aggregated JSON download.
  - Now supports **Parallel batch** processing with multicore OCR for faster throughput.
  - Supports both **Sequential batch** (existing) and **Parallel batch** (new) modes.
- **Multi-core OCR Processing**:
  - Enables parallelized OCR to leverage multiple CPU cores for improved performance.
- **Modular Architecture**:
  - Clean directory structure with dedicated helper modules for text extraction, section segmentation, field extraction, normalization.
  - Organized main files: api.py, streamlit_client.py.
- **End-to-End JSON Standardization**:

- **API Backend**: FastAPI server with CORS enabled for cross-origin requests.
- **Health Check**: Endpoint to verify backend status.

## Installation

1. **Clone the repository**:
   
   ```bash
   git clone https://github.com/cyb3r-cych0/resume-parser.git
   cd resume-parser
   ```

2. **Install dependencies**:

    Python 3.13.x is recommended (compatible with Streamlit).

    Create a virtual environment:

    ```bash
    python -m venv .env
    ```

### On Windows

- To install dependencies on Windows, run the batch file `install_requirements.bat` in Windows Terminal:

  ```bash
  cd c:\path\to\resume-parser
  install_requirements.bat
  ```

### On Unix/Linux/macOS (Git Bash, WSL, MinGW, or native Unix shells)

- To install dependencies on Unix-like systems, use `make`:

  ```bash
  cd /path/to/resume-parser
  make
  ```

1. **Additional spaCy model download (if not included in makefile or batch script):**

   ```bash
   pip install -U pip setuptools wheel
   pip install -U spacy
   python -m spacy download en_core_web_sm
   python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
   ```
   OR
2. Alternatively, you can choose a spaCy model that works best with your needs(speed &/ accuracy)
  ```bash
    python -m spacy download en_core_web_trf #  accuracy (slower)
    python -m spacy download en_core_web_lg #  speed (less accurate)
   ```
## Usage

**Steps**

1. Initialize DB
2. Run Backend (FastAPI)
3. Run Frontend (Streamlit)

**Note:** Run Backend `api.py` and Client `main.py` in Separate Terminals

### Initialize DB

```bash
  python initialize_db.py
```

### Running the Backend (FastAPI) [Terminal A]

Start the FastAPI server:

```bash
python api.py
```

Or with uvicorn directly:

```bash
uvicorn api:app --reload
```

The backend will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000).

Test backend health:

```bash
curl http://127.0.0.1:8000/health
```

Should return: `{"status":"ok"}`

### Quick Parse Test - Single File:

```bash
curl -F "file=@/path/to/sample.pdf" http://127.0.0.1:8000/parse
```

### Quick Parse Test - With Confidence Scores:

```bash
curl -F "file=@/path/to/sample.pdf" "http://127.0.0.1:8000/parse?include_confidence=true"
```

### Running the Client (Streamlit) [Terminal B]

Start the Streamlit app:

```bash
streamlit run Dashboard.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

Upload a resume file via the interface and view or download parsed results.

## Tips

- Ensure the backend is running before using the client.
- Health check (via Streamlit sidebar) should confirm backend connectivity.
- Adjust API URLs in `streamlit_client.py` or `.streamlit/secrets.toml` as needed.
- Supports single file upload or bulk sequential uploads.

## API Endpoints
- Homepage (main) - http://localhost:8501/
- Parse Single File - http://localhost:8501/Parse_Single
- Pass Batch/Bulk Files - http://localhost:8501/Parse_Batch
- View Database - http://localhost:8501/Database_Records

### POST /parse

Upload and parse resume files (PDF, DOCX, TXT).

- Request: Multipart form-data with `file` field.
- Response: JSON with extracted resume data.

### GET /health

Backend health check.

- Response: `{"status": "ok"}`

## Contributing

Contributions welcome! Please fork and submit pull requests.

## License

MIT License. See the [LICENSE](LICENSE) file.

## Author

cyb3r-cych0  
Email: minigates21@gmail.com
