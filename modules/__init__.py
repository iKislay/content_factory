# modules/__init__.py
from .discovery import get_trending_topic
from .narrator import generate_narrative
from .visuals import generate_visuals
from .voice import generate_voice
from .animator import apply_ken_burns
from .compiler import compile_video
from .publisher import publish_video

__all__ = [
    "get_trending_topic",
    "generate_narrative",
    "generate_visuals",
    "generate_voice",
    "apply_ken_burns",
    "compile_video",
    "publish_video"
]