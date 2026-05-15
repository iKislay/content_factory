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

# Webhook security
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

OUTPUT_DIR = "output"
TEMP_DIR = "temp"
DB_PATH = "state.db"

# Agent configuration
MAX_PRODUCTION_WORKERS = 10  # unified concurrent workers for image+audio fan-out (Task 5)
PRODUCTION_FANOUT_TIMEOUT_SEC = 300  # hard deadline for full production fan-out
AGENT_LOG_LEVEL = "INFO"     # structured agent logging level

# Reasoning & quality control
CRITIC_MIN_SCORE = 7         # overall score below which Critic requests revision (1-10)
MAX_REVISION_CYCLES = 2      # max Narrator→Critic revision loops before forcing approval
RESEARCH_MAX_RESULTS = 6     # DuckDuckGo results per search query
MAX_TOOL_ROUNDS = 3          # max agentic tool-use loop iterations per LLM call

# Circuit Breaker for failing tools
CIRCUIT_FAILURE_THRESHOLD = 3    # failures before circuit opens
CIRCUIT_TIMEOUT_WINDOW_SEC = 60  # time window to track failures (seconds)
CIRCUIT_COOLDOWN_SEC = 120       # seconds to wait before testing recovery
CIRCUIT_HALF_OPEN_RETRIES = 2   # test recoveries allowed in half-open state

# Retry & resilience configuration
TOOL_MAX_RETRIES = 3         # max retry attempts for failed tool calls
TOOL_RETRY_BASE_DELAY = 1.0  # base delay in seconds (exponential backoff: 1s, 2s, 4s...)
TOOL_RETRY_MAX_DELAY = 30.0  # maximum delay cap in seconds
TOOL_RETRY_BACKOFF = 2.0     # exponential backoff multiplier