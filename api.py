from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import json
import os
import threading
import base64
from datetime import datetime
from typing import List, Optional, Dict, Any

import config
from state import PipelineState
from agents.orchestrator import OrchestratorAgent

app = FastAPI(title="Content Factory API")

# Allow CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "state.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def parse_json(json_str: str) -> Optional[Any]:
    if not json_str:
        return None
    try:
        return json.loads(json_str)
    except:
        return None

class RunRequest(BaseModel):
    topic: str
    auto_approve: bool = False

@app.get("/api/runs")
def get_all_runs():
    conn = get_db_connection()
    cursor = conn.execute("SELECT * FROM pipeline_runs ORDER BY created_at DESC")
    runs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    for run in runs:
        run['status_label'] = _get_status_label(run['status'])
        run['is_running'] = run['status'] not in ("DONE", "CANCELLED", "FAILED")
        run['time_ago'] = _time_ago(run.get('created_at', ''))
    return {"runs": runs}

def _get_status_label(status: str) -> str:
    status_map = {
        "PENDING": "Pending",
        "TOPIC_AWAITING_APPROVAL": "Awaiting Topic Approval",
        "TOPIC_FOUND": "Topic Selected",
        "RESEARCHED": "Researching",
        "PLANNED": "Planning",
        "AWAITING_CRITIC": "Pending Review",
        "NARRATED": "Script Ready",
        "VISUALS_DONE": "Generating Visuals",
        "AUDIO_DONE": "Generating Audio",
        "ANIMATED": "Animating",
        "COMPILED": "Compiling",
        "DONE": "Completed",
        "CANCELLED": "Cancelled",
        "FAILED": "Failed",
    }
    return status_map.get(status, status)

