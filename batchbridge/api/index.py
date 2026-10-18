import os
import sys
from pathlib import Path
from urllib.parse import parse_qs


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/batchbridge.db")
os.environ.setdefault("AGENT_MODE", "demo")
os.environ.setdefault("SEED_DEMO_DATA", "true")

vercel_url = os.getenv("VERCEL_URL")
if vercel_url:
    public_url = f"https://{vercel_url}"
    os.environ.setdefault("APP_BASE_URL", public_url)
    os.environ.setdefault("ALLOWED_ORIGINS", public_url)

from app import models  # noqa: E402,F401
from app.database import Base, engine  # noqa: E402

Base.metadata.create_all(engine)

from app.main import app as fastapi_app  # noqa: E402


class VercelPathRewrite:
    def __init__(self, wrapped_app):
        self.wrapped_app = wrapped_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            query = parse_qs(scope.get("query_string", b"").decode())
            forwarded_path = query.get("path", [None])[0]
            if forwarded_path:
                scope = dict(scope)
                scope["path"] = f"/{forwarded_path.lstrip('/')}"
                scope["raw_path"] = scope["path"].encode()
        await self.wrapped_app(scope, receive, send)


app = VercelPathRewrite(fastapi_app)
