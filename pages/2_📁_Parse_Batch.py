#!/usr/bin/env python3
import json
import requests
import streamlit as st
import pandas as pd
from utils import circular_gauge

st.set_page_config(page_title="Batch Parsing", layout="wide")

DEFAULT_API_BASE = "http://127.0.0.1:8000"
api_base = st.sidebar.text_input("API base URL", value=DEFAULT_API_BASE)
api_parse = api_base.rstrip("/") + "/parse"
api_batch = api_base.rstrip("/") + "/parse/batch"
api_records = api_base.rstrip("/") + "/records"

st.markdown("<h2 style='margin:0'>📁 Parse Batch of Resumes</h2><div style='color:#666;margin-bottom:12px'>Upload multiple files and choose parse mode.</div>", unsafe_allow_html=True)

# ----- uploader + options -----
col_up = st.container()
with col_up:
    c1, c2 = st.columns([3,1])
    with c1:
        batch_files = st.file_uploader("Select multiple resumes", accept_multiple_files=True,
                                      type=["pdf","docx","txt","png","jpg","jpeg","tiff"], key="batch_files")
    with c2:
        save_toggle = st.checkbox("Save each parsed to DB", value=False, key="batch_save")
        include_conf = st.checkbox("Include confidence", value=False, key="batch_conf")

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# action buttons
a1, a2, a3 = st.columns([1,1,1])
with a1:
    parse_parallel = st.button("Parse in Parallel")
with a2:
    parse_sequential = st.button("Parse Sequentially")
with a3:
    clear_batch = st.button("Clear Results")

if clear_batch:
    st.session_state.pop("batch_results", None)
    # st.experimental_rerun()

# helper to display single result card
# ---------- robust result rendering ----------
def render_result_card(result):
    st.markdown("---")
    # normalize result shape
    # expected minimal: {"file":..., "status":..., "parsed": {...}, "resume_quality_score":..., "confidence_percentage": {...}, "parse_time": ...}
    file = result.get("file") or result.get("filename") or "unknown"
    status = result.get("status", "n/a")

    # parsed object may be nested or be the dict itself
    parsed = result.get("parsed") if isinstance(result.get("parsed"), dict) else None
    if not parsed:
        if all(k in result for k in ("name", "email")):
            parsed = result
        else:
            parsed = result.get("result") or {}

    parse_time = result.get("parse_time") or parsed.get("parse_time") or result.get("elapsed")

    st.markdown(f"### {file}  —  `{status}`")
    cols = st.columns([2,1,1])
    with cols[0]:
        st.markdown(f"**Name:** {parsed.get('name','—')}  \n**Email:** {parsed.get('email','—')}")
    with cols[1]:
        if parse_time:
            st.info(f"⏱ {float(parse_time):.2f} s")
    with cols[2]:
        score = result.get("resume_quality_score") or parsed.get("resume_quality_score")
        if score is not None:
            circular_gauge(score, label="Quality")
        else:
            st.write("")

    # confidence chart
    conf_pct = result.get("confidence_percentage") or parsed.get("confidence_percentage") or {}
    if isinstance(conf_pct, dict) and conf_pct:
        st.markdown("**Confidence (by field)**")
        items = [(k, float(v)) for k, v in conf_pct.items()]
        df = pd.DataFrame(items, columns=["field", "confidence"]).set_index("field").sort_values("confidence", ascending=True)
        st.bar_chart(df)
    # JSON expander
    with st.expander("Show parsed JSON", expanded=False):
        display_obj = {"file": file, "status": status, "parsed": parsed}
        # include confidence and score if present
        if isinstance(conf_pct, dict) and conf_pct:
            display_obj["confidence_percentage"] = conf_pct
        if score is not None:
            display_obj["resume_quality_score"] = score
        st.code(json.dumps(display_obj, indent=2), language="json")

    # Save button: POST to /save on backend (api_base + "/save")
    save_endpoint = api_base.rstrip("/") + "/save"
    if st.button("Save this result", key=f"save_{file}"):
        try:
            payload = {"filename": file, "parsed": parsed}
            resp = requests.post(save_endpoint, json=payload, timeout=10)
            if resp.ok:
                st.success("Saved to DB")
            else:
                st.error(f"Save failed: {resp.status_code} — {resp.text}")
        except Exception as e:
            st.error(f"Save error: {e}")

# ---------- API callers ----------
def call_batch_api(files_payload, params):
    try:
        r = requests.post(api_batch, files=files_payload, params=params, timeout=600)
        return r
    except Exception as e:
        st.error(f"Batch request failed: {e}")
        return None

def call_single_api(file_tuple, params):
    try:
        r = requests.post(api_parse, files={"file": file_tuple}, params=params, timeout=180)
        return r
    except Exception as e:
        st.error(f"Request failed for {file_tuple[0]}: {e}")
        return None

