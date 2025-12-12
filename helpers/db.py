#!/usr/bin/env python3
"""
stores raw file bytes (BLOB) and exposes helpers to save/get records.
"""
import os
import json
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (
    create_engine, Column, Integer, Text, DateTime, String, Boolean, LargeBinary
)

DB_DIR = os.path.join(os.getcwd(), "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "resume_results.db")
SQLITE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False}, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ResumeRecord(Base):
    __tablename__ = "resume_records"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(260), nullable=True)
    parsed_json = Column(Text, nullable=True)
    raw_file = Column(LargeBinary, nullable=True)   # raw uploaded bytes
    status = Column(String(50), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    source = Column(String(50), nullable=True)
    saved = Column(Boolean, default=True)

def init_db():
    """
    Initialize SQLAlchemy tables and the separate hash_cache table used for caching.
    """
    Base.metadata.create_all(bind=engine)

    # create simple hash_cache table for caching parsed outputs
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS hash_cache (
                hash TEXT PRIMARY KEY,
                parsed_json TEXT,
                resume_quality REAL,
                confidence_json TEXT
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print("init_db: failed to create hash_cache table:", e)

def save_parsed_result(filename: str, parsed_obj: Optional[Dict[str, Any]],
                       raw_bytes: Optional[bytes] = None,
                       status: str = "ok", error: str = None, source: str = "api") -> int:
    db = SessionLocal()
    try:
        rec = ResumeRecord(
            filename=filename,
            parsed_json=json.dumps(parsed_obj) if parsed_obj is not None else None,
            raw_file=raw_bytes,
            status=status,
            error=error,
            source=source,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec.id
    finally:
        db.close()

def get_record(record_id: int) -> Optional[Dict[str, Any]]:
    db = SessionLocal()
    try:
        rec = db.query(ResumeRecord).filter(ResumeRecord.id == record_id).first()
        if not rec:
            return None
        return {
            "id": rec.id,
            "filename": rec.filename,
            "parsed": json.loads(rec.parsed_json) if rec.parsed_json else None,
            "status": rec.status,
            "error": rec.error,
            "created_at": rec.created_at.isoformat(),
            "source": rec.source,
        }
    finally:
        db.close()

def get_raw_bytes(record_id: int) -> Optional[bytes]:
    db = SessionLocal()
    try:
        rec = db.query(ResumeRecord).filter(ResumeRecord.id == record_id).first()
        if not rec:
            return None
        return rec.raw_file
    finally:
        db.close()

def list_records(limit: int = 50, offset: int = 0):
    db = SessionLocal()
    try:
        q = db.query(ResumeRecord).order_by(ResumeRecord.created_at.desc()).offset(offset).limit(limit)
        out = []
        for rec in q:
            out.append({
                "id": rec.id,
                "filename": rec.filename,
                "status": rec.status,
                "created_at": rec.created_at.isoformat(),
                "source": rec.source,
            })
        return out
    finally:
        db.close()

def save_hash_cache(hash_value, parsed, resume_score, conf_pct):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO hash_cache(hash, parsed_json, resume_quality, confidence_json)
        VALUES (?, ?, ?, ?)
    """, (hash_value, json.dumps(parsed), float(resume_score or 0.0), json.dumps(conf_pct or {})))
    conn.commit()
    conn.close()

def get_record_by_hash(hash_value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT parsed_json, resume_quality, confidence_json FROM hash_cache WHERE hash = ?", (hash_value,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "parsed": json.loads(row[0]),
        "resume_quality_score": row[1],
        "confidence_percentage": json.loads(row[2]),
    }

def delete_hash_cache():
    """
    Remove all rows from the hash_cache table (clear cache).
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute("DELETE FROM hash_cache")
        conn.commit()
    finally:
        conn.close()

def delete_record(record_id: int) -> bool:
    """
    Delete a ResumeRecord by id. Returns True if deleted, False if not found.
    """
    db = SessionLocal()
    try:
        rec = db.query(ResumeRecord).filter(ResumeRecord.id == record_id).first()
        if not rec:
            return False
        db.delete(rec)
        db.commit()
        return True
    finally:
        db.close()
