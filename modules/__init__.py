# modules/__init__.py
from .discovery import get_trending_topic
from .narrator import generate_narrative
from .visuals import generate_visuals
from .voice import generate_audio
from .animator import animate_scenes
from .compiler import compile_video
from .publisher import publish, publish_video  # both names available

__all__ = [
    "get_trending_topic",
    "generate_narrative",
    "generate_visuals",
    "generate_audio",
    "animate_scenes",
    "compile_video",
    "publish",
    "publish_video",
]