# SQLite Persistence

Add a local SQLite persistence layer using SQLAlchemy (lightweight, offline, no external DB):

- create helpers/db.py (engine, models, helpers)
- update api.py to optionally save parse results (?save=true) and add endpoints to list / fetch saved results
- show how to initialize DB and test
- Everything stays local (file data/resume_results.db).

**How to test persistence**

1. Initialize DB

    Run once:

    `python initialize_db.py`

    - Ensure DB initialized.

2. Start backend:

    `uvicorn api:app --reload`

3. Health Check 

    `curl http://127.0.0.1:8000/health`

4. Parse a file and save:

    `curl -F "file=@/path/resume.pdf" "http://127.0.0.1:8000/parse?save=true"`

    - Response includes "db_id": <int>.

5. List records:

    `curl "http://127.0.0.1:8000/records?limit=10"`

6. Fetch saved record by id:

    `curl "http://127.0.0.1:8000/records/1"`

7. Parallel batch test (2+ files)

    `curl -F "files=@/full/path/to/sample_resume.pdf" -F "files=@/full/path/to/sample_resume2.docx" "http://127.0.0.1:8000/parse/batch"`

# Future Enhancements

**RoadMap**

- Show selected record in main area (not only sidebar).
- Add search/filter by filename or date in the sidebar.
- Add "Re-run parsing for this record" button (reparse stored file).
- Add export CSV of selected records.

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