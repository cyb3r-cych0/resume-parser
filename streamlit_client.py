import json
import requests
import streamlit as st

API_URL = st.secrets.get("API_URL", "http://127.0.0.1:8000/parse")

st.set_page_config(page_title="Resume Parser — Streamlit Client", layout="wide")

st.title("Resume Parser — Streamlit Client")
st.markdown("""
Upload a resume (PDF, DOCX, TXT). This client will send it to the local FastAPI backend and show the parsed JSON.
- Backend: `http://127.0.0.1:8000/parse`
""")

uploaded = st.file_uploader("Upload resume", type=["pdf", "docx", "txt"], key="uploader")
col1, col2 = st.columns([1, 1])

with col1:
    if uploaded is not None:
        st.info(f"File: {uploaded.name} — {uploaded.size/1024:.1f} KB")
        if st.button("Send to API"):
            with st.spinner("Uploading and parsing..."):
                files = {"file": (uploaded.name, uploaded.getvalue())}
                try:
                    resp = requests.post(API_URL, files=files, timeout=60)
                    if resp.status_code == 200:
                        parsed = resp.json()
                        st.success("Parsed successfully")
                        st.json(parsed)
                        st.download_button("Download parsed JSON", data=json.dumps(parsed, indent=2), file_name="parsed_resume.json", mime="application/json")
                    else:
                        st.error(f"API returned error: {resp.status_code} — {resp.text}")
                except requests.exceptions.RequestException as e:
                    st.error(f"Request failed: {e}")

with col2:
    st.subheader("Tips & quick checks")
    st.markdown("""
    - Ensure the FastAPI server is running at `http://127.0.0.1:8000`.
    - If using a custom host/port, set `st.secrets['API_URL']` or change `API_URL` above.
    - spaCy model must be downloaded via `python -m spacy download en_core_web_sm`.
    """)
    if st.button("Check backend health"):
        try:
            r = requests.get(API_URL.replace("/parse", "/health"), timeout=5)
            if r.ok:
                st.success("Backend healthy")
            else:
                st.error("Backend responded but returned error")
        except Exception as e:
            st.error(f"Could not contact backend: {e}")
