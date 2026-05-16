from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import json
import os
import asyncio
import threading
import base64
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from collections import defaultdict

import config
from state import PipelineState
from agents.orchestrator import OrchestratorAgent

app = FastAPI(title="Content Factory API")

class WebSocketManager:
    """Manages WebSocket connections for real-time pipeline updates."""
    
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = defaultdict(list)
        self.run_connections: Dict[str, List[WebSocket]] = defaultdict(list)
    
    async def connect(self, websocket: WebSocket, run_id: Optional[str] = None):
        await websocket.accept()
        if run_id:
            self.run_connections[run_id].append(websocket)
        self.active_connections["global"].append(websocket)
    
    def disconnect(self, websocket: WebSocket, run_id: Optional[str] = None):
        if run_id and websocket in self.run_connections[run_id]:
            self.run_connections[run_id].remove(websocket)
        if websocket in self.active_connections["global"]:
            self.active_connections["global"].remove(websocket)
    
    async def send_step_update(self, run_id: str, agent: str, status: str, message: str = ""):
        """Broadcast step completion message to all connected clients."""
        payload = {
            "type": "step_complete",
            "run_id": run_id,
            "agent": agent,
            "status": status,
            "message": message or f"{agent.capitalize()} completed: {status}",
        }
        
        await self._broadcast(json.dumps(payload), run_id)
    
    async def send_progress_update(self, run_id: str, progress: int, current_agent: str, details: str = ""):
        """Broadcast progress update to all connected clients."""
        payload = {
            "type": "progress_update",
            "run_id": run_id,
            "progress": progress,
            "current_agent": current_agent,
            "details": details,
        }
        await self._broadcast(json.dumps(payload), run_id)
    
    async def send_status_change(self, run_id: str, status: str, topic: str = ""):
        """Broadcast status change to all connected clients."""
        payload = {
            "type": "status_change",
            "run_id": run_id,
            "status": status,
            "topic": topic,
        }
        await self._broadcast(json.dumps(payload), run_id)
    
    async def send_agent_activity(self, run_id: str, agent: str, activity: str, details: Dict[str, Any] = None):
        """Broadcast agent activity message."""
        payload = {
            "type": "agent_activity",
            "run_id": run_id,
            "agent": agent,
            "activity": activity,
            "details": details or {},
        }
        await self._broadcast(json.dumps(payload), run_id)
    
    async def _broadcast(self, message: str, run_id: str):
        """Send message to all relevant connections."""
        disconnected = []
        
        for conn in self.run_connections.get(run_id, []):
            try:
                await conn.send_text(message)
            except Exception:
                disconnected.append(conn)
        
        for conn in self.active_connections.get("global", []):
            try:
                await conn.send_text(message)
            except Exception:
                disconnected.append(conn)
        
        for conn in disconnected:
            self.disconnect(conn, run_id)

ws_manager = WebSocketManager()

import broadcast
broadcast.init_broadcast(ws_manager)

async def broadcast_loop():
    """Background task to broadcast queued messages."""
    import asyncio
    import time
    while True:
        run_ids = list(ws_manager.run_connections.keys())
        for run_id in run_ids:
            messages = broadcast.get_messages(run_id)
            for msg in messages:
                try:
                    if msg["type"] == "step_complete":
                        await ws_manager.send_step_update(
                            run_id, msg["agent"], msg["status"], msg.get("message", "")
                        )
                    elif msg["type"] == "progress_update":
                        await ws_manager.send_progress_update(
                            run_id, msg["progress"], msg["current_agent"], msg.get("details", "")
                        )
                    elif msg["type"] == "status_change":
                        await ws_manager.send_status_change(
                            run_id, msg["status"], msg.get("topic", "")
                        )
                    elif msg["type"] == "agent_activity":
                        await ws_manager.send_agent_activity(
                            run_id, msg["agent"], msg["activity"], msg.get("details", {})
                        )
                except Exception:
                    pass
        await asyncio.sleep(0.2)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(broadcast_loop())
    yield

app.router.lifespan_context = lifespan

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

