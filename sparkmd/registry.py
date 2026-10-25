"""Shared SQLite registry. All writers use Registry.transaction()/the same RLock."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
 patient_id TEXT PRIMARY KEY, cohort TEXT NOT NULL DEFAULT 'unknown', sex TEXT, birth_year INTEGER
);
CREATE TABLE IF NOT EXISTS studies (
 study_uid TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(patient_id),
 study_date TEXT, rank INTEGER, timepoint TEXT, day_offset INTEGER,
 day_offset_source TEXT NOT NULL DEFAULT 'none', inbox_path TEXT, failure_reason TEXT,
 status TEXT NOT NULL DEFAULT 'received', priority TEXT NOT NULL DEFAULT 'routine',
 priority_reason TEXT, received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS series (
 series_uid TEXT PRIMARY KEY, study_uid TEXT NOT NULL REFERENCES studies(study_uid) ON DELETE CASCADE,
 modality TEXT, series_number INTEGER, kernel TEXT, kernel_list TEXT, slice_thickness REAL,
 n_instances INTEGER, image_type TEXT, axial INTEGER NOT NULL DEFAULT 0, path TEXT,
 eligible INTEGER NOT NULL DEFAULT 0, eligible_reason TEXT, fallback INTEGER NOT NULL DEFAULT 0,
 selected INTEGER NOT NULL DEFAULT 0, select_reason TEXT
);
CREATE TABLE IF NOT EXISTS tracks (
 track_id TEXT PRIMARY KEY, patient_id TEXT REFERENCES patients(patient_id),
 first_study_uid TEXT REFERENCES studies(study_uid) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS nodules (
 nodule_id TEXT PRIMARY KEY, study_uid TEXT NOT NULL REFERENCES studies(study_uid) ON DELETE CASCADE,
 series_uid TEXT REFERENCES series(series_uid) ON DELETE CASCADE, track_id TEXT REFERENCES tracks(track_id),
 lobe TEXT, center_mm TEXT, long_mm REAL, short_mm REAL, mean_mm REAL, volume_mm3 REAL,
 proposed_long_mm REAL, proposed_short_mm REAL, proposed_mean_mm REAL, proposal_source TEXT,
 box_mean_mm REAL, confirmed_by TEXT, confirmed_at TEXT, edited INTEGER NOT NULL DEFAULT 0,
 mean_hu REAL, type TEXT NOT NULL DEFAULT 'solid', det_score REAL
);
CREATE TABLE IF NOT EXISTS assessments (
 study_uid TEXT PRIMARY KEY REFERENCES studies(study_uid) ON DELETE CASCADE,
 lung_rads TEXT, rule_id TEXT, driver_nodule_id TEXT, management TEXT, growth_json TEXT,
 rules_version TEXT
);
CREATE TABLE IF NOT EXISTS extras (
 study_uid TEXT PRIMARY KEY REFERENCES studies(study_uid) ON DELETE CASCADE,
 emphysema_pct REAL, vertebra_label TEXT, vertebra_hu REAL, cac_json TEXT
);
CREATE TABLE IF NOT EXISTS reports (
 report_id TEXT PRIMARY KEY, study_uid TEXT NOT NULL REFERENCES studies(study_uid) ON DELETE CASCADE,
 kind TEXT NOT NULL, markdown TEXT NOT NULL, version INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft', approved_by TEXT, approved_at TEXT,
 UNIQUE(study_uid, kind, version)
);
CREATE TABLE IF NOT EXISTS agent_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, study_uid TEXT,
 source TEXT NOT NULL, message TEXT NOT NULL, payload_json TEXT
);
CREATE TABLE IF NOT EXISTS outbox (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
 report_id TEXT NOT NULL UNIQUE REFERENCES reports(report_id) ON DELETE CASCADE,
 recipient TEXT, payload_json TEXT
);
CREATE INDEX IF NOT EXISTS studies_patient_rank ON studies(patient_id, rank);
CREATE INDEX IF NOT EXISTS nodules_study ON nodules(study_uid);
CREATE INDEX IF NOT EXISTS agent_events_study ON agent_events(study_uid, id);
"""


class Registry:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.environ.get('SPARKMD_DB', str(Path(os.environ.get('SPARKMD_HOME', '/srv/spark-md')) / 'registry.sqlite')))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript(SCHEMA)
        self.db.commit()

    @contextmanager
    def transaction(self):
        with self.lock:
            try:
                yield self.db
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def one(self, sql: str, params=()):
        with self.lock:
            row = self.db.execute(sql, params).fetchone()
            return dict(row) if row is not None else None

    def all(self, sql: str, params=()):
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, params).fetchall()]

    def close(self):
        with self.lock:
            self.db.close()
