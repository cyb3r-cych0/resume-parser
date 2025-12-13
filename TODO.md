# Run Offline Mode Completely

# THEME TOGGLE

if "theme" not in st.session_state:
    st.session_state["theme"] = "light"

# Top-right small toggle; clicking the button sets session_state and Streamlit automatically reruns
cols = st.columns([1, 6, 1])
with cols[2]:
    btn_label = "🌙 Dark" if st.session_state["theme"] == "light" else "☀️ Light"
    if st.button(btn_label, key="theme_toggle_btn"):
        st.session_state["theme"] = "dark" if st.session_state["theme"] == "light" else "light"
        # no explicit st.experimental_rerun() — button click triggers rerun automatically

# SVG icon HTML (decorative)
ICON_HTML = """
<span id="theme-icon" style="margin-left:6px; vertical-align: middle;">
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="12" cy="12" r="5" stroke="currentColor" stroke-width="1.4"></circle>
    <g stroke="currentColor" stroke-width="1.4">
      <path d="M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/>
    </g>
  </svg>
</span>
"""
st.markdown(ICON_HTML, unsafe_allow_html=True)

# Stronger CSS: set global text color to --text so checkbox labels and small controls follow theme.
DARK_CSS = """
:root{
  --bg:#0c0f14; --text:#e6eef8; --muted:#9aa7b2; --card:#111318; --accent:#2b6cb0;
}
body, .stApp, .block-container { background: var(--bg) !important; color: var(--text) !important; }
/* enforce global text color so labels (checkboxes, small text) follow theme */
* { color: var(--text) !important; }
.stButton>button, .stDownloadButton>button { background-color: var(--card) !important; color: var(--text) !important; border: none !important; }
input[type="text"], textarea, input[type="number"] { background: #0b0d10 !important; color: var(--text) !important; }
pre { background: #0b0d10 !important; color: var(--text) !important; padding: 12px; border-radius:8px; }
/* animate icon only in dark */
#theme-icon { display:inline-block; transform-origin:center; animation: spin-slow 8s linear infinite; opacity:0.95; }
@keyframes spin-slow { from { transform: rotate(0deg);} to { transform: rotate(360deg);} }
"""

LIGHT_CSS = """
:root{
  --bg:#ffffff; --text:#111827; --muted:#6b7280; --card:#f3f4f6; --accent:#2563eb;
}
body, .stApp, .block-container { background: var(--bg) !important; color: var(--text) !important; }
/* enforce global text color in light so labels follow theme */
* { color: var(--text) !important; }
.stButton>button, .stDownloadButton>button { background-color: var(--card) !important; color: var(--text) !important; border: none !important; }
input[type="text"], textarea, input[type="number"] { background: #ffffff !important; color: var(--text) !important; }
pre { background: #f6f7fb !important; color: var(--text) !important; padding: 12px; border-radius:8px; }
/* disable animation in light mode */
#theme-icon { animation: none !important; transform: rotate(0deg) !important; opacity:0.95; }
"""

# Inject CSS matching current theme
css = DARK_CSS if st.session_state["theme"] == "dark" else LIGHT_CSS
st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


RAW FILE
  ↓
extract_text_from_bytes
  ↓
split_into_sections          ← section_segmentation.py
  ↓
assemble_full_schema         ← field_extraction.py
  ↓
normalize_schema             ← normalization.py
  ↓
return JSON
