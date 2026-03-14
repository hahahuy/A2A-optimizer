# ASCP Optimizer

**Agent Semantic Communication Protocol** — a Python toolkit that reduces AI agent token overhead via schema references, content-addressed artifacts, delta context, and compression.

## The Problem

Every LLM API call in a typical multi-agent setup silently pays a token tax:

```
Turn N input =
  system_prompt        (~200 tokens, always)
+ tool schemas         (~103 tokens × N_tools, resent every call)  ← the culprit
+ full history         (~150 tokens × N_turns, grows unbounded)
+ actual task          (~100 tokens)
```

With 24 MCP tools, **78% of your input tokens at turn 5 are pure overhead** — tool schemas resent verbatim on every single call. ASCP fixes this at the protocol layer.

| Metric | Baseline | With ASCP | Reduction |
|--------|----------|-----------|-----------|
| Tool schema tokens/call | 2,472 | ~6 (ID ref) | **~99%** |
| History tokens at turn 20 | ~3,000 | ~150 (delta) | **~95%** |
| Prose payload tokens | 500 | ~165 (compressed) | **~67%** |

---

## Install

```bash
pip install -e .

# Optional: token counting
pip install tiktoken

# Optional: heavy compression backend
pip install llmlingua
```

Requires Python 3.10+, no mandatory dependencies.

---

## The 5 Tools

### 1. Schema Registry

Register tool schema bundles once, reference them by `sha256:` ID on every subsequent call.

```python
from ascp import SchemaRegistry

registry = SchemaRegistry()

# Register once — returns a stable content-addressed ID
schema_id, ttl = registry.register([
    {"name": "read_file", "description": "...", "inputSchema": {...}},
    # ... 23 more tools
], ttl=3600)
# schema_id = "sha256:a3f2c1b9e5d4..."

# All subsequent calls: 6 tokens instead of 2,472
bundle = registry.resolve(schema_id)

# Extend TTL before expiry
registry.refresh(schema_id, ttl=3600)
```

### 2. Content-Addressed Artifact Store

Store large inter-agent payloads (analysis outputs, documents, code) by content hash. Pass the CID instead of re-sending the full payload.

```python
from ascp import ArtifactStore

store = ArtifactStore(max_bytes=100 * 1024 * 1024)  # 100 MB, LRU eviction

# Store any content — returns sha256: CID
cid = store.store("Full analysis report... (8,000 tokens)", media_type="text/plain")
# cid = "sha256:b7e2d9f1..."

# Pass only the CID between agents; fetch only when needed
entry = store.retrieve(cid)
print(entry.size)       # bytes
print(entry.stored_at)  # timestamp

store.delete(cid)
```

### 3. Delta Context Manager

Exchange only the messages added since the last shared checkpoint instead of the full conversation history.

```python
from ascp import DeltaContextManager, Message

mgr = DeltaContextManager()

history = [
    Message(role="user", content="Analyze Q3 sales"),
    Message(role="assistant", content="Found 3 anomalies..."),
]

# Checkpoint current state
ckpt = mgr.checkpoint(history, label="after-analysis")

# Later — only send what's new
history.append(Message(role="user", content="Explain anomaly #2"))
delta = mgr.delta(since=ckpt, current=history)
# delta = [Message(role="user", content="Explain anomaly #2")]

# Reconstruct full history on the other side
full = mgr.reconstruct(ckpt, delta)

# See how many tokens you're saving
stats = mgr.token_savings(ckpt, history)
# {"full_message_count": 3, "delta_count": 1, "saved_count": 2, "saved_pct": 66.7}
```

### 4. Compression Middleware

Strip filler phrases, collapse whitespace, and minify JSON payloads before transmission.

