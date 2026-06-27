import os
from dotenv import load_dotenv

# Skip GCE metadata check for local environments to eliminate connection latency/warnings
os.environ["NO_GCE_CHECK"] = "true"

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))


VAPI_PRIVATE_KEY = os.getenv("VAPI_PRIVATE_KEY", "")
VAPI_PUBLIC_KEY = os.getenv("VAPI_PUBLIC_KEY", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "clinic_knowledge")
FAISS_INDEX_PATH = os.path.join(BASE_DIR, "data", "faiss_index")
ASSISTANT_ID_FILE = os.path.join(BASE_DIR, "data", "assistant_id.txt")

# VAPI API
VAPI_API_BASE = "https://api.vapi.ai"

# Google Calendar & Server configurations
GOOGLE_CALENDAR_CREDENTIALS_RAW = os.getenv("GOOGLE_CALENDAR_CREDENTIALS", "backend/credentials/google-calendar-key.json")
if not os.path.isabs(GOOGLE_CALENDAR_CREDENTIALS_RAW):
    WORKSPACE_ROOT = os.path.dirname(BASE_DIR)
    GOOGLE_CALENDAR_CREDENTIALS = os.path.abspath(os.path.join(WORKSPACE_ROOT, GOOGLE_CALENDAR_CREDENTIALS_RAW))
else:
    GOOGLE_CALENDAR_CREDENTIALS = GOOGLE_CALENDAR_CREDENTIALS_RAW

GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "krishnasaimunagala@gmail.com")
PUBLIC_SERVER_URL = os.getenv("PUBLIC_SERVER_URL", "").rstrip("/")
