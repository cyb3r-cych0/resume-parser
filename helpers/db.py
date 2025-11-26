#!/usr/bin/env python3
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import (
    create_engine, Column, Integer, Text, DateTime, String, Boolean
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# DB file path (project-local)
DB_DIR = os.path.join(os.getcwd(), "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "resume_results.db")
SQLITE_URL = f"sqlite:///{DB_PATH}"

# SQLAlchemy setup
engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False}, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ResumeRecord(Base):
    __tablename__ = "resume_records"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(260), nullable=True)
    parsed_json = Column(Text, nullable=True)   # JSON string
    status = Column(String(50), nullable=True)  # ok / error / exception
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    source = Column(String(50), nullable=True)  # e.g., api, batch, ui
    saved = Column(Boolean, default=True)


def init_db():
    Base.metadata.create_all(bind=engine)


def save_parsed_result(filename: str, parsed_obj: Optional[Dict[str, Any]],
                       status: str = "ok", error: str = None, source: str = "api") -> int:
    """
    Saves parsed JSON object (dict) to DB. Returns record id.
    """
    db = SessionLocal()
    try:
        rec = ResumeRecord(
            filename=filename,
            parsed_json=json.dumps(parsed_obj) if parsed_obj is not None else None,
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
