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
    st.header("Parse Single File")
    c1, c2 = st.columns([2,1])
    with c1:
        uploaded = st.file_uploader("Upload single resume", type=["pdf","docx","txt","png","jpg","jpeg","tiff"], key="single_upload")
    with c2:
        include_conf = st.checkbox("Include confidence", value=False, key="single_conf")
        save_single_toggle = st.checkbox("Save parsed result to DB (single)", value=False, key="save_single_toggle")
    if st.button("Parse single", key="parse_single_btn"):
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
                    # show parsed result full-width
                    st.session_state["last_opened_record"] = data
                    st.success("Parsed result")
                else:
                    st.error(f"API returned {r.status_code}: {r.text}")
            except Exception as e:
                st.error(f"Request failed: {e}")

    st.markdown("---")

    # ---------------- Bulk upload block ----------------
    st.header("Parse Bulk Files")
    bcol1, bcol2 = st.columns([2,1])
    with bcol1:
        bulk_files = st.file_uploader(
            "Select multiple resumes (pdf/docx/txt/image)",
            accept_multiple_files=True,
            type=["pdf","docx","txt","png","jpg","jpeg","tiff"],
            key="bulk_upload"
        )
    with bcol2:
        save_bulk_toggle = st.checkbox("Save each parsed result to DB (batch)", value=False, key="save_bulk_toggle")
    bcol3, bcol4 = st.columns([2,2])
    with bcol3:
        parallel_clicked = st.button("Parse parallel", key="parallel_batch_btn")
    with bcol4:
        sequential_clicked = st.button("Parse sequential", key="seq_batch_btn")

    def show_batch_results(resp_json):
        st.subheader("Batch results")
        st.write(f"Processed: {resp_json.get('batch_count', 'n/a')} files")
        for r in resp_json.get("results", [])[:20]:
            st.markdown(f"**{r.get('file')}** — status: `{r.get('status')}`")
            if r.get("status") == "ok":
                parsed = r.get("parsed", {})
                # show name/email/phone summary and confidence (if present)
                name = parsed.get("name", "")
                email = parsed.get("email", "")
                phone = parsed.get("phoneNumber", "")
                st.markdown(f"- Name: **{name}**  \n- Email: {email}  \n- Phone: {phone}")
                if r.get("parsed") and isinstance(r, dict):
                    conf = r.get("confidence") or parsed.get("confidence") or r.get("confidence")
                    # show confidence if exists at top-level or inside parsed->confidence
                    if conf:
                        st.markdown(f"- Confidence: `{conf}`")
                # truncated JSON preview
                st.code(json.dumps(parsed, indent=2)[:4000], language="json")
                # st.markdown(
                #     f"<pre style='font-size:18px; line-height:1.5; padding:20px; background:#fafafa;'>{json.dumps(parsed, indent=2)}</pre>",
                #     unsafe_allow_html=True
                # )

            else:
                st.text(r.get("error") or r.get("parsed") or "")
        st.download_button("Download full batch JSON", data=json.dumps(resp_json, indent=2), file_name="batch_results.json", mime="application/json", key="download_batch_json")

    # Parallel handler
    if parallel_clicked:
        if not bulk_files:
            st.warning("Select files first")
        else:
            try:
                files_payload = []
                for f in bulk_files:
                    files_payload.append(("files", (f.name, f.getvalue())))
                params = {}
                if save_bulk_toggle:
                    params["save"] = "true"
                r = requests.post(api_batch, files=files_payload, params=params, timeout=600)
                if r.status_code == 200:
                    show_batch_results(r.json())
                else:
                    st.error(f"Batch API error: {r.status_code} — {r.text}")
            except Exception as e:
                st.error(f"Parallel batch failed: {e}")

    # Sequential handler
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
                        results.append({"file": f.name, "status": f"error {r.status_code}", "result": r.text})
                except Exception as e:
                    results.append({"file": f.name, "status": "exception", "result": str(e)})
                progress.progress((i+1)/total)
            st.success("Sequential batch finished")
            st.write("Summary (first 10):")
            for rr in results[:10]:
                st.write(rr["file"], "-", rr["status"])
            st.download_button("Download sequential results", data=json.dumps(results, indent=2), file_name="seq_batch_results.json", mime="application/json", key="download_seq_json")

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
