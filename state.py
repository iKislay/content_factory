# state.py
import sqlite3
import uuid
import json
from datetime import datetime
from typing import Optional
import config


class PipelineState:
    """SQLite state manager for pipeline runs."""

    def init_db(self) -> None:
        """Create the database and table if not exists."""
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id TEXT PRIMARY KEY,
                topic TEXT,
                scenes_json TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def create_run(self, topic: str) -> str:
        """Insert a new run, returns run_id (uuid4)."""
        run_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO pipeline_runs (run_id, topic, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, topic, "PENDING", now, now)
        )
        conn.commit()
        conn.close()
        return run_id

    def get_pending_run(self) -> Optional[dict]:
        """Returns the most recent non-DONE run."""
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM pipeline_runs WHERE status != 'DONE' ORDER BY created_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    def update_status(self, run_id: str, status: str) -> None:
        """Update run status."""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE pipeline_runs SET status = ?, updated_at = ? WHERE run_id = ?",
            (status, now, run_id)
        )
        conn.commit()
        conn.close()

    def save_scenes(self, run_id: str, scenes: list) -> None:
        """Save JSON scenes to the run."""
        scenes_json = json.dumps(scenes)
        now = datetime.now().isoformat()
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE pipeline_runs SET scenes_json = ?, updated_at = ? WHERE run_id = ?",
            (scenes_json, now, run_id)
        )
        conn.commit()
        conn.close()

    def get_scenes(self, run_id: str) -> list:
        """Retrieve saved scenes."""
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT scenes_json FROM pipeline_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return json.loads(row[0])
        return []

    def mark_done(self, run_id: str) -> None:
        """Set status to DONE."""
        self.update_status(run_id, "DONE")