# config.py
import os
from dotenv import load_dotenv
load_dotenv()

LLM_PROVIDER = "groq"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2"

# Google Cloud TTS Configuration
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "google")  # "google" or "kokoro"
GOOGLE_CLOUD_TTS_API_KEY = os.getenv("GOOGLE_CLOUD_TTS_API_KEY", "")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

IMAGE_PROVIDER = "pollinations"
POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"
IMAGE_WIDTH = 1024
IMAGE_HEIGHT = 1792

SCENES_COUNT = 5
SCENE_DURATION_SEC = 6
VIDEO_FPS = 24
KEN_BURNS_ZOOM_RATIO = 0.04

KOKORO_VOICE = "af_bella"
KOKORO_SAMPLE_RATE = 24000

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

OUTPUT_DIR = "output"
TEMP_DIR = "temp"
DB_PATH = "state.db"

# Agent configuration
MAX_PRODUCTION_WORKERS = 3   # concurrent threads for image + audio fan-out
AGENT_LOG_LEVEL = "INFO"     # structured agent logging level

# Reasoning & quality control
CRITIC_MIN_SCORE = 7         # overall score below which Critic requests revision (1-10)
MAX_REVISION_CYCLES = 2      # max Narrator→Critic revision loops before forcing approval
RESEARCH_MAX_RESULTS = 6     # DuckDuckGo results per search query
MAX_TOOL_ROUNDS = 3          # max agentic tool-use loop iterations per LLM call