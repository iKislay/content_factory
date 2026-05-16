# agents/text_publisher.py
"""
TextPublisherAgent — publishes text content to platforms or exports.

Handles:
- Writing content to Markdown file
- Optional: Direct posting to LinkedIn/Twitter API (future)
- Generating a "preview" of how the content will look

Blackboard messages consumed:
  TEXT_APPROVED  { content, platform, topic, scores }

Blackboard messages produced:
  TEXT_PUBLISHED { output_path, platform, content_preview }
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional

from agents.base import AgentResult, BaseAgent
import config


_TEXT_PREVIEW_TEMPLATES = {
    "linkedin": """
╔══════════════════════════════════════════════════════════════════╗
║                        LINKEDIN PREVIEW                          ║
╠══════════════════════════════════════════════════════════════════╣
║ {content}
╚══════════════════════════════════════════════════════════════════╝
""",
    "twitter": """
╔══════════════════════════════════════════════════════════════════╗
║                        TWITTER PREVIEW                           ║
╠══════════════════════════════════════════════════════════════════╣
║ {content}
╚══════════════════════════════════════════════════════════════════╝
""",
}


class TextPublisherAgent(BaseAgent):
    """
    Publishes text content to file or buffer.
    
    For now, outputs to Markdown file. Can be extended to support
    direct API posting to LinkedIn/Twitter.
    """

    name = "text_publisher"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        self.log("Publishing text content...")

        # Load from blackboard
        approved_msg = self.get_latest(run_id, "TEXT_APPROVED")
        
        if not approved_msg:
            return AgentResult(
                success=False,
                reasoning="TEXT_APPROVED message missing",
                errors=["No approved text to publish"],
            )

        payload = approved_msg["payload"]
        content = payload.get("content", "")
        platform = payload.get("platform", "linkedin")
        topic = payload.get("topic", "")
        scores = payload.get("scores", {})

        # Generate output
        output_path = self._publish(content, platform, topic, run_id)
        
        # Generate preview
        preview = self._generate_preview(content, platform)

        # Save text content to DB so API can serve it to frontend
        self._save_to_db(run_id, content, platform, output_path)

        self.log(f"Published to: {output_path}")

        # Post to blackboard
        self.post_message(
            run_id=run_id,
            msg_type="TEXT_PUBLISHED",
            payload={
                "output_path": output_path,
                "platform": platform,
                "content_preview": preview,
                "topic": topic,
                "scores": scores,
            },
            recipient="orchestrator",
        )

        return AgentResult(
            success=True,
            output={
                "output_path": output_path,
                "platform": platform,
                "content_preview": preview,
            },
            next_agent="orchestrator",
            reasoning=f"Text published to {platform} ({output_path})",
        )

    def _publish(
        self, 
        content: str, 
        platform: str, 
        topic: str, 
        run_id: str
    ) -> str:
        """Write content to file."""
        output_dir = getattr(config, "OUTPUT_DIR", "output")
        os.makedirs(output_dir, exist_ok=True)

        # Create filename
        safe_topic = "".join(c for c in topic if c.isalnum() or c in " -_")[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{platform}_{safe_topic}_{timestamp}.md"
        
        filepath = os.path.join(output_dir, filename)
        
        # Add frontmatter
        frontmatter = f"""---
platform: {platform}
topic: {topic}
created: {datetime.now().isoformat()}
run_id: {run_id}
---

"""
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter)
            f.write(content)
        
        return filepath

    def _generate_preview(self, content: str, platform: str) -> str:
        """Generate a terminal-friendly preview."""
        template = _TEXT_PREVIEW_TEMPLATES.get(platform, _TEXT_PREVIEW_TEMPLATES["linkedin"])
        
        # Truncate content for preview
        preview_content = content[:500] + "..." if len(content) > 500 else content
        # Replace newlines for display
        preview_content = preview_content.replace("\n", "\\n")
        
        return template.format(content=preview_content)

    def _save_to_db(self, run_id: str, content: str, platform: str, output_path: str) -> None:
        """Persist text content and output path to pipeline_runs table."""
        try:
            conn = sqlite3.connect(config.DB_PATH)
            # Ensure text_content column exists
            try:
                conn.execute("ALTER TABLE pipeline_runs ADD COLUMN text_content TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists

            conn.execute(
                "UPDATE pipeline_runs SET final_path = ?, text_content = ?, updated_at = ? WHERE run_id = ?",
                (output_path, content, datetime.now().isoformat(), run_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            self.log(f"Warning: could not save text to DB: {e}")