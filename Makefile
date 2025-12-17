.PHONY: all update-pip install-spacy download-spacy-model download-sentence-transformer

all: update-pip install-requirements install-spacy download-spacy-model download-sentence-transformer-model


update-pip:
\tpip install -U pip setuptools wheel

install-requirements:
\tpip install -r requirements.txt

install-spacy:
\tpip install -U spacy

download-spacy-model:
\tpython -m spacy download en_core_web_sm

download-sentence-transformer-model:
\tpython download_all-MiniLlM-L6-v2.py