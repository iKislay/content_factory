# state.py
import sqlite3
import uuid
import json
from datetime import datetime
from typing import Optional, List
import config


class PipelineState:
    """SQLite state manager for pipeline runs."""

    def init_db(self) -> None:
        """Create all database tables if they don't exist."""
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id TEXT PRIMARY KEY,
                topic TEXT,
                scenes_json TEXT,
                image_paths_json TEXT,
                audio_map_json TEXT,
                video_paths_json TEXT,
                final_path TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at TEXT,
                updated_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_messages (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                recipient TEXT,
                msg_type TEXT NOT NULL,
                payload_json TEXT,
                created_at TEXT,
                FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
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

    def get_run_status(self, run_id: str) -> str:
        """Get the current status of a run."""
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM pipeline_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else "PENDING"

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

    def save_image_paths(self, run_id: str, paths: list) -> None:
        """Save image paths to the run."""
        paths_json = json.dumps(paths)
        now = datetime.now().isoformat()
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE pipeline_runs SET image_paths_json = ?, updated_at = ? WHERE run_id = ?",
            (paths_json, now, run_id)
        )
        conn.commit()
        conn.close()

    def get_image_paths(self, run_id: str) -> list:
        """Retrieve saved image paths."""
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT image_paths_json FROM pipeline_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return json.loads(row[0])
        return []

    def save_audio_map(self, run_id: str, audio_map: dict) -> None:
        """Save audio map to the run."""
        audio_json = json.dumps(audio_map)
        now = datetime.now().isoformat()
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE pipeline_runs SET audio_map_json = ?, updated_at = ? WHERE run_id = ?",
            (audio_json, now, run_id)
        )
        conn.commit()
        conn.close()

    def get_audio_map(self, run_id: str) -> dict:
        """Retrieve saved audio map, with keys normalized to integers."""
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT audio_map_json FROM pipeline_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            loaded = json.loads(row[0])
            return {int(k): v for k, v in loaded.items()}
        return {}

    def save_video_paths(self, run_id: str, paths: list) -> None:
        """Save video paths to the run."""
        paths_json = json.dumps(paths)
        now = datetime.now().isoformat()
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE pipeline_runs SET video_paths_json = ?, updated_at = ? WHERE run_id = ?",
            (paths_json, now, run_id)
        )
        conn.commit()
        conn.close()

    def get_video_paths(self, run_id: str) -> list:
        """Retrieve saved video paths."""
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT video_paths_json FROM pipeline_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return json.loads(row[0])
        return []

    def save_final_path(self, run_id: str, path: str) -> None:
        """Save final video path to the run."""
        now = datetime.now().isoformat()
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE pipeline_runs SET final_path = ?, updated_at = ? WHERE run_id = ?",
            (path, now, run_id)
        )
        conn.commit()
        conn.close()

    def get_final_path(self, run_id: str) -> str:
        """Retrieve final video path."""
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT final_path FROM pipeline_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else ""

    def mark_done(self, run_id: str) -> None:
        """Set status to DONE."""
        self.update_status(run_id, "DONE")

    # ─── Agent Message Bus ────────────────────────────────────────────────────

    def post_message(
        self,
        run_id: str,
        sender: str,
        msg_type: str,
        payload: dict,
        recipient: Optional[str] = None,
    ) -> str:
        """Post a message to the agent blackboard. Returns message id."""
        msg_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        payload_json = json.dumps(payload)
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO agent_messages
               (id, run_id, sender, recipient, msg_type, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, run_id, sender, recipient, msg_type, payload_json, now),
        )
        conn.commit()
        conn.close()
        return msg_id

    def log_handoff(
        self,
        run_id: str,
        from_agent: str,
        to_agent: str,
        payload: dict,
        metadata: Optional[dict] = None
    ) -> str:
        """
        Log an agent-to-agent handoff with payload details.
        
        This makes the data flow between agents explicit and traceable.
        """
        msg_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        handoff_payload = {
            "from_agent": from_agent,
            "to_agent": to_agent,
            "payload_keys": list(payload.keys()) if payload else [],
            "payload_summary": self._summarize_payload(payload),
            "metadata": metadata or {},
            "handoff_time": now
        }
        
        payload_json = json.dumps(handoff_payload)
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO agent_messages
               (id, run_id, sender, recipient, msg_type, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, run_id, from_agent, to_agent, "HANDOFF", payload_json, now),
        )
        conn.commit()
        conn.close()
        return msg_id

    def _summarize_payload(self, payload: dict) -> dict:
        """Create a summary of payload for logging."""
        summary = {}
        for key, value in payload.items():
            if isinstance(value, str):
                summary[key] = value[:100] + "..." if len(value) > 100 else value
            elif isinstance(value, list):
                summary[key] = f"[{len(value)} items]"
            elif isinstance(value, dict):
                summary[key] = f"{{{len(value)} keys}}"
            else:
                summary[key] = str(type(value).__name__)
        return summary

    def get_handoffs(self, run_id: str) -> List[dict]:
        """Get all handoff logs for a run."""
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM agent_messages
               WHERE run_id = ? AND msg_type = 'HANDOFF'
               ORDER BY created_at ASC""",
            (run_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        result = []
        for row in rows:
            d = dict(row)
            if d.get("payload_json"):
                d["payload"] = json.loads(d["payload_json"])
            result.append(d)
        return result

    def get_messages(
        self, run_id: str, msg_type: Optional[str] = None
    ) -> List[dict]:
        """Retrieve all messages for a run, optionally filtered by type."""
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if msg_type:
            cursor.execute(
                """SELECT * FROM agent_messages
                   WHERE run_id = ? AND msg_type = ?
                   ORDER BY created_at ASC""",
                (run_id, msg_type),
            )
        else:
            cursor.execute(
                """SELECT * FROM agent_messages
                   WHERE run_id = ? ORDER BY created_at ASC""",
                (run_id,),
            )
        rows = cursor.fetchall()
        conn.close()
        result = []
        for row in rows:
            d = dict(row)
            if d.get("payload_json"):
                d["payload"] = json.loads(d["payload_json"])
            else:
                d["payload"] = {}
            result.append(d)
        return result

    def get_latest_message(self, run_id: str, msg_type: str) -> Optional[dict]:
        """Return the most recent message of a given type for a run."""
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM agent_messages
               WHERE run_id = ? AND msg_type = ?
               ORDER BY created_at DESC LIMIT 1""",
            (run_id, msg_type),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            d = dict(row)
            if d.get("payload_json"):
                d["payload"] = json.loads(d["payload_json"])
            else:
                d["payload"] = {}
            return d
        return None