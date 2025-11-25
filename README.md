# Resume Parser

A web application for parsing and extracting key information from resumes using Natural Language Processing (NLP). The project consists of a FastAPI backend for processing uploaded resume files (PDF, DOCX, TXT) and a Streamlit client for a user-friendly web interface.

## Features

- **Resume Parsing**: Extracts structured data from resumes including:
  - Name
  - Email addresses
  - Phone numbers
  - URLs
  - GitHub and LinkedIn handles
  - Organizations/Companies
  - Skills (from a predefined list)
  - Top frequent terms
- **File Support**: Supports PDF, DOCX, and TXT file formats.
- **NLP-Powered**: Uses spaCy with the `en_core_web_sm` model for entity recognition.
- **Web Interface**: Streamlit-based client for easy file upload and result viewing.
- **API Backend**: FastAPI server with CORS enabled for cross-origin requests.
- **Health Check**: Endpoint to verify backend status.

## Installation

1. **Clone the repository**:
   
  `git clone https://github.com/cyb3r-cych0/resume-parser.git`

   `cd resume-parser`

2. **Install dependencies**:

    Download Python 3.13.x - Compatible with Streamlit

    Create virtual environment 

    `(3.13.7) python -m venv .env`

    `pip install -r requirements.txt`
   

3. **Download spaCy model**:

    `pip install -U pip setuptools wheel`

    `pip install -U spacy`

    `python -m spacy download en_core_web_sm` 

    `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"`
  

   If the above fails, download and install manually from the spaCy models page.

## Usage [ Two Terminals ]

### Running the Backend (FastAPI) [ Terminal A ]

Start the FastAPI server:

`python api.py`

Or using uvicorn directly:

`uvicorn api:app --reload`

The backend will be available at `http://127.0.0.1:8000`.

  #### Health Endpoint Test 0:

  `curl http://127.0.0.1:8000/health`

  `hould return: {"status":"ok"}`

  ### Quick Parse Test 1 -Single-File Parse:

  `curl -F "file=@/path/to/some/sample.pdf" http://127.0.0.1:8000/parse`

  should return JSON response `{"Parsed": {key:data}}` 

  ### Quick Parse Test 2 - With Confidence Scores:
  `curl -F "file=@/full/path/to/sample.pdf" "http://127.0.0.1:8000/parse?include_confidence=true"`

  should return JSON response `{"Parsed": {key:data}, "confidence":{key:confidence}}` 

### Running the Client (Streamlit) [ Terminal B ]

Start the Streamlit app:

`streamlit run streamlit_client.py`

The client will be available at `http://localhost:8501`.

Upload a resume file via the web interface, and the parsed data will be displayed as JSON. You can also download the parsed results.

### Tips

- Ensure the backend is running before using the client.
      `Health check (Streamlit sidebar) should show Backend healthy.`

- For custom API URLs, update `API_URL` in `streamlit_client.py` or set it in `.streamlit/secrets.toml`.

- Single upload -> parsed JSON should appear.

- Bulk upload -> sequential processing; results downloadable JSON.

## API Endpoints

### POST /parse
Uploads and parses a resume file.

- **Request**: Multipart form-data with file field (PDF, DOCX, TXT) or OCR.
- **Response**: JSON object containing extracted data.
  `json`
  {
    
    name: John Doe,
    emails: [john.doe@example.com],
    phones: [+1-123-456-7890],
    linkedin_handles: [johndoe],
    github_handles: [johndoe],
    urls\: [https://example.com],
    organizations\: [ABCCorp],
    skills: [python, machine learning],
    top_terms: [data, analysis, python],
    raw_text_head: First 40 lines of extracted text...
  }

### GET /health
Checks the health of the backend.

- **Response**: `{status: ok}`

## Configuration

- **Secrets**: Edit `.streamlit/secrets.toml` to configure API keys or custom settings (e.g., Google API key placeholder).
- **CORS**: The backend allows requests from `http://localhost:8501` and `http://127.0.0.1:8501\`by default. Modify in `api.py` if needed.

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request for any improvements or bug fixes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Author

Name: `cyb3r-cych0`
Email: `minigates21@gmail.com`

