# Parsely — Intelligent Resume Parser & Quality Scoring System

Parsely is a modular, NLP-powered resume parsing system designed to extract 
structured candidate information from diverse resume formats (PDF, DOCX, 
scanned documents), evaluate extraction quality, and prepare clean data for 
downstream HR, ATS, or analytics pipelines.
This project follows a hybrid NLP architecture (rule-based + statistical NLP) 
to ensure accuracy, transparency, speed, and control, making it suitable for 
real-world production use.

## ✨ Key Features

### 1. Multi-Format Resume Ingestion
- **Supports:**
  - PDF (text & scanned)
  - DOCX
  - Image-based resumes (via OCR)
- Automatic fallback handling when OCR or text extraction partially fails

### 2. Intelligent Section Segmentation
- **Detects and normalizes resume sections such as:**
  - Header / Contact
  - Education
  - Work Experience
  - Skills
  - Certifications
  - Achievements
- **Uses:**
  - Heuristic rules
  - Canonical section mapping
  - Works even when resumes do not follow standard headings

### 3. Semantic Field Extraction

- **Accurately extracts:**
  - Personal Information
  - Name (validated using heuristics + NER)
  - Email
  - Phone number
  - Education
  - UG / PG degree separation
  - Institution names
  - Graduation years
- **Work Experience**
  - Organization names
  - Job titles
  - Start & end years
  - Bullet-point responsibilities
- **Certifications & Achievements**

### 4. Advanced Work Experience Parsing

- **Groups experience blocks using year markers**
- **Extracts:**
  - Clean organization names
  - Job titles using title dictionaries
  - Action-based bullet points (verb-driven filtering)
  - De-duplicates overlapping experience entries

### 5. Skills Extraction & Categorization

- **Extracts technical skills using noise-resistant logic**
- **Categorizes skills into:**
  - Languages
  - Frameworks
  - Databases
  - Cloud
  - Tools
  - Infrastructure
  - Testing

### 6. Resume Quality & Confidence Scoring

- **Each parsed resume is evaluated with:**
  - Per-field confidence scores
    - Name
    - Email
    - Education
    - Experience
    - Certifications
  - Overall Resume Quality Score (0–100)
 - This allows:
   - Automated quality filtering
   - Downstream validation
   - Confidence-based storage decisions

### 7. Automatic High-Quality Resume Persistence

- **Resumes scoring above a configurable threshold (e.g., 80%) can be:**
  - Automatically saved to the database
- **Lower-quality resumes can be:**
  - Reviewed
  - Reprocessed
  - Rejected
- Designed for high-volume batch pipelines

## 8. Batch & Single Resume Processing

- **Single Resume API**
  - Real-time parsing
- **Batch Processing**
  - Parallel execution
  - Thread / process pool optimization
- **Cache-aware hashing prevents re-processing duplicates**

### 9. Clean, Normalized Output Schema

- **Final output is:**
  - Fully normalized
  - JSON-serializable
  - Ready for:
    - ATS ingestion
    - Analytics
    - ML pipelines
    - Databases

### 10. Interactive Dashboard

- **View parsed resumes**
 - **Compare:**
   - Saved vs rejected resumes
- **Inspect:**
   - Extracted fields
   - Quality scores
- **Designed for recruiters, analysts, and evaluators**

## 🏗️ System Architecture (High-Level)
  ```css
  Resume File
      ↓
  Text Extraction (OCR / PDF / DOCX)
      ↓
  Section Segmentation
      ↓
  Section Classification
      ↓
  Semantic Field Extraction
      ↓
  Normalization & Cleaning
      ↓
  Confidence & Quality Scoring
      ↓
  Database / API / Dashboard
  ```

## 📁 Project Structure (Key Files)
```
  File	                  ----- Purpose
  text_extraction.py      ----- OCR & raw text extraction
  section_segmentation.py ----- Resume section splitting
  section_classifier.py	  ----- Canonical section mapping
  semantic_extraction.p   ----- Core schema assembly
  field_extraction.py	  ----- Education & experience extraction
  ner_utils.py	          ----- spaCy-based NER augmentation
  normalization.py	      ----- Data cleaning & normalization
  batch_worker.py	      ----- Batch & single resume processing
  db.py	                  ----- Database persistence
  api.py	              ----- REST API
  Dashboard.py	          ----- UI & visualization
```

## 🧠 Design Philosophy
- **Why Hybrid NLP (Not LLM-Only)?**
  - Deterministic behavior
  - Explainable decisions
  - Lower latency
  - No hallucinations
  - Cost-efficient at scale
  - Easier compliance & auditing
- LLMs can be integrated later as an enhancement, not a dependency.

