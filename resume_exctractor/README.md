## Installation

1. **Clone the repository**:
   
  `git clone https://github.com/cyb3r-cych0/resume-parser.git`

   `cd resume-parser`

   create virtual environment

2. **Install Requirements**

    python --version 3.13 `compatible with streamlit`

3. **Install dependencies**:

    python -m venv .env
    .env\Scripts\activate.ps1

   `pip install -r requirements.txt`   

4. **Download spaCy model**:

    pip install -U pip setuptools wheel
    pip install -U spacy
    python -m spacy download en_core_web_sm - efficiency
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" - `Both models are used offline after this download.`
    python -m spacy download en_core_web_trf - accuracy

    pip install spacy[lookups,transformers]

5. **How To Run**

    In the Terminal run:

    `uvicorn api:app --reload`

    ### Quick Run Tests

    Open another terminal in the project root directory and activate virtual environment

    #### Test Health Endpoint:

    `curl http://127.0.0.1:8000/health`

     should return: `{"status":"ok"}`

    #### Text Extraction - PDF/DOCX/OCR:
    
    `python helpers/text_extraction.py /full/path/to/sample_resume.pdf`

    should return extracted text (first ~10k chars). For images, point to a JPG/PNG.

    #### Quick parse test (Single-File PArse):

    `curl -F "file=@/path/to/some/sample.pdf" http://127.0.0.1:8000/parse`

    should return JSON response `{"Parsed": {data}}` 

    # With Confidence Scores:
    `curl -F "file=@/full/path/to/sample.pdf" "http://127.0.0.1:8000/parse?include_confidence=true"`

    should return JSON response `{"Parsed": {key:data}, "confidence":{key:confidence}}` 

6. **Pipeline**
    `OCR → text extraction → section segmentation → field extraction → normalization → final JSON`