```python
from ascp import CompressionPipeline, WhitespaceCompressor, FillerPhraseCompressor, JSONMinifier

# Default pipeline: whitespace → filler phrases → JSON minify
pipeline = CompressionPipeline()

result = pipeline.compress(
    "Certainly! I'd be happy to help. As an AI language model, "
    "here is the analysis:\n\n\n{ \"status\":  \"ok\",  \"count\":  42 }"
)

print(result.original_tokens)    # ~35
print(result.compressed_tokens)  # ~12
print(result.saved_pct)          # ~65.7
print(result.compressed)
# 'here is the analysis:\n\n{"status":"ok","count":42}'
```

**Custom pipeline:**
```python
pipeline = CompressionPipeline([WhitespaceCompressor(), JSONMinifier()])

# Chain additional compressors
pipeline.add(FillerPhraseCompressor())
```

**Optional heavy backend (LLMLingua-2, 3–6× compression):**
```python
# pip install llmlingua
from llmlingua import PromptCompressor

class LLMLinguaCompressor:
    def __init__(self, ratio=0.5):
        self._c = PromptCompressor("microsoft/llmlingua-2-xlm-roberta-large-meetingbank")
        self._ratio = ratio
    def compress(self, text):
        return self._c.compress_prompt(text, rate=self._ratio)["compressed_prompt"]
    def name(self):
        return f"llmlingua2(ratio={self._ratio})"

pipeline = CompressionPipeline().add(LLMLinguaCompressor(ratio=0.5))
```

### 5. A2A/MCP Adapter

Wire all four tools into JSON-RPC 2.0 messages compatible with MCP and A2A.

```python
from ascp import MCPAdapter, A2AAdapter

# --- MCP ---
adapter = MCPAdapter()

# Build initialize capabilities to advertise ASCP support
caps = adapter.build_initialize_capabilities()
# {"tools": {}, "ascp": {"schemaRef": True, "registryVersion": "0.1"}}

# Check if peer supports ASCP
if adapter.is_ascp_capable(peer_initialize_params):
    # Register tools once
    req = adapter.tools_register_request(tools, ttl=3600)
    # → sends to MCP server, gets back schema_id

    # All subsequent tool calls use the ref
    call = adapter.tool_call_request("read_file", {"path": "/etc/hosts"}, schema_id=schema_id)

    # If peer responds with ASCP_REF_UNKNOWN, fallback gracefully
    fallback = adapter.handle_ref_unknown(schema_id)

# --- A2A ---
a2a = A2AAdapter(base_url="https://my-agent.example.com")

card = a2a.agent_card(
    name="DataAgent",
    description="Analyzes structured data",
    skills=[{"id": "analyze", "name": "Analyze"}],
)
# card["capabilities"]["ascp"]["schemaRef"] == True

msg = a2a.send_message_with_ref("Analyze Q3 sales", schema_id=schema_id)
# {"role": "user", "parts": [{"type": "text", ...}, {"type": "schema_ref", ...}]}
```

---

## Full Example: MCP Handshake with Schema References

```python
from ascp import MCPAdapter

adapter = MCPAdapter()
tools = [{"name": "search", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}}]

# Turn 1: register and use full schema
req = adapter.tools_register_request(tools)
schema_id = req["params"]["tools_schema_id"] if "tools_schema_id" in req.get("params", {}) else None

# After server acknowledges, resolve locally
schema_id, _ = adapter.registry.register(tools)

# Turn 2+: reference only — ~6 tokens vs ~2,472
ref = {"tool_schema_ref": schema_id}

# Verify registry holds the bundle
assert adapter.registry.resolve(schema_id) == tools
```

---

## Docs

- [`docs/ascp-spec-v0.1.md`](docs/ascp-spec-v0.1.md) — Full ASCP protocol specification (RFC-style)
- [`docs/ascp-research-post.md`](docs/ascp-research-post.md) — "The 2,472-Token Tax" — research post with SoTA analysis

---

## Tests

```bash
pip install pytest
pytest -v   # 99 tests, 0 failures
```

---

## License

MIT
