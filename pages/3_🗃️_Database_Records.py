#!/usr/bin/env python3
import io
import csv
import json
import requests
import streamlit as st
import pandas as pd
from datetime import datetime
from utils import circular_gauge

st.set_page_config(page_title="Saved Records", layout="wide")

DEFAULT_API_BASE = "http://127.0.0.1:8000"
api_base = st.sidebar.text_input("API base URL", value=DEFAULT_API_BASE)
api_records = api_base.rstrip("/") + "/records"

st.markdown("<h2 style='margin:0'>🗃️ Saved Parsed Records</h2><div style='color:#666;margin-bottom:12px'>Browse, inspect, export and reparse stored records.</div>", unsafe_allow_html=True)

# ---------------- Controls ----------------
controls_col1, controls_col2, controls_col3 = st.columns([2,2,2])

with controls_col1:
    records_limit = st.number_input("Limit", min_value=1, max_value=1000, value=50, key="db_limit")
    if st.button("Fetch Records", key="fetch_records_btn"):
        try:
            r = requests.get(api_records, params={"limit": records_limit}, timeout=6)
            if r.ok:
                st.session_state["records_list"] = r.json().get("results", [])
                st.success(f"Loaded {len(st.session_state['records_list'])} records")
            else:
                st.error(f"List failed: {r.status_code}")
        except Exception as e:
            st.error(f"List request failed: {e}")

with controls_col2:
    search_q = st.text_input("Search filename contains", value="", key="db_search")
    date_from = st.date_input("From (created)", value=None, key="db_from")
    date_to = st.date_input("To (created)", value=None, key="db_to")

with controls_col3:
    show_cached_only = st.checkbox("Show cached only", value=False, key="db_cached_only")
    if st.button("Clear cached rows", key="clear_cached_btn"):
        st.session_state.pop("records_list", None)
        st.info("Cleared cached list")

st.markdown("---")

# ---------------- Load initial records if missing ----------------
if "records_list" not in st.session_state:
    st.session_state["records_list"] = []

# quick helper to filter records locally
def filter_records(rows, q, dfrom, dto, cached_only):
    out = []
    for r in rows:
        fname = r.get("filename","")
        created = r.get("created_at") or r.get("created")
        if q and q.lower() not in fname.lower():
            continue
        if dfrom or dto:
            try:
                if created:
                    dt = datetime.fromisoformat(created)
                    if dfrom and dt.date() < dfrom:
                        continue
                    if dto and dt.date() > dto:
                        continue
            except Exception:
                pass
        if cached_only:
            # cached flag may be absent; treat as False if missing
            meta_cached = r.get("cached", False)
            if not meta_cached:
                # also try to detect cached from stored small flag (not guaranteed)
                continue
        out.append(r)
    return out

# ---------------- Table of records (summary) ----------------
rows = st.session_state.get("records_list", [])
filtered = filter_records(rows, search_q, date_from, date_to, show_cached_only)

st.markdown(f"**Results:** {len(filtered)} (showing {min(len(filtered), records_limit)})")
if not filtered:
    st.info("No records to show. Click 'Fetch Records' or parse files to populate the DB.")
else:
    # build a DataFrame for summary display
    table_rows = []
    for r in filtered[:records_limit]:
        rid = r.get("id")
        fname = r.get("filename","")
        status = r.get("status","")
        created = r.get("created_at", r.get("created",""))
        cached_flag = r.get("cached", False)
        table_rows.append({"id": rid, "filename": fname, "status": status, "created_at": created, "cached": cached_flag})

    df = pd.DataFrame(table_rows)
    if not df.empty:
        # small table view
        st.dataframe(df[["id","filename","status","created_at","cached"]], width='stretch', height=240)

    # actions on table: select ID
    st.markdown("---")
    select_col1, select_col2 = st.columns([3,1])
    with select_col1:
        selected_id = st.number_input("Open record id", min_value=0, value=0, step=1, key="select_record_id")
    with select_col2:
        if st.button("Open", key="open_selected_btn"):
            if selected_id:
                try:
                    rr = requests.get(f"{api_base.rstrip('/')}/records/{selected_id}", timeout=6)
                    if rr.ok:
                        st.session_state["last_opened_record"] = rr.json()
                        st.success(f"Opened record {selected_id}")
                    else:
                        st.error(f"Fetch failed: {rr.status_code}")
                except Exception as e:
                    st.error(f"Fetch failed: {e}")

    # export visible records
    exp_c1, exp_c2 = st.columns([1,1])
    with exp_c1:
        if st.button("Export visible CSV", key="export_visible_csv"):
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["id","filename","status","created_at"])
            for rec in filtered[:records_limit]:
                writer.writerow([rec.get("id"), rec.get("filename"), rec.get("status"), rec.get("created_at")])
            st.download_button("Download CSV", data=buf.getvalue(), file_name="records_visible.csv", mime="text/csv", key="dl_visible_csv")
    with exp_c2:
        if st.button("Export visible JSON", key="export_visible_json"):
            st.download_button("Download JSON", data=json.dumps(filtered[:records_limit], indent=2), file_name="records_visible.json", mime="application/json", key="dl_visible_json")

