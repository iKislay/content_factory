from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import json
import os
import threading
import base64
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
    return {"runs": runs}

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
    try:
        state = PipelineState()
        state.init_db()
        orchestrator = OrchestratorAgent(state)
        orchestrator.run(run_id=run_id)
    except Exception as e:
        print(f"Error in pipeline execution: {e}")

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
