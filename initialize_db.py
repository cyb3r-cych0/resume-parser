#!/usr/bin/env python3
"""
Run this once (from project root, in the env)
This creates database/parsed_resumes.db.
"""
from helpers.db import init_db
init_db()
print("DB initialized at database/parsed_resumes.db")
