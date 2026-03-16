from __future__ import annotations

import itertools
import threading
from typing import Optional

from ascp.artifact_store import ArtifactStore
from ascp.compression import CompressionPipeline
from ascp.delta_context import DeltaContextManager, Message
from ascp.registry import SchemaRegistry

_id_counter = itertools.count(1)
_id_lock = threading.Lock()


def _next_id() -> int:
    with _id_lock:
        return next(_id_counter)


class MCPAdapter:
    def __init__(
        self,
        registry: Optional[SchemaRegistry] = None,
        store: Optional[ArtifactStore] = None,
        delta_manager: Optional[DeltaContextManager] = None,
        pipeline: Optional[CompressionPipeline] = None,
    ) -> None:
        self.registry = registry if registry is not None else SchemaRegistry()
        self.store = store if store is not None else ArtifactStore()
        self.delta_manager = delta_manager if delta_manager is not None else DeltaContextManager()
        self.pipeline = pipeline if pipeline is not None else CompressionPipeline()
        self._schema_id: Optional[str] = None
        self._schema_id_lock = threading.Lock()

    def tools_register_request(self, tools: list[dict], ttl: int = 3600) -> dict:
        schema_id, _ = self.registry.register(tools, ttl=ttl)
        with self._schema_id_lock:
            self._schema_id = schema_id
        return {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "tools/register",
            "params": {"tools": tools, "ttl": ttl},
        }

    def tools_register_response(self, schema_id: str, ttl: int) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "result": {"schema_id": schema_id, "ttl": ttl},
        }

    def tools_list_response(self, tools: list[dict], use_ref: bool = False) -> dict:
        with self._schema_id_lock:
            schema_id = self._schema_id
        if use_ref and schema_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": _next_id(),
                "result": {"tool_schema_ref": schema_id},
            }
        return {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "result": {"tools": tools},
        }

    def tool_call_request(
        self, name: str, arguments: dict, schema_id: Optional[str] = None
    ) -> dict:
        params: dict = {"name": name, "arguments": arguments}
        if schema_id is not None:
            params["_ascp"] = {"tool_schema_ref": schema_id}
        return {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "tools/call",
            "params": params,
        }

    def handle_ref_unknown(self, schema_id: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "error": {
                "code": -32001,
                "message": "ASCP_REF_UNKNOWN",
                "data": {"schema_id": schema_id, "fallback_required": True},
            },
        }

    def is_ascp_capable(self, initialize_params: dict) -> bool:
        try:
            return bool(initialize_params["capabilities"]["ascp"]["schemaRef"])
        except (KeyError, TypeError):
            return False

    def build_initialize_capabilities(self) -> dict:
        return {
            "tools": {},
            "ascp": {"schemaRef": True, "registryVersion": "0.1"},
        }


class A2AAdapter:
    def __init__(
        self,
        registry: Optional[SchemaRegistry] = None,
        store: Optional[ArtifactStore] = None,
        base_url: str = "https://agent.example.com",
    ) -> None:
        self.registry = registry if registry is not None else SchemaRegistry()
        self.store = store if store is not None else ArtifactStore()
        self.base_url = base_url.rstrip("/")

    def agent_card(self, name: str, description: str, skills: list[dict]) -> dict:
        return {
            "name": name,
            "description": description,
            "url": self.base_url,
            "skills": skills,
            "capabilities": {
                "ascp": {
                    "schemaRef": True,
                    "registryEndpoint": self.base_url + "/ascp/registry",
                    "registryVersion": "0.1",
                    "defaultTtl": 86400,
                }
            },
        }

    def schema_ref_part(self, schema_id: str) -> dict:
        return {
            "type": "schema_ref",
            "schema_id": schema_id,
            "registry": self.base_url + "/ascp/registry",
        }

    def send_message_with_ref(self, text: str, schema_id: str) -> dict:
        return {
            "role": "user",
            "parts": [
                {"type": "text", "text": text},
                self.schema_ref_part(schema_id),
            ],
        }

    def is_ascp_capable(self, agent_card: dict) -> bool:
        try:
            return bool(agent_card["capabilities"]["ascp"]["schemaRef"])
        except (KeyError, TypeError):
            return False
