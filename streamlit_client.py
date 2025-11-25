# streamlit_client.py
import io
import json
import time
from pathlib import Path
import requests
import streamlit as st

# Configuration
DEFAULT_API = "http://127.0.0.1:8000/parse"
st.set_page_config(page_title="Resume Extractor — Client", layout="wide")

st.title("Resume Extractor — Streamlit Client")
st.markdown("Uploads resumes to local FastAPI (`/parse`) and shows structured JSON. Fully offline.")

api_url = st.text_input("API URL", value=DEFAULT_API)
include_conf = st.checkbox("Include confidence scores", value=False)

st.sidebar.header("Quick actions")
if st.sidebar.button("Check backend health"):
    try:
        r = requests.get(api_url.replace("/parse", "/health"), timeout=4)
        if r.ok:
            st.sidebar.success("Backend healthy")
        else:
            st.sidebar.error(f"Health check returned {r.status_code}")
    except Exception as e:
        st.sidebar.error(f"Could not contact backend: {e}")

st.header("Single file upload")
uploaded = st.file_uploader("Upload resume (pdf/docx/txt/image)", type=["pdf","docx","txt","png","jpg","jpeg","tiff"])
col1, col2 = st.columns([1,1])

with col1:
    if uploaded is not None:
        st.info(f"File: {uploaded.name} — {uploaded.size/1024:.1f} KB")
        if st.button("Send to API"):
            with st.spinner("Uploading and parsing..."):
                try:
                    files = {"file": (uploaded.name, uploaded.getvalue())}
                    params = {"include_confidence": str(include_conf).lower()}
                    resp = requests.post(api_url, files=files, params=params, timeout=120)
                    if resp.status_code == 200:
                        data = resp.json()
                        st.success("Parsed successfully")
                        st.json(data)
                        st.download_button("Download JSON", data=json.dumps(data, indent=2), file_name=f"{Path(uploaded.name).stem}.json", mime="application/json")
                    else:
                        st.error(f"API error {resp.status_code}: {resp.text}")
                except Exception as e:
                    st.error(f"Request failed: {e}")

with col2:
    st.subheader("Tips")
    st.markdown("""
    - Ensure FastAPI is running at the `API URL` above.
    - If OCR fails, install Tesseract & Poppler (system packages).
    - Use the bulk uploader below for multiple files.
    """)

st.markdown("---")
st.header("Bulk upload (multiple files) — sequential")
bulk = st.file_uploader("Select multiple resumes", accept_multiple_files=True, type=["pdf","docx","txt","png","jpg","jpeg","tiff"])
if bulk:
    if st.button("Start bulk upload"):
        results = []
        progress = st.progress(0)
        total = len(bulk)
        for i, f in enumerate(bulk):
            try:
                files = {"file": (f.name, f.getvalue())}
                params = {"include_confidence": str(include_conf).lower()}
                r = requests.post(api_url, files=files, params=params, timeout=180)
                if r.status_code == 200:
                    j = r.json()
                    results.append({"file": f.name, "status": "ok", "result": j})
                else:
                    results.append({"file": f.name, "status": f"error {r.status_code}", "result": r.text})
            except Exception as e:
                results.append({"file": f.name, "status": "exception", "result": str(e)})
            progress.progress((i+1)/total)
        st.success("Bulk upload finished")
        # show summary table and let download aggregated CSV/JSON
        st.write("Results summary (first 5 shown):")
        for r in results[:5]:
            st.write(r["file"], "-", r["status"])
        st.download_button("Download aggregated JSON", data=json.dumps(results, indent=2), file_name="bulk_results.json", mime="application/json")
