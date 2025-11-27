#!/usr/bin/env python3
"""
Run this once (from project root, in the env)
This creates data/resume_results.db.
"""
from helpers.db import init_db
init_db()
print("DB initialized at data/resume_results.db")