# ---------- parallel handler (store normalized results, then enrich missing fields) ----------
if parse_parallel:
    if not batch_files:
        st.warning("Please select files.")
    else:
        st.info("Parallel Parsing... This may take a moment. Please wait!")
        with st.spinner("Processing...", show_time=True):
            files_payload = [("files", (f.name, f.getvalue())) for f in batch_files]
            params = {}
            if save_toggle:
                params["save"] = "true"
            params["include_confidence"] = str(include_conf).lower()
            resp = call_batch_api(files_payload, params)

        if resp and resp.status_code == 200:
            data = resp.json()
            raw_results = data.get("results", [])
            enriched = []

            # Map original uploads by filename for enrichment fallback
            upload_map = {f.name: f for f in batch_files} if batch_files else {}

            for item in raw_results:
                # Normalize file name
                fname = item.get("file") or item.get("filename")
                # If item already contains quality & confidence, keep it
                has_score = item.get("resume_quality_score") is not None
                has_conf = item.get("confidence_percentage") or (isinstance(item.get("confidence"), dict) and item.get("confidence"))
                if has_score and has_conf:
                    enriched.append(item)
                    continue

                # fallback: keep original item
                enriched.append(item)

            st.session_state["batch_results"] = {
                "batch_count": data.get("batch_count", len(enriched)),
                "results": enriched,
                "parse_time": data.get("parse_time"),
            }
            st.success("Batch finished (results enriched)")
        else:
            st.error(f"Batch API error: {resp.status_code if resp else 'n/a'}")

# ---------- sequential handler (unchanged but ensure similar structure) ----------
if parse_sequential:
    if not batch_files:
        st.warning("Please select files.")
    else:
        st.info("Parsing sequentially...")
        total = len(batch_files)
        prog = st.progress(0)
        results = {"batch_count": total, "results": [], "parse_time": 0.0}
        for i, f in enumerate(batch_files):
            file_tuple = (f.name, f.getvalue())
            params = {"include_confidence": str(include_conf).lower()}
            if save_toggle:
                params["save"] = "true"
            r = call_single_api(file_tuple, params)
            if r and r.status_code == 200:
                # single API returns a payload dict; wrap it to envelope shape if needed
                payload = r.json()
                # if payload already an envelope (has 'parsed'), keep it; else wrap
                if isinstance(payload, dict) and "parsed" in payload:
                    results["results"].append(payload)
                else:
                    # wrap into envelope
                    results["results"].append({"file": f.name, "status": "ok", "parsed": payload})
            else:
                results["results"].append({"file": f.name, "status": f"error {r.status_code if r else 'n/a'}"})
            prog.progress((i+1)/total)
        st.session_state["batch_results"] = results
        st.success("Sequential parsing finished")

# ---------- SHOW BATCH RESULTS (summary + on-demand detail) ----------
results_bundle = st.session_state.get("batch_results")
if results_bundle:
    st.markdown("## Batch Results")

    if "parse_time" in results_bundle:
        st.info(f"⏱ Batch parse time: {results_bundle['parse_time']:.2f} s")

    rows = results_bundle.get("results", [])
    total = len(rows)

    st.markdown(f"Showing {min(total,50)} of {total} results (click a row to view details)")

    # Lightweight summary table (fast)
    summary_cols = st.columns([4,1,1,1])  # filename | status | time | actions
    summary_cols[0].markdown("**Filename**")
    summary_cols[1].markdown("**Status**")
    summary_cols[2].markdown("**Time**")
    summary_cols[3].markdown("**Actions**")

    # ensure session selection state
    if "batch_selected_idx" not in st.session_state:
        st.session_state["batch_selected_idx"] = None

    for idx, item in enumerate(rows[:200]):  # cap to 200 for safety
        fname = item.get("file") or item.get("filename") or f"file_{idx}"
        status = item.get("status", "n/a")
        parsed = item.get("parsed") if isinstance(item.get("parsed"), dict) else {}
        ptime = item.get("parse_time") or parsed.get("parse_time") or item.get("elapsed") or ""
        # one-line row
        c0, c1, c2, c3 = st.columns([4,1,1,1])
        c0.markdown(f"**{fname}**\n<small style='color:#888'>{parsed.get('email','')}</small>", unsafe_allow_html=True)
        c1.markdown(f"`{status}`")
        c2.markdown(f"{(float(ptime)):.2f}s" if ptime else "—")
        if c3.button("Show details", key=f"show_detail_{idx}"):
            st.session_state["batch_selected_idx"] = idx
            # scroll-like UX: bring details into view by rerunning (light)
            # st.experimental_rerun()

    st.markdown("---")

    # If an item is selected, render its full heavy card below (only one)
    sel = st.session_state.get("batch_selected_idx")
    if sel is not None and 0 <= sel < len(rows):
        st.markdown(f"### Details — {rows[sel].get('file') or rows[sel].get('filename')}")
        # Render full result card (heavy visuals happen here) with a pleasant spinner
        with st.spinner("Rendering details… this may take a moment", show_time=True):
            render_result_card(rows[sel])

        # navigation buttons for convenience
        nav1, nav2, nav3 = st.columns([1, 1, 6])
        if nav1.button("Prev", key="batch_prev"):
            st.session_state["batch_selected_idx"] = max(0, sel - 1)
            # st.experimental_rerun()
        if nav2.button("Next", key="batch_next"):
            st.session_state["batch_selected_idx"] = min(len(rows) - 1, sel + 1)
            # st.experimental_rerun()
    else:
        st.info("Select a result row to view full details (gauge, chart, JSON).")
