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
   
  `git clone [<https://github.com/cyb3r-cych0/resume-parser.git>]`

   `cd resume-parser`

2. **Install dependencies**:

   `pip install -r requirements.txt`
   

3. **Download spaCy model**:

   `python -m spacy download en_core_web_sm`
  

   If the above fails, download and install manually from the spaCy models page.

## Usage

### Running the Backend (FastAPI)

Start the FastAPI server:

`python api.py`

Or using uvicorn directly:

`uvicorn api:app --host 127.0.0.1 --port 8000 --reload`

The backend will be available at `http://127.0.0.1:8000`.

### Running the Client (Streamlit)

Start the Streamlit app:

`streamlit run streamlit_client.py`

The client will be available at `http://localhost:8501`.

Upload a resume file via the web interface, and the parsed data will be displayed as JSON. You can also download the parsed results.

### Tips

- Ensure the backend is running before using the client.
- For custom API URLs, update `API_URL` in `streamlit_client.py` or set it in `.streamlit/secrets.toml`.
- Use the health check button in the client to verify backend connectivity.

## API Endpoints

### POST /parse
Uploads and parses a resume file.

- **Request**: Multipart form-data with file field (PDF, DOCX, or TXT).
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

