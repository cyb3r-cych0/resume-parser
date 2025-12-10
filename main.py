#!/usr/bin/env python3
import requests
import streamlit as st
import psutil
import os
import shutil
import sqlite3
import psutil
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Parsely — API", layout="wide")

# -------------------- Hero Title --------------------
st.markdown(
    """
    <h1 style='text-align:center; color:#4caf50; font-size:60px; margin-bottom:0;'>
        Parsely — API
    </h1>
    <h3 style='text-align:center; color:#555; margin-top:-10px;'>
        Automated Resume Intelligence Platform
    </h3>
    """,
    unsafe_allow_html=True
)

# -------------------- Backend Helpers --------------------
# --- helper: API, DB & OCR check ---
def system_status(api_base):
    status = {
        "api_ready": False,
        "db_ready": False,
        "ocr_ready": False
    }
    try:
        r = requests.get(api_base.rstrip("/") + "/health", timeout=3)
        status["api_ready"] = r.ok
    except Exception:
        status["api_ready"] = False
    try:
        conn = sqlite3.connect("data/parsed_resumes.db")  # adjust if your DB file has diff name
        conn.execute("SELECT name FROM sqlite_master LIMIT 1;")
        conn.close()
        status["db_ready"] = True
    except Exception:
        status["db_ready"] = False
    status["ocr_ready"] = shutil.which("tesseract") is not None
    return status

# --- helper:get backend live info ---
def get_backend_info(api_base):
    info = {"latency_ms": None, "version": "unknown"}
    health_url = api_base.rstrip("/") + "/health"
    try:
        import time
        start = time.perf_counter()
        r = requests.get(health_url, timeout=3)
        end = time.perf_counter()
        if r.ok:
            info["latency_ms"] = round((end - start) * 1000, 2)
            info["version"] = r.json().get("version", "unknown")
    except Exception:
        pass
    return info

# --- helper: fetch and display recent records ---
def fetch_recent_records(api_base, limit=5):
    try:
        r = requests.get(api_base.rstrip("/") + "/records", params={"limit": limit}, timeout=4)
        if r.ok:
            return r.json().get("results", [])
    except Exception:
        pass
    return []

# --- helper: render small system stats cards ---
def _color_for_pct(pct):
    """Return brighter color shades."""
    if pct is None:
        return "#f0f0f0"
    if pct < 60:
        return "#d1f5d3"   # brighter green
    if pct < 85:
        return "#fff2b3"   # bright yellow
    return "#ffd4d4"       # bright red


