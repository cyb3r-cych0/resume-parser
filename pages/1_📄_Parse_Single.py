#!/usr/bin/env python3
import os
import json
import psutil
import requests
import pandas as pd
import streamlit as st
from utils import circular_gauge
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Parse Single Resume", layout="wide")

DEFAULT_API_BASE = "http://127.0.0.1:8000"
api_base = DEFAULT_API_BASE
api_parse = api_base.rstrip("/") + "/parse"

MODEL_CHOICES = ["en_core_web_sm", "en_core_web_lg", "en_core_web_trf"]
model_choice = st.sidebar.selectbox("📀 NLP model (speed ↔ accuracy)", MODEL_CHOICES, index=0,
                                    help="Pick small (fast), large (better NER), or trf (best accuracy)", key="single_model_choice")
# CSS tweaks
st.markdown(
    """
    <style>
    .card {
      padding:16px;
      border-radius:12px;
      background:#005f69;
      box-shadow:0 6px 18px rgba(0,0,0,0.06);
      margin-bottom:18px;
    }
    .centered {
      display:flex; align-items:center; justify-content:center;
    }
    .muted { color: #000000; font-size:14px; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown("<div class='card'><h2 style='margin:0'>📄 Parse Single Resume</h2><div class='muted'>Upload a file and click Parse</div></div>", unsafe_allow_html=True)

# cache controls
st.sidebar.markdown("---")
st.sidebar.header("🎛️ Cache Control")
cache_enabled = st.sidebar.checkbox("Enable cache (model-aware)", value=True, key="single_cache_enabled")
if st.sidebar.button("🧹 Clear Cache"):
    try:
        resp = requests.post(api_base.rstrip("/") + "/cache/clear", timeout=10)
        if resp.ok:
            st.sidebar.success("Cache cleared on server")
        else:
            st.sidebar.error(f"Clear failed: {resp.status_code}")
    except Exception as e:
        st.sidebar.error(f"Clear failed: {e}")

st.sidebar.markdown("---")
with st.sidebar:
    st.text_input("🛜 API Base URL", value=api_base)

# Centered uploader area
with st.container():
    col1, col2, col3 = st.columns([1, 6, 1])
    with col2:
        uploaded = st.file_uploader("Upload resume (pdf/docx/png/jpg/tiff)", type=["pdf","docx","txt","png","jpg","jpeg","tiff"], key="single_file", help="Drop or click to select")
        st.markdown("<div style='height:6px'; 'margin-top=:15px;'></div>", unsafe_allow_html=True)
        c1, c2 = st.columns([2,2])
        with c1:
            include_conf = st.checkbox("Include confidence", value=False, key="ui_single_conf")
        with c2:
            save_toggle = st.checkbox("Save to DB", value=False, key="ui_single_save")
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        # action buttons row
        btn_col1, btn_col2 = st.columns([2,2])
        with btn_col1:
            parse_clicked = st.button("Parse Resume", key="parse_btn")
        with btn_col2:
            clear_clicked = st.button("Clear Results", key="clear_btn")

if clear_clicked:
    st.session_state.pop("single_file", None)
    st.session_state.pop("last_single_result", None)
    # st.experimental_rerun()

if parse_clicked:
    if not uploaded:
        st.warning("Please upload a resume first.")
    else:
        try:
            st.info("Parsing... This may take a moment. Please wait!")
            with st.spinner("Processing...", show_time=True):
                files = {"file": (uploaded.name, uploaded.getvalue())}
                params = {"include_confidence": str(include_conf).lower(), "model": model_choice,
                          "cache": "true" if cache_enabled else "false"}
                if save_toggle:
                    params["save"] = "true"
                r = requests.post(api_parse, files=files, params=params, timeout=120)
            if r.status_code == 200:
                data = r.json()
                # normalized UI-friendly envelope:
                st.session_state["last_single_result"] = data
                # show success + parse time if present
                st.success("Parsed successfully")
                if "parse_time" in data:
                    st.info(f"⏱ Parse Time: **{data['parse_time']:.2f}** s. 🖥 Parsing Model: **{model_choice}**")
                # show cached badge if backend returned cached timing
                timings = data.get("timings") or (data.get("parsed", {}) or {}).get("timings", {})
                if isinstance(timings, dict) and timings.get("cached"):
                    st.warning("⚡ Result returned from cache")
            else:
                st.error(f"API error {r.status_code}: {r.text}")
        except Exception as e:
            st.error(f"Request failed: {e}")

# Show results area if present
result = st.session_state.get("last_single_result")
if result:
    # layout: left metadata + gauge, right JSON/confidence
    left, right = st.columns([1,2])

    # left: summary card
    with left:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        parsed = result.get("parsed", {}) or result
        st.markdown(f"**File:** {result.get('file','(uploaded)')}")
        if result.get("parse_time") is not None:
            st.markdown(f"⏱ Parse time: **{result['parse_time']:.2f} s**")
        # gauge (use nested keys depending on response shape)
        score = result.get("resume_quality_score") or (parsed.get("resume_quality_score") if isinstance(parsed, dict) else None)
        if score is not None:
            circular_gauge(score, label="Quality Score")
        else:
            st.info("No quality score available")

        # --- INSERT TIMINGS SNIPPET HERE ---
        timings = result.get("timings") or (result.get("parsed", {}) or {}).get("timings")
        if isinstance(timings, dict):
            mt = ", ".join([f"{k}:{('cached' if v is True else f'{v:.2f}s')}" for k, v in timings.items()])
            st.markdown(f"**Timings:** {mt}")

        # small contact summary
        st.markdown("---")
        st.markdown("**Contact**")
        st.write(parsed.get("name", "—"))
        st.write(parsed.get("email","—"))
        st.write(parsed.get("phoneNumber","—"))

        save_endpoint = api_base.rstrip("/") + "/save"
        if st.button("Save parsed result", key="single_save"):
            try:
                payload = {"filename": result.get("file") or uploaded.name, "parsed": result.get("parsed", {})}
                resp = requests.post(save_endpoint, json=payload, timeout=10)
                if resp.ok:
                    st.success("Saved to DB")
                else:
                    st.error(f"Save failed: {resp.status_code} — {resp.text}")
            except Exception as e:
                st.error(f"Save error: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

    # right: confidence and JSON
    with right:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Parsed Data")
        # confidence table (if available)
        conf_percent = None
        if "confidence_percentage" in result:
            conf_percent = result["confidence_percentage"]
        elif isinstance(parsed, dict) and "confidence_percentage" in parsed:
            conf_percent = parsed["confidence_percentage"]

        if conf_percent:
            st.markdown("**Field confidence (%)**")
            # Build DataFrame sorted by score (descending)
            items = [(k, float(v)) for k, v in conf_percent.items()]
            df = pd.DataFrame(items, columns=["field", "confidence"]).set_index("field")
            df = df.sort_values("confidence", ascending=False)

            # Show horizontal bar chart using st.bar_chart (Streamlit will render cleanly)
            st.bar_chart(df)
            st.markdown("---")

        st.subheader("Full JSON")
        # collapsible JSON view
        with st.expander("Show parsed JSON", expanded=False):
            st.code(json.dumps(result, indent=2), language="json")
        st.markdown("</div>", unsafe_allow_html=True)
