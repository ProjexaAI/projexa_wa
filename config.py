import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "projexa_internship")

OPENCODE_API_KEY = os.getenv("OPENCODE_API_KEY", "")
OPENCODE_MODEL = os.getenv("OPENCODE_MODEL", "mimo-v2.5-free")
OPENCODE_BASE_URL = "https://opencode.ai/zen/v1"

OPENWA_API_URL = os.getenv("OPENWA_API_URL", "http://localhost:2785/api")
OPENWA_API_KEY = os.getenv("OPENWA_API_KEY", "")
OPENWA_SESSION_ID = os.getenv("OPENWA_SESSION_ID", "")

# JWT (must match web app's JWT_SECRET)
JWT_SECRET = os.getenv("JWT_SECRET", "")
WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "http://localhost:3000")

# Cloudflare R2 (direct upload)
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "")
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "")
R2_CDN_BASE_URL = os.getenv("R2_CDN_BASE_URL", "")

SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# Master admin password (impersonation mode)
MASTER_ADMIN_PASSWORD = os.getenv("MASTER_ADMIN_PASSWORD", "")
