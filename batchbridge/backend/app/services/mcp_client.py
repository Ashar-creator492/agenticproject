import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import get_settings

AGENT_TOOL_PERMISSIONS = {
    "triage": {"get_case", "search_products", "find_related_reports"},
    "traceability": {
        "get_case",
        "search_products",
        "get_batch",
        "get_batch_shipments",
        "get_non_recipient_retailers",
        "find_related_reports",
        "get_distribution_summary",
    },
    "escalation": {
        "get_case",
        "get_approved_traceability",
        "get_batch_shipments",
        "get_inspection_findings",
        "get_case_evidence_metadata",
        "get_case_timeline",
        "get_distribution_summary",
    },
}


class EvidenceMCPClient:
    def __init__(self) -> None:
        self.trace: list[dict[str, Any]] = []
        backend_dir = Path(__file__).resolve().parents[2]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(backend_dir)
        environment["DATABASE_URL"] = get_settings().database_url
        self.parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server"],
            env=environment,
            cwd=str(backend_dir.parent),
        )

    @asynccontextmanager
    async def session(self):
        async with stdio_client(self.parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    @staticmethod
    def _decode(result) -> Any:
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            if set(structured) == {"result"}:
                return structured["result"]
            return structured
        texts = [item.text for item in result.content if getattr(item, "type", None) == "text"]
        if not texts:
            return None
        text = "\n".join(texts)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    async def call(
        self,
        agent_type: str,
        session: ClientSession,
        name: str,
        arguments: dict,
    ) -> Any:
        # Enforce each stage's least-privilege tool allowlist locally.
        if name not in AGENT_TOOL_PERMISSIONS.get(agent_type, set()):
            raise PermissionError(f"Agent {agent_type} cannot call MCP tool {name}")
        started = time.monotonic()
        trace = {"tool": name, "success": False, "record_count": 0}
        try:
            result = await session.call_tool(name, arguments)
            if result.isError:
                raise RuntimeError(f"MCP tool {name} failed: {self._decode(result)}")
            decoded = self._decode(result)
            trace["success"] = True
            if isinstance(decoded, list):
                trace["record_count"] = len(decoded)
            elif isinstance(decoded, dict):
                trace["record_count"] = int(decoded.get("found", True))
            return decoded
        finally:
            trace["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
            self.trace.append(trace)
