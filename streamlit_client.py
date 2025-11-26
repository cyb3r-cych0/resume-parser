#!/usr/bin/env python3
"""
Fixes the single-file Save (calls /parse?save=true)
Allows Save on single and Save on batch (toggle)
Adds a Sidebar: Query DB panel to list recent records and view a selected record
Keeps the UI simple and offline-friendly
"""
import json
import requests
import streamlit as st
from pathlib import Path
from typing import List

st.set_page_config(page_title="Resume Extractor — Client", layout="wide")
st.title("Resume Extractor — Streamlit Client")
st.markdown("Offline demo client for the Resume Extractor API. Upload → parse → optionally save to local SQLite DB.")

# Defaults
DEFAULT_API = "http://127.0.0.1:8000/parse"
API_BASE = DEFAULT_API.rsplit("/parse", 1)[0]

# --- Sidebar: backend & DB query ---
st.sidebar.header("Backend / DB")
api_url_base = st.sidebar.text_input("API Base URL", value=API_BASE)
api_parse = api_url_base.rstrip("/") + "/parse"
api_batch = api_url_base.rstrip("/") + "/parse/batch"
api_health = api_url_base.rstrip("/") + "/health"
api_records = api_url_base.rstrip("/") + "/records"

if st.sidebar.button("Check backend health", key="check_health_btn"):
    try:
        r = requests.get(api_health, timeout=3)
        if r.ok:
            st.sidebar.success("Backend healthy")
        else:
            st.sidebar.error(f"Health: {r.status_code}")
    except Exception as e:
        st.sidebar.error(f"Health check failed: {e}")

# ---- Sidebar: robust cached record list + open record ----
st.sidebar.markdown("---")
st.sidebar.header("Query saved results (SQLite)")
records_limit = st.sidebar.number_input("List limit", min_value=1, max_value=200, value=20, key="records_limit")

# Fetch records and store in session_state when user clicks "Fetch"
if "records_list" not in st.session_state:
    st.session_state["records_list"] = []  # initialize

if st.sidebar.button("Fetch recent records", key="fetch_records_btn"):
    try:
        r = requests.get(api_records, params={"limit": records_limit}, timeout=6)
        if r.ok:
            out = r.json()
            rows = out.get("results", [])
            st.session_state["records_list"] = rows
            st.sidebar.success(f"Loaded {len(rows)} records")
        else:
            st.sidebar.error(f"List failed: {r.status_code}")
    except Exception as e:
        st.sidebar.error(f"List request failed: {e}")

# If we have records in session state, show them persistently
rows = st.session_state.get("records_list", [])
if rows:
    options = [f"{row['id']} — {row.get('filename','(no name)')} — {row.get('status','')}" for row in rows]
    selected = st.sidebar.selectbox("Select a record to open", options, index=0, key="record_selectbox")
    # parse id safely
    try:
        sel_id = int(selected.split("—")[0].strip())
    except Exception:
        sel_id = None

    if st.sidebar.button("Open selected record", key="open_record_btn"):
        if sel_id is None:
            st.sidebar.error("Could not parse selected record id.")
        else:
            try:
                r2 = requests.get(f"{api_records}/{int(sel_id)}", timeout=6)
                if r2.ok:
                    st.sidebar.success(f"Record {sel_id} loaded")
                    # pretty print JSON in sidebar
                    try:
                        st.sidebar.json(r2.json())
                    except Exception:
                        st.sidebar.text(json.dumps(r2.json(), indent=2))
                else:
                    st.sidebar.error(f"Fetch failed: {r2.status_code} {r2.text}")
            except Exception as e:
                st.sidebar.error(f"Fetch failed: {e}")

# Provide a small "clear" control
if st.sidebar.button("Clear cached records", key="clear_records_btn"):
    st.session_state["records_list"] = []
    st.sidebar.info("Cached records cleared.")



st.sidebar.markdown("---")
st.sidebar.caption("Tip: Ensure backend (uvicorn) is running and the API URL is correct.")

# --- Main UI: single upload ---
st.header("Single resume")
col1, col2 = st.columns([2, 1])
with col1:
    uploaded = st.file_uploader("Upload a resume (pdf/docx/txt/image)", type=["pdf","docx","txt","png","jpg","jpeg","tiff"])