def _time_ago(dt_str: str) -> str:
    """Convert ISO datetime to human-readable relative time."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        now = datetime.now()
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            mins = seconds // 60
            return f"{mins} min{'s' if mins > 1 else ''} ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif seconds < 604800:
            days = seconds // 86400
            return f"{days} day{'s' if days > 1 else ''} ago"
        else:
            return dt.strftime("%b %d, %Y")
    except:
        return dt_str

@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    conn = get_db_connection()
    cursor = conn.execute("SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,))
    run = cursor.fetchone()
    conn.close()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    run_dict = dict(run)
    run_dict['image_paths'] = parse_json(run_dict.get('image_paths_json', '[]'))
    run_dict['audio_map'] = parse_json(run_dict.get('audio_map_json', '{}'))
    run_dict['status_label'] = _get_status_label(run_dict['status'])
    run_dict['is_running'] = run_dict['status'] not in ("DONE", "CANCELLED", "FAILED")
    run_dict['time_ago'] = _time_ago(run_dict.get('created_at', ''))
    return run_dict

@app.get("/api/runs/{run_id}/images")
def get_run_images(run_id: str):
    conn = get_db_connection()
    cursor = conn.execute("SELECT image_paths_json FROM pipeline_runs WHERE run_id = ?", (run_id,))
    run = cursor.fetchone()
    conn.close()
    
    if not run or not run['image_paths_json']:
        return {"images": []}
    
    image_paths = parse_json(run['image_paths_json']) or []
    images = []
    for path in image_paths:
        if os.path.exists(path):
            with open(path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
                images.append({"path": path, "data": encoded})
    return {"images": images}

@app.get("/api/runs/{run_id}/messages")
def get_run_messages(run_id: str, msg_type: Optional[str] = None):
    conn = get_db_connection()
    
    if msg_type:
        cursor = conn.execute(
            "SELECT * FROM agent_messages WHERE run_id = ? AND msg_type = ? ORDER BY created_at ASC",
            (run_id, msg_type)
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM agent_messages WHERE run_id = ? ORDER BY created_at ASC",
            (run_id,)
        )
    
    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Parse payload json for convenience
    for msg in messages:
        msg['payload'] = parse_json(msg.get('payload_json')) or {}
        msg['receiver'] = msg.get('recipient', '')  # alias for frontend
        
    return {"messages": messages}

@app.get("/api/stats")
def get_stats():
    conn = get_db_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
        completed = conn.execute("SELECT COUNT(*) FROM pipeline_runs WHERE status = 'DONE'").fetchone()[0]
        
        quality_scores = conn.execute("SELECT payload_json FROM agent_messages WHERE msg_type = 'RESEARCH_COMPLETE'").fetchall()
        avg_quality = 0
        if quality_scores:
            scores = []
            for row in quality_scores:
                try:
                    payload = json.loads(row[0])
                    if 'quality' in payload and 'score' in payload['quality']:
                        scores.append(payload['quality']['score'])
                except:
                    pass
            if scores:
                avg_quality = sum(scores) / len(scores)
        
        return {
            "total_runs": total, 
            "completed_runs": completed, 
            "success_rate": (completed / total * 100) if total > 0 else 0, 
            "avg_quality": round(avg_quality, 1)
        }
    except Exception as e:
        return {
            "total_runs": 0, 
            "completed_runs": 0, 
            "success_rate": 0, 
            "avg_quality": 0,
            "error": str(e)
        }
    finally:
        conn.close()

def run_pipeline_task(run_id: str, auto_approve: bool):
    state = PipelineState()
    try:
        state.init_db()
        orchestrator = OrchestratorAgent(state)
        result = orchestrator.run(run_id=run_id, auto_approve=auto_approve)
        if not result.success:
            state.update_status(run_id, "FAILED")
    except Exception as e:
        print(f"Error in pipeline execution: {e}")
        try:
            state.update_status(run_id, "FAILED")
        except:
            pass

@app.post("/api/runs")
def start_run(req: RunRequest, background_tasks: BackgroundTasks):
    state = PipelineState()
    state.init_db()
    run_id = state.create_run(req.topic)
    
    # Run in background
    thread = threading.Thread(target=run_pipeline_task, args=(run_id, req.auto_approve))
    thread.daemon = True
    thread.start()
    
    return {"run_id": run_id, "status": "PENDING", "topic": req.topic}

# Endpoints for human-in-the-loop interactions

class ApprovalRequest(BaseModel):
    action: str  # "approve" or "reject"
    feedback: Optional[str] = None
    selected_topic: Optional[str] = None

@app.post("/api/runs/{run_id}/approve")
def approve_step(run_id: str, req: ApprovalRequest):
    conn = get_db_connection()
    payload = json.dumps({"action": req.action, "feedback": req.feedback, "selected_topic": req.selected_topic})
    
    conn.execute(
        "INSERT INTO agent_messages (run_id, msg_type, sender, recipient, payload_json) VALUES (?, ?, ?, ?, ?)",
        (run_id, "USER_INPUT", "USER", "ORCHESTRATOR", payload)
    )
    conn.commit()
    conn.close()
    
    return {"status": "ok", "message": "Feedback submitted"}

@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str):
    conn = get_db_connection()
    cursor = conn.execute("SELECT status FROM pipeline_runs WHERE run_id = ?", (run_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Run not found")
    
    current_status = row[0]
    if current_status in ("DONE", "CANCELLED", "FAILED"):
        conn.close()
        return {"status": "ok", "message": f"Run is already {current_status.lower()}"}
    
    conn.execute("UPDATE pipeline_runs SET status = 'CANCELLED', updated_at = ? WHERE run_id = ?",
                 (datetime.now().isoformat(), run_id))
    conn.commit()
    conn.close()
    
    return {"status": "ok", "message": "Run cancelled"}

@app.post("/api/runs/{run_id}/retry")
def retry_run(run_id: str, background_tasks: BackgroundTasks):
    conn = get_db_connection()
    cursor = conn.execute("SELECT status, topic FROM pipeline_runs WHERE run_id = ?", (run_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Run not found")
    
    current_status, topic = row[0], row[1]
    if current_status not in ("DONE", "CANCELLED", "FAILED"):
        conn.close()
        return {"status": "error", "message": f"Cannot retry - run is {current_status}"}
    
    new_run_id = f"{run_id}-retry-{datetime.now().strftime('%H%M%S')}"
    conn.execute(
        "INSERT INTO pipeline_runs (run_id, topic, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (new_run_id, topic, "PENDING", datetime.now().isoformat(), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    
    thread = threading.Thread(target=run_pipeline_task, args=(new_run_id, False))
    thread.daemon = True
    thread.start()
    
    return {"run_id": new_run_id, "status": "PENDING", "topic": topic}

@app.delete("/api/runs")
def delete_all_runs():
    conn = get_db_connection()
    conn.execute("DELETE FROM agent_messages")
    conn.execute("DELETE FROM pipeline_runs")
    conn.commit()
    conn.close()
    return {"status": "ok", "message": "All runs deleted"}
