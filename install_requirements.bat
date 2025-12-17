@echo off
REM 1. Standard updates
python -m pip install --upgrade pip setuptools wheel

REM 2. Dependencies
pip install -r requirements.txt
pip install -U spacy

REM 3. SpaCy Model
python -m spacy download en_core_web_sm

REM 4. SentenceTransformer pre-download script
python download_all-MiniLM-L6-v2.py

echo.
echo Installation and Setup complete. All models saved to local directories.
pause