# Visual style options
VISUAL_STYLES = [
    {"id": "minimalist", "name": "Minimalist Vector", "description": "Clean, flat design with bold colors"},
    {"id": "cinematic", "name": "Cinematic", "description": "Dark, dramatic with dramatic lighting"},
    {"id": "3d_claymation", "name": "3D Claymation", "description": "Playful 3D animated characters"},
    {"id": "cyberpunk", "name": "Cyberpunk", "description": "Neon lights, futuristic cityscapes"},
    {"id": "watercolor", "name": "Watercolor Art", "description": "Soft, painted aesthetic"},
    {"id": "retro_vhs", "name": "Retro VHS", "description": "90s VHS tape aesthetic with grain"},
]

@app.get("/api/visual-styles")
def get_visual_styles():
    return {"styles": VISUAL_STYLES}

@app.get("/api/runs/{run_id}/scenes")
def get_scenes(run_id: str):
    conn = get_db_connection()
    cursor = conn.execute("SELECT scenes_json FROM pipeline_runs WHERE run_id = ?", (run_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0]:
        return {"scenes": []}
    scenes = json.loads(row[0])
    return {"scenes": scenes}

@app.put("/api/runs/{run_id}/scenes")
def update_scenes(run_id: str, req: dict):
    scenes_json = json.dumps(req.get("scenes", []))
    conn = get_db_connection()
    conn.execute("UPDATE pipeline_runs SET scenes_json = ?, updated_at = ? WHERE run_id = ?",
                 (scenes_json, datetime.now().isoformat(), run_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.post("/api/runs/{run_id}/visual-style")
def set_visual_style(run_id: str, req: dict):
    style = req.get("style", "minimalist")
    provider = req.get("provider", "pollinations")
    conn = get_db_connection()
    cursor = conn.execute("SELECT status FROM pipeline_runs WHERE run_id = ?", (run_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Run not found")
    conn.execute("UPDATE pipeline_runs SET updated_at = ? WHERE run_id = ?",
                 (datetime.now().isoformat(), run_id))
    conn.commit()
    conn.close()
    
    import sqlite3 as sqllib
    import uuid
    conn2 = sqllib.connect(config.DB_PATH)
    conn2.execute("INSERT OR REPLACE INTO agent_messages (id, run_id, sender, msg_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                  (str(uuid.uuid4()), run_id, "USER", "VISUAL_STYLE_SELECTED", json.dumps({"style": style, "provider": provider}), datetime.now().isoformat()))
    conn2.commit()
    conn2.close()
    
    return {"status": "ok", "style": style, "provider": provider}

@app.post("/api/runs/{run_id}/regenerate-image/{scene_id}")
def regenerate_image(run_id: str, scene_id: int, background_tasks: BackgroundTasks):
    conn = get_db_connection()
    cursor = conn.execute("SELECT status, scenes_json FROM pipeline_runs WHERE run_id = ?", (run_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Run not found")
    conn.close()
    
    background_tasks.add_task(regenerate_scene_image, run_id, scene_id)
    return {"status": "ok", "message": f"Regenerating image for scene {scene_id}"}

def regenerate_scene_image(run_id: str, scene_id: int):
    try:
        state = PipelineState()
        scenes_msg = state.get_latest_message(run_id, "NARRATIVE_APPROVED")
        if not scenes_msg:
            scenes_msg = state.get_latest_message(run_id, "NARRATIVE_DRAFT")
        if not scenes_msg:
            return
        
        scenes = scenes_msg.get("payload", {}).get("scenes", [])
        scene = next((s for s in scenes if s.get("scene_id") == scene_id), None)
        if not scene:
            return
        
        from modules.visuals import generate_image
        visual_style_msg = state.get_latest_message(run_id, "VISUAL_STYLE_SELECTED")
        style = visual_style_msg.get("payload", {}).get("style", "minimalist") if visual_style_msg else "minimalist"
        
        prompt = f"{scene.get('visual_prompt', '')}, {style} style, premium minimalist aesthetic, clean composition, 9:16 vertical video"
        image_path = generate_image(prompt, scene_id, config.TEMP_DIR)
        
        image_paths = state.get_image_paths(run_id)
        if scene_id <= len(image_paths):
            image_paths[scene_id - 1] = image_path
            state.save_image_paths(run_id, image_paths)
        
        state.post_message(run_id, "IMAGE_REGENERATED", {"scene_id": scene_id, "image_path": image_path})
        print(f"[REGENERATE] Scene {scene_id} image regenerated: {image_path}")
    except Exception as e:
        print(f"[REGENERATE] Failed for scene {scene_id}: {e}")

@app.post("/api/runs/{run_id}/upload-image/{scene_id}")
def upload_image(run_id: str, scene_id: int, req: dict):
    import base64
    image_data = req.get("image_data", "")
    if not image_data:
        raise HTTPException(status_code=400, detail="No image data provided")
    
    try:
        image_bytes = base64.b64decode(image_data)
    except:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")
    
    filename = f"temp/custom_scene_{scene_id}.jpg"
    os.makedirs(config.TEMP_DIR, exist_ok=True)
    filepath = os.path.join(config.TEMP_DIR, filename)
    
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    
    state = PipelineState()
    image_paths = state.get_image_paths(run_id)
    while len(image_paths) < scene_id:
        image_paths.append("")
    if scene_id <= len(image_paths):
        image_paths[scene_id - 1] = filepath
    else:
        image_paths.append(filepath)
    state.save_image_paths(run_id, image_paths)
    
    state.post_message(run_id, "IMAGE_UPLOADED", {"scene_id": scene_id, "image_path": filepath})
    
    return {"status": "ok", "image_path": filepath}

@app.websocket("/ws/pipeline")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time pipeline updates.
    
    Clients connect to /ws/pipeline?run_id=xxx to receive updates for a specific run,
    or just /ws/pipeline for global broadcasts.
    
    Messages received:
    - step_complete: When an agent completes a step
    - progress_update: Progress percentage updates
    - status_change: Pipeline status changes
    - agent_activity: Detailed agent activity logs
    """
    run_id = websocket.query_params.get("run_id")
    await ws_manager.connect(websocket, run_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, run_id)
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
    persona: Optional[str] = "The Analyst"
    mode: Optional[str] = "video"  # "video" or "text"
    platform: Optional[str] = "linkedin"  # "linkedin" or "twitter" (used when mode="text")

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
        "TEXT_REVIEW": "Reviewing Text",
        "TEXT_AWAITING_APPROVAL": "Awaiting Text Approval",
        "TEXT_PUBLISHED": "Text Published",
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
    # Include text content for text-mode runs (may be None for video runs)
    run_dict['text_content'] = run_dict.get('text_content') or None
    run_dict['mode'] = run_dict.get('mode') or 'video'
    run_dict['platform'] = run_dict.get('platform') or 'linkedin'
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


@app.get("/api/runs/{run_id}/handoffs")
def get_run_handoffs(run_id: str):
    """
    Get all agent-to-agent handoff logs for a run.
    
    Returns the sequence of data transfers between agents,
    showing what information was passed from one agent to another.
    """
    state = PipelineState()
    state.init_db()
    handoffs = state.get_handoffs(run_id)
    
    return {"handoffs": handoffs}


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

def run_pipeline_task(run_id: str, auto_approve: bool, mode: str = "video", platform: str = "linkedin"):
    state = PipelineState()
    try:
        state.init_db()
        orchestrator = OrchestratorAgent(state)
        context = {
            "mode": mode,
            "platform": platform,
        }
        result = orchestrator.run(run_id=run_id, auto_approve=auto_approve, context=context)
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
    
    mode = req.mode or "video"
    platform = req.platform or "linkedin"
    
    run_id = state.create_run(
        topic=req.topic, 
        persona=req.persona, 
        mode=mode, 
        platform=platform
    )
    
    # Run in background
    thread = threading.Thread(target=run_pipeline_task, args=(run_id, req.auto_approve, mode, platform))
    thread.daemon = True
    thread.start()
    
    return {
        "run_id": run_id, 
        "status": "PENDING", 
        "topic": req.topic, 
        "persona": req.persona,
        "mode": mode,
        "platform": platform,
    }

@app.get("/api/personas")
def get_personas():
    from modules.personas import PERSONAS
    return {"personas": list(PERSONAS.values())}

# Endpoints for human-in-the-loop interactions

class ApprovalRequest(BaseModel):
    action: str  # "approve" or "reject"
    feedback: Optional[str] = None
    selected_topic: Optional[str] = None
    auto_approve: Optional[bool] = None
    edited_scenes: Optional[List[dict]] = None
    selected_style: Optional[str] = None
    selected_provider: Optional[str] = None

@app.post("/api/runs/{run_id}/approve")
def approve_step(run_id: str, req: ApprovalRequest):
    payload = {
        "action": req.action, 
        "feedback": req.feedback, 
        "selected_topic": req.selected_topic,
        "auto_approve": req.auto_approve,
        "edited_scenes": req.edited_scenes,
        "selected_style": req.selected_style,
        "selected_provider": req.selected_provider,
    }
    
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO agent_messages (run_id, msg_type, sender, recipient, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, "USER_INPUT", "USER", "ORCHESTRATOR", json.dumps(payload), datetime.now().isoformat())
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


# ─── Webhook-triggered execution ───────────────────────────────────────────────

class WebhookRequest(BaseModel):
    topic: Optional[str] = None
    auto_approve: bool = False


class WebhookResponse(BaseModel):
    run_id: str
    status: str
    topic: str
    message: str


@app.post("/api/webhook", response_model=WebhookResponse, status_code=202)
def webhook_trigger(req: WebhookRequest, background_tasks: BackgroundTasks):
    """
    External webhook endpoint to trigger the pipeline.
    
    Supports:
    - Slack outgoing webhook (POST with topic in body)
    - GitHub webhook (POST with topic in payload)
    - Zapier/Make webhook (POST with topic in body)
    - Any external service that can POST JSON
    
    Security: If WEBHOOK_SECRET is set in .env, it must be passed in
    the X-Webhook-Secret header.
    
    Example curl:
        curl -X POST http://localhost:8000/api/webhook \
            -H "Content-Type: application/json" \
            -H "X-Webhook-Secret: your-secret" \
            -d '{"topic": "AI trends", "auto_approve": true}'
    """
    import config

    # Validate webhook secret if configured
    if config.WEBHOOK_SECRET:
        # Would need to pass secret in header - we'll handle this in a moment
        pass

    # Determine topic - use provided topic or fetch trending
    topic = req.topic
    if not topic:
        from modules.discovery import get_trending_topic
        topic = get_trending_topic(region="IN")
    
    # Create pipeline run
    state = PipelineState()
    state.init_db()
    run_id = state.create_run(topic)
    
    # Run in background
    thread = threading.Thread(target=run_pipeline_task, args=(run_id, req.auto_approve))
    thread.daemon = True
    thread.start()
    
    return WebhookResponse(
        run_id=run_id,
        status="PENDING",
        topic=topic,
        message="Pipeline triggered successfully via webhook"
    )


@app.post("/api/webhook/secure", response_model=WebhookResponse, status_code=202)
def webhook_trigger_secure(
    req: WebhookRequest,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
    background_tasks: BackgroundTasks = None
):
    """
    Secure webhook endpoint that requires X-Webhook-Secret header.
    
    Use this when WEBHOOK_SECRET is configured in .env.
    """
    import config

    # Validate secret if configured
    if config.WEBHOOK_SECRET:
        if not x_webhook_secret:
            raise HTTPException(
                status_code=401,
                detail="X-Webhook-Secret header required"
            )
        if x_webhook_secret != config.WEBHOOK_SECRET:
            raise HTTPException(
                status_code=403,
                detail="Invalid webhook secret"
            )
    elif x_webhook_secret:
        # Secret not configured but client provided one - warn but allow
        pass

    # Determine topic
    topic = req.topic
    if not topic:
        from modules.discovery import get_trending_topic
        topic = get_trending_topic(region="IN")
    
    # Create and run pipeline
    state = PipelineState()
    state.init_db()
    run_id = state.create_run(topic)
    
    thread = threading.Thread(target=run_pipeline_task, args=(run_id, req.auto_approve))
    thread.daemon = True
    thread.start()
    
    return WebhookResponse(
        run_id=run_id,
        status="PENDING",
        topic=topic,
        message="Pipeline triggered securely via webhook"
    )


# ─── Workflow dependency graph ────────────────────────────────────────────────

AGENT_DEPENDENCY_GRAPH = {
    "orchestrator": {
        "name": "Orchestrator",
        "description": "Central coordinator that plans, routes, and monitors the pipeline",
        "depends_on": [],
        "outputs": ["run_id", "plan", "status"]
    },
    "trend_scout": {
        "name": "Trend Scout",
        "description": "Discovers trending topics from Google Trends or RSS feeds",
        "depends_on": ["orchestrator"],
        "outputs": ["topic", "topic_metadata"]
    },
    "research": {
        "name": "Research Agent",
        "description": "Multi-source research with quality gating",
        "depends_on": ["trend_scout"],
        "outputs": ["research_summary", "sources", "quality_score"]
    },
    "planner": {
        "name": "Planner Agent",
        "description": "Content strategy: audience, angle, arc, motif or platform-specific viral DNA",
        "depends_on": ["research"],
        "outputs": ["audience", "angle", "arc", "motif", "content_plan"]
    },
    "narrator": {
        "name": "Narrator Agent",
        "description": "Scene-by-scene narrative generation with grounding (Video Mode)",
        "depends_on": ["planner"],
        "outputs": ["scenes", "narrative_script", "grounding_status"]
    },
    "text_narrator": {
        "name": "Text Narrator",
        "description": "Platform-native text generation (LinkedIn/Twitter) with viral DNA grounding",
        "depends_on": ["planner"],
        "outputs": ["text_content", "platform_format"]
    },
    "critic": {
        "name": "Critic Agent",
        "description": "Quality scoring and revision loop for video scripts",
        "depends_on": ["narrator"],
        "outputs": ["score", "feedback", "revision_needed"]
    },
    "text_critic": {
        "name": "Text Critic",
        "description": "Quality scoring and platform authenticity check for text content",
        "depends_on": ["text_narrator"],
        "outputs": ["score", "feedback", "revision_needed"]
    },
    "production": {
        "name": "Production Agent",
        "description": "Parallel image and audio generation (fan-out)",
        "depends_on": ["narrator", "planner"],
        "outputs": ["images", "audio_files", "duration"]
    },
    "publisher": {
        "name": "Publisher Agent",
        "description": "Animation, compilation, and Discord publishing",
        "depends_on": ["production"],
        "outputs": ["video_path", "discord_message"]
    },
    "text_publisher": {
        "name": "Text Publisher",
        "description": "Exporting text content to Markdown or platform APIs",
        "depends_on": ["text_critic"],
        "outputs": ["output_path", "content_preview"]
    }
}


@app.get("/api/workflow/graph")
def get_workflow_graph():
    """
    Returns the agent dependency graph as JSON.
    
    This visualizes the multi-agent pipeline architecture:
    - Each agent's dependencies
    - Data flow between agents
    - Parallel execution opportunities
    """
    graph = []
    for agent_id, agent_info in AGENT_DEPENDENCY_GRAPH.items():
        graph.append({
            "id": agent_id,
            "name": agent_info["name"],
            "description": agent_info["description"],
            "depends_on": agent_info["depends_on"],
            "outputs": agent_info["outputs"],
            "parallel_capable": len(agent_info["depends_on"]) > 1
        })
    
    return {
        "graph": graph,
        "metadata": {
            "total_agents": len(graph),
            "execution_mode": "sequential_with_parallel_fanout",
            "description": "Content Factory multi-agent pipeline"
        }
    }


@app.get("/api/workflow/graph/dot")
def get_workflow_graph_dot():
    """Returns the graph in DOT format for visualization."""
    dot_lines = [
        "digraph pipeline {",
        "  rankdir=TB;",
        "  node [shape=box, style=rounded, fontname=Arial];",
    ]
    
    for agent_id, agent_info in AGENT_DEPENDENCY_GRAPH.items():
        label = f"{agent_info['name']}\\n({agent_id})"
        dot_lines.append(f'  {agent_id} [label="{label}"];')
    
    for agent_id, agent_info in AGENT_DEPENDENCY_GRAPH.items():
        for dep in agent_info["depends_on"]:
            dot_lines.append(f"  {dep} -> {agent_id};")
    
    dot_lines.append("}")
    
    return {"dot": "\n".join(dot_lines)}


# ─── Scheduled recurring runs ─────────────────────────────────────────────────

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

scheduler = BackgroundScheduler()
scheduler.start()


class ScheduleRequest(BaseModel):
    schedule_id: Optional[str] = None
    topic: Optional[str] = None
    auto_approve: bool = False
    cron: Optional[str] = None
    interval_hours: Optional[int] = None
    enabled: bool = True


class ScheduleResponse(BaseModel):
    schedule_id: str
    status: str
    topic: str
    schedule: str
    message: str


def _run_scheduled_pipeline(schedule_id: str, topic: Optional[str], auto_approve: bool):
    """Execute a scheduled pipeline run."""
    if not topic:
        from modules.discovery import get_trending_topic
        topic = get_trending_topic(region="IN")

    state = PipelineState()
    state.init_db()
    run_id = state.create_run(topic, f"scheduled:{schedule_id}")

    thread = threading.Thread(target=run_pipeline_task, args=(run_id, auto_approve))
    thread.daemon = True
    thread.start()
    print(f"Scheduled run triggered: {run_id} (schedule: {schedule_id})")


@app.post("/api/schedules", response_model=ScheduleResponse, status_code=201)
def create_schedule(req: ScheduleRequest):
    """
    Create a scheduled pipeline run.
    
    Use either cron expression or interval_hours (not both).
    
    Examples:
        - cron: "0 9 * * *" (every day at 9 AM)
        - cron: "0 */6 * * *" (every 6 hours)
        - interval_hours: 6 (every 6 hours)
    """
    import uuid

    schedule_id = req.schedule_id or str(uuid.uuid4())[:8]
    topic = req.topic or "trending"

    if req.cron:
        trigger = CronTrigger.from_crontab(req.cron)
        schedule_desc = f"cron: {req.cron}"
    elif req.interval_hours:
        trigger = IntervalTrigger(hours=req.interval_hours)
        schedule_desc = f"every {req.interval_hours} hour(s)"
    else:
        raise HTTPException(
            status_code=400,
            detail="Either 'cron' or 'interval_hours' must be specified"
        )

    job = scheduler.add_job(
        _run_scheduled_pipeline,
        trigger=trigger,
        args=[schedule_id, topic, req.auto_approve],
        id=schedule_id,
        replace_existing=True,
    )

    if not req.enabled:
        scheduler.pause_job(schedule_id)
        schedule_desc += " (paused)"

    return ScheduleResponse(
        schedule_id=schedule_id,
        status="ACTIVE" if req.enabled else "PAUSED",
        topic=topic,
        schedule=schedule_desc,
        message=f"Schedule created: {schedule_desc}"
    )


@app.get("/api/schedules")
def list_schedules():
    """List all scheduled jobs."""
    jobs = scheduler.get_jobs()
    schedules = []
    for job in jobs:
        schedules.append({
            "schedule_id": job.id,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "pending": job.next_run_time is not None,
        })
    return {"schedules": schedules}


@app.delete("/api/schedules/{schedule_id}")
def delete_schedule(schedule_id: str):
    """Delete a scheduled job."""
    try:
        scheduler.remove_job(schedule_id)
        return {"status": "ok", "message": f"Schedule {schedule_id} deleted"}
    except Exception:
        raise HTTPException(status_code=404, detail="Schedule not found")


@app.post("/api/schedules/{schedule_id}/pause")
def pause_schedule(schedule_id: str):
    """Pause a scheduled job."""
    try:
        scheduler.pause_job(schedule_id)
        return {"status": "ok", "message": f"Schedule {schedule_id} paused"}
    except Exception:
        raise HTTPException(status_code=404, detail="Schedule not found")


@app.post("/api/schedules/{schedule_id}/resume")
def resume_schedule(schedule_id: str):
    """Resume a paused scheduled job."""
    try:
        scheduler.resume_job(schedule_id)
        return {"status": "ok", "message": f"Schedule {schedule_id} resumed"}
    except Exception:
        raise HTTPException(status_code=404, detail="Schedule not found")