with col2:
    include_conf = st.checkbox("Include confidence", value=False)
    save_single_toggle = st.checkbox("Save parsed result to DB (single)", value=False)
    parse_btn = st.button("Parse single file")

if parse_btn:
    if not uploaded:
        st.warning("Please upload a file first.")
    else:
        st.info(f"Uploading {uploaded.name} ...")
        try:
            files = {"file": (uploaded.name, uploaded.getvalue())}
            params = {"include_confidence": str(include_conf).lower()}
            # decide whether to ask back-end to save
            if save_single_toggle:
                params["save"] = "true"
            resp = requests.post(api_parse, files=files, params=params, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                st.success("Parsed result")
                st.json(data)
                st.download_button("Download JSON", data=json.dumps(data, indent=2), file_name=f"{Path(uploaded.name).stem}.json", mime="application/json")
            else:
                st.error(f"API error {resp.status_code}: {resp.text}")
        except Exception as e:
            st.error(f"Request failed: {e}")

st.markdown("---")

# --- Bulk (multiple) upload with both sequential and parallel options ---
st.header("Bulk upload")
bulk_files = st.file_uploader("Select multiple resumes", accept_multiple_files=True, type=["pdf","docx","txt","png","jpg","jpeg","tiff"])
col_a, col_b, col_c = st.columns([1,1,1])
with col_a:
    save_bulk_toggle = st.checkbox("Save each parsed result to DB (batch)", value=False)
with col_b:
    parallel_btn = st.button("Start PARALLEL batch upload")
with col_c:
    seq_btn = st.button("Start SEQUENTIAL batch upload")

def do_batch_request(files_list, parallel=True, save_each=False):
    if not files_list:
        st.warning("No files selected.")
        return
    try:
        # prepare files param structure for requests
        if parallel:
            endpoint = api_batch
            files_payload = []
            for f in files_list:
                files_payload.append(("files", (f.name, f.getvalue())))
            params = {}
            if save_each:
                params["save"] = "true"
            r = requests.post(endpoint, files=files_payload, params=params, timeout=600)
            if r.status_code == 200:
                res = r.json()
                st.success(f"Batch processed: {res.get('batch_count')} files")
                st.json(res)
                st.download_button("Download batch results", data=json.dumps(res, indent=2), file_name="batch_results.json", mime="application/json")
            else:
                st.error(f"Batch API error {r.status_code}: {r.text}")
        else:
            # sequential: call parse endpoint for each file
            results = []
            total = len(files_list)
            progress = st.progress(0)
            for i, f in enumerate(files_list):
                files_param = {"file": (f.name, f.getvalue())}
                params = {}
                if save_each:
                    params["save"] = "true"
                params["include_confidence"] = str(include_conf).lower()
                r = requests.post(api_parse, files=files_param, params=params, timeout=180)
                if r.status_code == 200:
                    results.append({"file": f.name, "status": "ok", "result": r.json()})
                else:
                    results.append({"file": f.name, "status": f"error {r.status_code}", "result": r.text})
                progress.progress((i+1)/total)
            st.success("Sequential batch finished")
            st.write("Summary:")
            for rr in results[:10]:
                st.write(rr["file"], "-", rr["status"])
            st.download_button("Download sequential results", data=json.dumps(results, indent=2), file_name="seq_batch_results.json", mime="application/json")
    except Exception as e:
        st.error(f"Batch request failed: {e}")

if parallel_btn:
    do_batch_request(bulk_files, parallel=True, save_each=save_bulk_toggle)

if seq_btn:
    do_batch_request(bulk_files, parallel=False, save_each=save_bulk_toggle)

st.markdown("---")
st.caption("Bulk upload: Parallel uses the server's /parse/batch endpoint (multi-process). Sequential calls the single /parse endpoint repeatedly.")

# --- Footer: quick debug info ---
st.write("## Debug")
st.write(f"API parse endpoint: {api_parse}")
st.write(f"API batch endpoint: {api_batch}")
st.write(f"Records endpoint: {api_records}")