# ---------------- Show last opened record or selection ----------------
rec = st.session_state.get("last_opened_record")
if rec:
    st.markdown("---")
    st.subheader("Opened Record")

    # support both shapes: API envelope or parsed-only
    parsed = rec.get("parsed") if isinstance(rec.get("parsed"), dict) else (rec if isinstance(rec, dict) else {})
    confidence_pct = rec.get("confidence_percentage") or parsed.get("confidence_percentage") or rec.get("confidence")
    score = rec.get("resume_quality_score") or parsed.get("resume_quality_score")
    timings = rec.get("timings") or parsed.get("timings")

    meta_cols = st.columns([1,3,1])
    meta_cols[0].markdown(f"**Filename**\n{rec.get('filename','')}")
    meta_cols[1].markdown(f"**Contact**\n{parsed.get('name','')}  \n{parsed.get('email','')}")
    meta_cols[2].markdown(f"**ID**\n{rec.get('id','')}")

    st.markdown("---")
    # show gauge + timings + confidence chart + JSON
    left, right = st.columns([1,2])
    with left:
        if score is not None:
            circular_gauge(score, label="Quality")
        if isinstance(timings, dict):
            mt = ", ".join([f"{k}:{('cached' if v is True else f'{v:.2f}s')}" for k,v in timings.items()])
            st.markdown(f"**Timings:** {mt}")
        st.markdown("---")
        # download raw file
        if st.button("Download raw file", key="db_download_raw"):
            try:
                dl = requests.get(f"{api_base.rstrip('/')}/records/{rec.get('id')}/download", timeout=6)
                if dl.status_code == 200:
                    fname = rec.get("filename", f"record_{rec.get('id')}")
                    st.download_button("Download bytes", data=dl.content, file_name=fname,
                                       mime="application/octet-stream", key="dl_raw_btn")
                else:
                    st.error(f"Download failed: {dl.status_code}")
            except Exception as e:
                st.error(f"Download failed: {e}")

        # Re-parse stored file (calls backend and saves result)
        if st.button("Re-parse stored file", key="db_reparse"):
            try:
                rr = requests.post(f"{api_base.rstrip('/')}/records/{rec.get('id')}/reparse",
                                   params={"include_confidence": "true", "save": "true"}, timeout=120)
                if rr.ok:
                    st.success("Reparse completed and saved")
                    # update last opened record with returned parsed result (API returns parsed envelope)
                    st.session_state["last_opened_record"] = rr.json()

                    # refresh records list in session (best-effort)
                    try:
                        rlist = requests.get(api_base.rstrip("/") + "/records", params={"limit": records_limit},
                                             timeout=6)
                        if rlist.ok:
                            st.session_state["records_list"] = rlist.json().get("results", [])
                    except Exception:
                        pass
                else:
                    st.error(f"Reparse failed: {rr.status_code} — {rr.text}")
            except Exception as e:
                st.error(f"Reparse failed: {e}")

        # Delete flow: two-step confirmation to avoid accidents
        delete_key = f"delete_pending_{rec.get('id')}"
        if st.button("Delete record", key="db_delete"):
            st.session_state[delete_key] = True

        if st.session_state.get(delete_key):
            st.warning("Confirm delete — this will remove the record permanently.")
            if st.button("Confirm delete", key=f"db_confirm_delete_{rec.get('id')}"):
                try:
                    d = requests.delete(f"{api_base.rstrip('/')}/records/{rec.get('id')}", timeout=6)
                    if d.ok:
                        st.success("Record deleted")
                        # remove from session lists & clear opened record
                        st.session_state["last_opened_record"] = None
                        try:
                            st.session_state["records_list"] = [x for x in st.session_state.get("records_list", []) if
                                                                x.get("id") != rec.get("id")]
                        except Exception:
                            pass
                        # clear the pending flag
                        st.session_state.pop(delete_key, None)
                    else:
                        st.error(f"Delete failed: {d.status_code} — {d.text}")
                except Exception as e:
                    st.error(f"Delete failed: {e}")
            if st.button("Cancel", key=f"db_cancel_delete_{rec.get('id')}"):
                st.session_state.pop(delete_key, None)

    with right:
        if isinstance(confidence_pct, dict) and confidence_pct:
            st.markdown("**Field confidence (%)**")
            items = [(k, float(v)) for k, v in confidence_pct.items()]
            df = pd.DataFrame(items, columns=["field","confidence"]).set_index("field").sort_values("confidence", ascending=False)
            st.bar_chart(df)
            st.markdown("---")

        st.subheader("Full parsed JSON")
        with st.expander("Show parsed JSON", expanded=True):
            st.code(json.dumps(parsed, indent=2), language="json")

    st.markdown("---")

# ---------------- Footer / debug ----------------
st.markdown("### Tools")
st.write("You can open records from the home page 'Recent Activity' or by typing an ID above.")
st.write(f"Backend: {api_base}")
