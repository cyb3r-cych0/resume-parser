#!/usr/bin/env python3
import spacy
import threading
from typing import Optional

_lock = threading.Lock()
_models = {}  # name -> loaded model

# Allowed model names (only these will be accepted via API)
ALLOWED_MODELS = ("en_core_web_sm", "en_core_web_lg", "en_core_web_trf")

def get_spacy_model(name: str) -> Optional[object]:
    """
    Thread-safe lazy loader for spaCy models. Returns loaded model or raises an exception
    if the model is not installed locally.
    """
    if not name:
        name = "en_core_web_sm"
    if name not in ALLOWED_MODELS:
        raise ValueError(f"Unsupported model '{name}'. Choose one of: {', '.join(ALLOWED_MODELS)}")
    # return cached copy if present
    if name in _models:
        return _models[name]
    # load with lock to avoid races
    with _lock:
        if name in _models:
            return _models[name]
        try:
            nlp = spacy.load(name)
            _models[name] = nlp
            return nlp
        except Exception as e:
            # re-raise for caller to handle: this prevents silent downloads
            raise e