def render_system_stats(auto_refresh=True):
    if auto_refresh:
        st_autorefresh(interval=2000, key="system_stats_refresh")

    cpu_pct = psutil.cpu_percent(interval=0.2)
    cpu_count = psutil.cpu_count(logical=True)
    mem = psutil.virtual_memory()
    mem_pct = mem.percent
    max_workers_cap = int(os.getenv("MAX_WORKERS_CAP", "6"))
    proc_count = len(psutil.pids())

    st.markdown("### 🖥 System Stats")

    def card(title, body, bg="#f0f0f0"):
        st.markdown(
            f"""
            <div style='padding:12px; margin-bottom:10px; border-radius:12px;
                        background:{bg};
                        border:1px solid rgba(0,0,0,0.08);
                        box-shadow: 0px 2px 4px rgba(0,0,0,0.05);
                        color:#000;'>
                <div style="font-weight:700; font-size:15px; margin-bottom:6px; color:#000;">
                    {title}
                </div>
                <div style="font-size:14px; color:#222;">
                    {body}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    # CPU
    cpu_bg = _color_for_pct(cpu_pct)
    card("CPU", f"{cpu_pct:.0f}% used<br>{cpu_count} logical cores", bg=cpu_bg)

    # Memory
    mem_bg = _color_for_pct(mem_pct)
    card("Memory", f"{mem_pct:.0f}% used<br>{round(mem.total/1024**3,1)} GB total", bg=mem_bg)

    # Workers cap (neutral)
    card("Workers Cap", str(max_workers_cap), bg="#fafafa")

    # Processes (neutral)
    card("Processes", str(proc_count), bg="#fafafa")

with st.sidebar:
    render_system_stats()

st.markdown("---")
st.subheader(" 🖥 Backend Status")

api_base = st.text_input("API Base URL", value="http://127.0.0.1:8000")

stat = system_status(api_base)
col1, col2, col3 = st.columns(3)
col1.metric("API Ready", "Yes" if stat["api_ready"] else "No")
col2.metric("DB Ready", "Yes" if stat["db_ready"] else "No")
col3.metric("OCR Ready", "Yes" if stat["ocr_ready"] else "No")
st.markdown("---")

backend_info = get_backend_info(api_base)
col_a, col_b = st.columns(2)
lat = backend_info["latency_ms"]
ver = backend_info["version"]
col_a.metric("Latency", f"{lat} ms" if lat else "N/A")
col_b.metric("API Version", ver)

api_health = api_base.rstrip("/") + "/health"
col1, col2 = st.columns([1,3])
with col1:
    if st.button("Check Backend Health"):
        try:
            r = requests.get(api_health, timeout=3)
            if r.ok:
                st.success("🟢 Backend Connected")
                st.session_state["backend_ok"] = True
            else:
                st.error(f"🔴 Backend Error: {r.status_code}")
                st.session_state["backend_ok"] = False
        except Exception as e:
            st.error(f"🔴 Failed: {e}")
            st.session_state["backend_ok"] = False
with col2:
    if st.session_state.get("backend_ok") is True:
        st.info("Backend is healthy. You can now parse resumes from the menu.")
    elif st.session_state.get("backend_ok") is False:
        st.warning("Backend unreachable. Start FastAPI first.")

st.markdown("---")
st.subheader("Quick Actions")

c1, c2, c3 = st.columns(3)
card_style = """
    padding:20px; 
    border-radius:12px; 
    background:#f5f5f5; 
    box-shadow:0 2px 6px rgba(0,0,0,0.1); 
    text-align:center; 
    cursor:pointer;
"""
with c1:
    if st.button("📄 Parse Single", key="go_single"):
        st.switch_page("pages/1_📄_Parse_Single.py")
with c2:
    if st.button("📁 Parse Batch", key="go_batch"):
        st.switch_page("pages/2_📁_Parse_Batch.py")
with c3:
    if st.button("🗃️ View Records", key="go_records"):
        st.switch_page("pages/3_🗃️_Database_Records.py")

st.markdown("---")
st.subheader("Recent Activity")

recent = fetch_recent_records(api_base, limit=5)
if recent:
    for rec in recent:
        rid = rec.get("id")
        fname = rec.get("filename", "—")
        status = rec.get("status", "—")
        created = rec.get("created_at", rec.get("created", "—"))
        cols = st.columns([4,1,1])
        cols[0].markdown(f"**{fname}**  \n<small style='color:#666'>{created}</small>", unsafe_allow_html=True)
        cols[1].markdown(f"`{status}`")
        if cols[2].button("Open", key=f"open_recent_{rid}"):
            try:
                rr = requests.get(f"{api_base.rstrip('/')}/records/{rid}", timeout=4)
                if rr.ok:
                    # store record in session
                    st.session_state["last_opened_record"] = rr.json()
                    st.success(f"Opened record {rid}")
                    # auto-switch to the Records page
                    st.switch_page("pages/3_🗃️_Database_Records.py")
                else:
                    st.error(f"Failed to open record ({rr.status_code})")
            except Exception as e:
                st.error(f"Open failed: {e}")
else:
    st.info("No recent records. Parse a file or fetch records from the Records page.")

st.markdown("---")
st.markdown(
    """
    <div style='text-align:center; color:#888; font-size:14px; margin-top:40px;'>
        Parsely © 2025 — Resume Parsing & Intelligence Suite 
    </div>
    <div style='text-align:center; color:#4caf50; font-size:12px; margin-top:10px;'>
        Developed by cyb3-cych0
    </div>
    """,
    unsafe_allow_html=True
)
