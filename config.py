import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(exist_ok=True)

# Flask config
SECRET_KEY = os.getenv("SECRET_KEY", "pgmnt-dev-key-change-me")

# PIN authentication
PIN_HASH = os.getenv("PIN_HASH", "")
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"

# Dev server port
PORT = int(os.getenv("PORT", "5004"))
