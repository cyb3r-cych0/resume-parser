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