## 🛠️ Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/cyb3r-cych0/resume-parser.git
   cd resume-parser
   ```

2. **Install dependencies**:
    - Python 3.13.x is recommended (compatible with Streamlit).
    - Create a virtual environment:
    ```bash
    python -m venv .env
    ```

   - #### On Windows
     - To install dependencies on Windows, run the batch file `install_requirements.bat` in Windows Terminal:
       ```bash
       cd c:\path\to\resume-parser
       install_requirements.bat
       ```

   - #### On Unix/Linux/macOS (Git Bash, WSL, MinGW, or native Unix shells)
     - To install dependencies on Unix-like systems, use `make`:
       ```bash
        cd /path/to/resume-parser
        make
       ```

3. Additional spaCy model download (if not included in makefile or batch script):
   ```bash
   pip install -U pip setuptools wheel
   pip install -U spacy
   python -m spacy download en_core_web_sm 
   python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
   ```
   **OR**
4. Alternatively, you can choose a spaCy model that works best with your needs(speed &/ accuracy)
  ```bash
    python -m spacy download en_core_web_trf #  slower 
    python -m spacy download en_core_web_lg #  very large
   ```

## 🚀 How To Run

**Steps**
  - Run Backend (FastAPI)
  - Run Frontend (Streamlit)

**Note:** Run Backend `api.py` and Client `Dashboard.py` in Separate Terminals

### 1. Running the Backend (FastAPI) [Terminal A]
- **Start the FastAPI server:**
  ```bash
  python api.py
  ```

- **Or with uvicorn directly:**
  ```bash
  uvicorn api:app --reload
  ```
   - The backend will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000).

- **Test backend health:**
  ```bash
  curl http://127.0.0.1:8000/health
  ```
   - Should return: `{"status":"ok"}`

- ####  Quick Parse Test - Single File:
  ```bash
  curl -F "file=@/path/to/sample.pdf" http://127.0.0.1:8000/parse
  ```

- #### Quick Parse Test - With Confidence Scores:
  ```bash
  curl -F "file=@/path/to/sample.pdf" "http://127.0.0.1:8000/parse?include_confidence=true"
  ```

### 2. Running the Client (Streamlit) [Terminal B]
- **Start the Streamlit app:**
  ```bash
  streamlit run Dashboard.py
  ```
   - Open [http://localhost:8501](http://localhost:8501) in your browser.

### 3. Usage
**To Parse Single File:**
  - Choose `Parse Single` on the Side Panel or `Quick Actions`
  - Select `NLP Model` on the Side Bar Panel
  - Upload a resume file via the interface
  - Check `Include Confidence` and or `Save to DB` checkboxes
  - Click `Parse` and wait a few seconds
  - View parsed results displayed
    - Quality Score Gauge and Confidence Score Bar Chart should be displayed
    - Scroll down to analyze the `JSON` file
  - Save or download parsed results.

**To Parse Batch Files**
- Choose `Parse Batch` on the Side Panel or `Quick Actions`
  - Select `NLP Model` on the Side Bar Panel
  - Upload a resume file via the interface
  - Check `Include Confidence` and or `Save to DB` checkboxes
  - Click `Parse Paralle` or `Parse Sequentially` and wait a few seconds
  - View parsed results by clicking the `show` button at the end of each file displayed
    - Quality Score Gauge and Confidence Score Bar Chart per file should be displayed
    - Scroll down to analyze the `JSON` file
    - Repeat for all batch files parsed
  - Save or download parsed results.

**Database Records**
- Click `Database Records` on the Side Panel or `Quick Actions`
- Click on `Fetch Records` button to fetch saved records
- Interact with `Export Visible CSV` or `Export Visible JSON` to export table data
- Enter `record_id` on the textbox below to open displayed records
- Choose `Download File`, `Reparse File` or `Delete File`

### 4.  📊 Example Output
    json
      {
        "name": "John Doe",
        "email": "john.doe@email.com",
        "workExperience": [...],
        "education": {...},
        "resume_quality_score": 78.6,
        "confidence_percentage": {...}
    }

## Tips

- Ensure the backend is running before using the client.
- Health check (via Streamlit sidebar) should confirm backend connectivity.
- Adjust API URLs in `Dashboard.py` or `.streamlit/secrets.toml` as needed.
- Supports single file upload or bulk sequential uploads.
- Supported File Type: `(PDF, DOCX, TXT, JPG, PNG, JPEG)`
- Clear cache before reparsing file to avoid display of stored cached data


## API Endpoints
- Dashboard - http://localhost:8501/
- Parse Single File - http://localhost:8501/Parse_Single
- Parse Batch Files - http://localhost:8501/Parse_Batch
- Database - http://localhost:8501/Database_Records

## 🏁 Status

✅ Core objectives completed 

⏸️ Further improvements planned

## 🔮 Future Scope

Optional LLM refinement layer

Resume–job matching

Skill gap analysis

Multilingual support

## Contributing

Contributions welcome! Please fork and submit pull requests.

## License

MIT License. See the [LICENSE](LICENSE) file.

## Author

cyb3r-cych0  
Email: minigates21@gmail.com
