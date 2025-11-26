@echo off
REM Upgrade pip, setuptools, wheel
python -m pip install --upgrade pip setuptools wheel

REM Install from requirements.txt
pip install -r requirements.txt

REM Install/upgrade spacy
pip install -U spacy

REM Download the spacy English model
python -m spacy download en_core_web_sm

REM Pre-download the SentenceTransformer model
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

echo.
echo Installation and setup complete.
pause
