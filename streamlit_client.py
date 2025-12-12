#!/usr/bin/env python3
"""
Fixes the single-file Save (calls /parse?save=true)
Allows Save on single and Save on batch (toggle)
Adds a Sidebar: Query DB panel to list recent records and view a selected record
Keeps the UI simple and offline-friendly
Features:
    -> Shows selected record in the main area on demand (button Open selected record (main area))
    -> Provides search/filter by filename/date (client-side filter of fetched records).
    -> Adds Re-run parsing button for a stored record (calls /records/{id}/reparse).
    -> Exports selected records (list) as CSV and JSON (CSV contains id, filename, status, created_at).
"""
import io
import csv
import json
import requests
import streamlit as st

# ------------- Circular Gauge Component -------------
def circular_gauge(score: float, label="Resume Quality Score"):
    """
    Renders an animated circular gauge (0–100).
    Uses pure HTML/CSS so it works offline in Streamlit.
    """
    pct = min(max(score, 0), 100)

    html = f"""
    <div style="display:flex; justify-content:center; margin-top:20px; margin-bottom:30px;">
        <div style="
            width: 180px; 
            height: 180px; 
            border-radius: 50%;
            background: conic-gradient(#4caf50 {pct*3.6}deg, #d9d9d9 0deg);
            display:flex; 
            align-items:center; 
            justify-content:center;
            position:relative;
            box-shadow: 0 0 12px rgba(0,0,0,0.15);
        ">
            <div style="
                width:140px;
                height:140px;
                border-radius:50%;
                background:white;
                display:flex;
                flex-direction:column;
                align-items:center;
                justify-content:center;
                text-align:center;
                font-family:sans-serif;
            ">
                <span style="font-size:32px; font-weight:700; color:#333;">{pct:.1f}%</span>
                <span style="font-size:14px; opacity:0.7;">{label}</span>
            </div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


st.set_page_config(page_title="Parsely — API", layout="wide")
st.markdown(
    "<h1 style='text-align: center; font-size: 50px; color:#4caf50;'>Parsely API</h1>",
    unsafe_allow_html=True
)

# ---------------- Config ----------------
DEFAULT_API_BASE = "http://127.0.0.1:8000"
api_base = st.sidebar.text_input("API base URL", value=DEFAULT_API_BASE, key="api_base")
api_parse = api_base.rstrip("/") + "/parse"
api_batch = api_base.rstrip("/") + "/parse/batch"
api_health = api_base.rstrip("/") + "/health"
api_records = api_base.rstrip("/") + "/records"

# ---------------- Sidebar (compact) ----------------
if st.sidebar.button("Check backend health", key="health_btn"):
    try:
        r = requests.get(api_health, timeout=3)
        if r.ok:
            st.sidebar.success("Backend healthy")
        else:
            st.sidebar.error(f"Health: {r.status_code}")
    except Exception as e:
        st.sidebar.error(f"Health check failed: {e}")

st.sidebar.markdown("---")
st.sidebar.header("Saved records (local DB)")

records_limit = st.sidebar.number_input("List limit", min_value=1, max_value=200, value=50, key="records_limit")
if "records_list" not in st.session_state:
    st.session_state["records_list"] = []

if st.sidebar.button("Fetch recent records", key="fetch_records_btn"):
    try:
        r = requests.get(api_records, params={"limit": records_limit}, timeout=6)
        if r.ok:
            st.session_state["records_list"] = r.json().get("results", [])
            st.sidebar.success(f"Loaded {len(st.session_state['records_list'])} records")
        else:
            st.sidebar.error(f"List failed: {r.status_code}")
    except Exception as e:
        st.sidebar.error(f"List request failed: {e}")

if st.sidebar.button("Clear cached records", key="clear_records_btn"):
    st.session_state["records_list"] = []
    st.sidebar.info("Cleared cached records")

with st.sidebar.expander("Record actions", expanded=False):
    rows = st.session_state.get("records_list", [])
    if rows:
        search_filename = st.text_input("Filename contains", value="", key="search_filename")
        filtered = [r for r in rows if (search_filename.lower() in (r.get("filename","").lower()))] if search_filename else rows
        options = [f"{r['id']} — {r.get('filename','(no name)')} — {r.get('status','')} — {r.get('created_at','')}" for r in filtered]
        sel = st.selectbox("Select record", options, key="record_selectbox")
        try:
            selected_id = int(sel.split("—")[0].strip())
        except Exception:
            selected_id = None

        st.markdown("")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Open Parsed File", key="open_main_btn"):
                if selected_id:
                    try:
                        rr = requests.get(f"{api_records}/{selected_id}", timeout=6)
                        if rr.ok:
                            st.session_state["last_opened_record"] = rr.json()
                            st.success(f"Opened record {selected_id}")
                        else:
                            st.error(f"Fetch failed: {rr.status_code}")
                    except Exception as e:
                        st.error(f"Fetch failed: {e}")
                else:
                    st.error("Select a record first")
            if st.button("Reparse File", key="reparse_btn"):
                if selected_id:
                    try:
                        rr = requests.post(f"{api_records}/{selected_id}/reparse", params={"save":"true"}, timeout=60)
                        if rr.ok:
                            st.session_state["last_opened_record"] = rr.json()
                            st.success("Reparse successful (new record saved)")
                        else:
                            st.error(f"Reparse failed: {rr.status_code}")
                    except Exception as e:
                        st.error(f"Reparse failed: {e}")
                else:
                    st.error("Select a record first")
        with c2:
            if st.button("Download File", key="download_file_btn"):
                if selected_id:
                    try:
                        dl = requests.get(f"{api_records}/{selected_id}/download", timeout=6)
                        if dl.status_code == 200:
                            fname = filtered[0].get("filename", f"record_{selected_id}")
                            st.sidebar.download_button("Download raw file", data=dl.content, file_name=fname, mime="application/octet-stream", key="download_raw_btn")
                        else:
                            st.error(f"Download failed: {dl.status_code}")
                    except Exception as e:
                        st.error(f"Download failed: {e}")
                else:
                    st.error("Select a record first")

        st.markdown("---")
        if st.button("Export shown records as CSV", key="export_csv_btn"):
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["id","filename","status","created_at"])
            for rec in filtered:
                writer.writerow([rec.get("id"), rec.get("filename"), rec.get("status"), rec.get("created_at")])
            st.sidebar.download_button("Download CSV", data=buf.getvalue(), file_name="records_export.csv", mime="text/csv", key="download_csv_btn")
        if st.button("Export shown records as JSON", key="export_json_btn"):
            st.sidebar.download_button("Download JSON", data=json.dumps(filtered, indent=2), file_name="records_export.json", mime="application/json", key="download_json_btn")
    else:
        st.write("No cached records. Click 'Fetch recent records' above.")

st.sidebar.markdown("---")
st.sidebar.caption("Use the expander to act on a selected record.")

# ---------------- Main area ----------------
main = st.container()
with main:

    st.markdown("---")

    tab_single, tab_batch = st.tabs(["📄 Parse Single File", "📁 Parse Batch Files"])

    # ==========================
    #     SINGLE FILE TAB
    # ==========================
    with tab_single:
        st.header("Parse Single File")
        c1, c2 = st.columns([2,1])
        with c1:
            uploaded = st.file_uploader("Upload a resume",
                                        type=["pdf","docx","txt","png","jpg","jpeg","tiff"],
                                        key="single_upload")
        with c2:
            include_conf = st.checkbox("Include confidence", value=False, key="single_conf")
            save_single_toggle = st.checkbox("Save parsed result to DB", value=False, key="save_single_toggle")

        if st.button("Parse Single Resume", key="parse_single_btn"):
            if not uploaded:
                st.warning("Upload a file first")
            else:
                try:
                    files = {"file": (uploaded.name, uploaded.getvalue())}
                    params = {"include_confidence": str(include_conf).lower()}
                    if save_single_toggle:
                        params["save"] = "true"

                    r = requests.post(api_parse, files=files, params=params, timeout=120)

                    if r.status_code == 200:
                        data = r.json()
                        st.session_state["last_opened_record"] = data
                        st.success("Parsed successfully")

                        if "parse_time" in data:
                            st.info(f"⏱ Parse Time: {data['parse_time']:.2f} seconds")

                        if "resume_quality_score" in data:
                            circular_gauge(data["resume_quality_score"])

                    else:
                        st.error(f"API returned {r.status_code}: {r.text}")
                except Exception as e:
                    st.error(f"Request failed: {e}")

    # ==========================
    #     BATCH FILE TAB
    # ==========================
    with tab_batch:
        st.header("Parse Bulk Files")
        b1, b2 = st.columns([2,1])
        with b1:
            bulk_files = st.file_uploader(
                "Select multiple resumes",
                accept_multiple_files=True,
                type=["pdf","docx","txt","png","jpg","jpeg","tiff"],
                key="bulk_upload"
            )
        with b2:
            save_bulk_toggle = st.checkbox("Save to DB", value=False, key="save_bulk_toggle")

        c3, c4 = st.columns([2,2])
        with c3:
            parallel_clicked = st.button("Parse in Parallel", key="parallel_batch_btn")
        with c4:
            sequential_clicked = st.button("Parse Sequentially", key="seq_batch_btn")

        # --- batch handling (keep your existing functions) ---
        def show_batch_results(resp_json):
            st.subheader("Batch Results")
            st.write(f"Processed: {resp_json.get('batch_count', 'n/a')} files")
            if "parse_time" in resp_json:
                st.info(f"⏱ Batch Parse Time: {resp_json['parse_time']:.2f} seconds")

            for r in resp_json.get("results", [])[:20]:
                st.markdown(f"### {r.get('file')}")
                st.write(f"Status: `{r.get('status')}`")
                if r.get("status") == "ok":
                    parsed = r.get("parsed", {})
                    st.code(json.dumps(parsed, indent=2), language="json")
            st.download_button("Download batch JSON",
                               data=json.dumps(resp_json, indent=2),
                               file_name="batch_results.json",
                               mime="application/json",
                               key="download_batch_json")

        # --- parallel handler ---
        if parallel_clicked:
            if not bulk_files:
                st.warning("Select files first")
            else:
                try:
                    files_payload = [("files", (f.name, f.getvalue())) for f in bulk_files]
                    params = {"save": "true"} if save_bulk_toggle else {}
                    r = requests.post(api_batch, files=files_payload, params=params, timeout=600)
                    if r.status_code == 200:
                        show_batch_results(r.json())
                    else:
                        st.error(f"Batch API error {r.status_code}")
                except Exception as e:
                    st.error(f"Parallel batch failed: {e}")

        # --- sequential handler ---
        if sequential_clicked:
            if not bulk_files:
                st.warning("Select files first")
            else:
                results = []
                progress = st.progress(0)
                total = len(bulk_files)

                for i, f in enumerate(bulk_files):
                    try:
                        files_param = {"file": (f.name, f.getvalue())}
                        params = {"include_confidence": "false"}
                        if save_bulk_toggle:
                            params["save"] = "true"

                        r = requests.post(api_parse, files=files_param, params=params, timeout=180)
                        if r.status_code == 200:
                            results.append({"file": f.name, "status": "ok", "result": r.json()})
                        else:
                            results.append({"file": f.name, "status": f"error {r.status_code}"})
                    except Exception as e:
                        results.append({"file": f.name, "status": "exception", "result": str(e)})

                    progress.progress((i+1)/total)

                st.success("Sequential batch finished")
                st.write(results[:10])
                st.download_button("Download sequential results",
                                   data=json.dumps(results, indent=2),
                                   file_name="seq_batch_results.json",
                                   mime="application/json",
                                   key="download_seq_json")

    st.markdown("---")

    # Display last opened/parsed record full-width
    last = st.session_state.get("last_opened_record")
    if last:
        st.subheader("Opened / Parsed Record")
        # 'last' may be either the API response (with 'parsed') or a stored parsed object
        if isinstance(last, dict) and "parsed" in last:
            parsed = last.get("parsed", {})
            confidence = last.get("confidence") or parsed.get("confidence")
            dbid = last.get("db_id")
        else:
            parsed = last if isinstance(last, dict) else {}
            confidence = parsed.get("confidence")
            dbid = parsed.get("db_id")
        # header summary
        meta_cols = st.columns([1,3,1])
        meta_cols[0].markdown(f"**Name**\n{parsed.get('name','')}")
        meta_cols[1].markdown(f"**Primary contact**\n{parsed.get('email','')}  \n{parsed.get('phoneNumber','')}")
        meta_cols[2].markdown(f"**DB id**\n{dbid or ''}")
        if confidence:
            st.markdown(f"**Confidence (summary):** `{confidence}`")
        if "resume_quality_score" in last:
            circular_gauge(last["resume_quality_score"], label="Quality Score")
        st.markdown("#### Full parsed JSON")
        # truncated JSON preview
        st.code(json.dumps(parsed, indent=2), language="json")
        # st.markdown(
        #     f"<pre style='font-size:18px; line-height:1.5; padding:20px; background:#fafafa;'>{json.dumps(parsed, indent=2)}</pre>",
        #     unsafe_allow_html=True
        # )

    else:
        st.info("No parsed/opened record yet. Parse a file or fetch & open a saved record from the sidebar.")

    st.markdown("---")
    st.write("Debug:")
    st.write(f"API parse: {api_parse}")
    st.write(f"API batch: {api_batch}")
    st.write(f"Records API: {api_records}")
