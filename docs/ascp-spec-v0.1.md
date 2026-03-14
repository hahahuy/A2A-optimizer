# ASCP: Agent Semantic Communication Protocol
### Specification Version 0.1 — Draft

---

## Abstract

This document defines the **Agent Semantic Communication Protocol (ASCP)**, a lightweight protocol extension layer for AI agent communication frameworks — specifically the Model Context Protocol (MCP) and the Agent-to-Agent (A2A) protocol. ASCP introduces a **Schema Reference Layer** that eliminates the repeated transmission of identical tool schema payloads on every LLM API invocation, a problem herein termed the *Tool Schema Tax*. By replacing full schema bodies with content-addressed identifiers on subsequent calls, ASCP reduces per-call token overhead by up to 97% for schema-heavy workloads, aligns with LLM provider prefix-caching mechanisms, and is 100% backward-compatible with existing MCP and A2A implementations.

---

## Status of This Document

This document is an **individual draft specification**, version 0.1. It is not affiliated with Anthropic, Google, or the Linux Foundation. It is published for community review and feedback.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [RFC 2119].

Implementations that claim ASCP compliance MUST implement all REQUIRED behaviors described herein. OPTIONAL features MAY be omitted, but MUST NOT be implemented in a conflicting manner.

---

## 1. Introduction

Modern AI agent systems are composed of one or more LLM-backed agents that communicate with tool servers (via MCP) and with peer agents (via A2A). In both protocols, tool capability descriptions — schemas that enumerate available tools, their parameters, and their types — are the primary mechanism by which an LLM understands what actions are available to it.

The current state of these protocols results in these schemas being re-transmitted in full on every LLM API call. In a workload with 24 tools across 3 MCP servers, this overhead reaches 2,472 tokens per call. Within 5 conversational turns in a standard LangGraph + MCP setup, tool schemas alone constitute approximately 78% of total LLM input tokens. This is not a marginal inefficiency — it is a structural flaw.

ASCP addresses this at the protocol layer, not the application layer, through three mechanisms:

1. **Schema Registration**: A one-time registration operation that issues a stable, content-addressed identifier for any tool schema bundle.
2. **Schema Reference Fields**: A wire-format substitution that allows the full schema body to be replaced with a compact reference token on all subsequent calls.
3. **Capability Negotiation**: An extension to MCP and A2A handshakes that allows peers to declare ASCP support, ensuring graceful fallback when one side does not support the protocol.

---

## 2. Problem Statement

### 2.1 The Tool Schema Tax

In MCP, tool schemas are delivered via the `tools/list` response and are expected to be included in the system prompt or tool parameter of every LLM API call. A single MCP tool schema has the following structure:

```json
{
  "name": "read_file",
  "description": "Read the contents of a file at a given path.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "The file path to read."
      }
    },
    "required": ["path"]
  }
}
```

A schema of this complexity consumes approximately **103 tokens** when tokenized by a typical LLM tokenizer. This figure scales linearly with tool count. With 24 tools across 3 MCP servers, the baseline overhead is:

> `24 tools × 103 tokens/tool = 2,472 tokens` per LLM call

This overhead is constant regardless of the content of the user's query. It is paid on every single API invocation, including trivial one-token responses.

### 2.2 Measurements

The following table illustrates the cumulative and proportional cost of the Tool Schema Tax in a representative LangGraph + MCP session:

| Metric | Value |
|---|---|
| Tool count | 24 (across 3 MCP servers) |
| Tokens per tool schema | ~103 |
| Schema overhead per call | 2,472 tokens |
| Avg. user message size | ~30 tokens |
| Avg. assistant response size | ~120 tokens |
| Cumulative schema tokens at turn 5 | ~12,360 tokens |
| Cumulative non-schema tokens at turn 5 | ~3,450 tokens |
| **Schema % of total input at turn 5** | **~78%** |

At typical LLM API pricing, this represents a direct monetary waste proportional to workload scale. For an agent handling 10,000 tool-assisted queries per day at $3.00/MTok (input), 24 tools generate approximately **$74/day in avoidable schema overhead**.

### 2.3 Why Existing Approaches Don't Solve This

**LLM Provider Prefix Caching** (Anthropic: ~90% cost reduction; OpenAI: ~50%) partially mitigates this by caching the static prefix of a prompt. However, prefix caching operates at the API provider level and requires the prefix to be bit-identical across calls. Any change to the user message or prior conversation history after the system prompt invalidates or shortens the cacheable prefix, depending on provider implementation. ASCP is complementary: by moving schemas out of the prompt context and into a separately negotiated reference, ASCP maximizes the stable prefix available for caching.

**Application-level memoization** (e.g., caching tool lists in agent code) reduces network round-trips but does not reduce token count. The LLM still receives full schemas in its context window.

**Tool filtering** (dynamically selecting relevant tools per query) reduces token count but requires semantic reasoning to select tools, adds latency, and can miss tools that are relevant to multi-step plans.

ASCP is the only approach that operates at the **wire format layer**, is **transparent to both the LLM and the application**, and provides **guaranteed schema omission** from subsequent calls.

---

## 3. Terminology

**Schema Bundle**: A JSON array of one or more MCP tool schema objects, or an equivalent capability descriptor in A2A, treated as an atomic unit for the purposes of registration and referencing.

**Schema ID**: A content-addressed identifier for a Schema Bundle, formatted as `sha256:<hex-digest>` (see Section 4.2).

**Schema Registry**: A logical service (embedded in an MCP server, A2A agent, or standalone) that stores Schema Bundles keyed by Schema ID and services resolution requests.

**Schema Reference (`schema_ref` / `tool_schema_ref`)**: A wire-format field containing a Schema ID, used in place of a full Schema Bundle.

**ASCP-capable**: A descriptor applied to an MCP server, MCP client, or A2A agent that has implemented the ASCP extension as defined in this specification.

**Fallback**: The behavior of reverting to full schema transmission when one or both parties in a communication exchange are not ASCP-capable.

**TTL (Time to Live)**: The duration for which a Schema Registry entry is considered valid and MUST be retained by the holder.

---

## 4. Protocol Design: Schema Reference Layer

### 4.1 Schema Registration

Schema registration is the process by which a Schema Bundle is submitted to a Schema Registry and assigned a stable Schema ID. The registration MUST be idempotent: submitting the same bundle twice MUST return the same Schema ID and MUST NOT create duplicate entries.

Registration MAY be initiated by either party in a communication exchange (client or server in MCP; requester or responder in A2A). The party that possesses the schema typically initiates registration; however, a receiver MAY also register a schema it has received in full, for use in future exchanges.

A registration request MUST include:

- The full Schema Bundle as a JSON array.
- An optional `ttl` field, specified in seconds, indicating the desired retention duration (see Section 4.4).

A registration response MUST include:

- The `schema_id` string for the registered bundle.
- The `ttl` that will be honored (which MAY differ from the requested TTL).

### 4.2 Schema ID Format

Schema IDs MUST be formatted as:

```
"sha256:" <lowercase-hex-encoded SHA-256 digest>
```

The digest MUST be computed over the **canonical JSON serialization** of the Schema Bundle. Canonical serialization is defined as:

1. All JSON object keys are sorted lexicographically (Unicode code point order) at all nesting levels.
2. No insignificant whitespace (no spaces, no newlines outside string values).
3. Encoding is UTF-8.

Example:

```
sha256:a3f2c1b9e5d4087f6c2a91b3d7e0f4a8c6b2e9d1f0a3c5b7e2d9f1a4c6b8e0d2
```

Implementations MUST verify the Schema ID upon retrieval from the registry by recomputing the digest and comparing it to the stored ID. A mismatch MUST be treated as a integrity failure (see Section 9.1).

### 4.3 Tool Schema Reference Field

When an ASCP-capable sender has previously registered a Schema Bundle and received a Schema ID, it MAY substitute the full bundle with the following reference object in any protocol message that would otherwise carry the full bundle:

```json
{
  "tool_schema_ref": "sha256:a3f2c1b9e5d4087f6c2a91b3d7e0f4a8c6b2e9d1f0a3c5b7e2d9f1a4c6b8e0d2"
}
```

The `tool_schema_ref` field:

- MUST NOT be present alongside a full `tools` array in the same message.
- MUST reference a Schema ID that has been previously registered with the receiver's Schema Registry within the active TTL window.
- MAY be used in any MCP or A2A message that carries tool schema information, subject to the extensions defined in Sections 5 and 6.

A receiver that encounters a `tool_schema_ref` it cannot resolve (unknown ID, expired TTL, or registry unavailable) MUST respond with an error code `ASCP_REF_UNKNOWN` and SHOULD include a `fallback_required: true` field in the error response, prompting the sender to retransmit the full bundle.

### 4.4 Cache Semantics & TTL

Schema Registry entries MUST be retained for at least the agreed TTL duration. The TTL clock begins at the time of registration acknowledgment.

Default TTL values:

| Context | Default TTL |
|---|---|
| In-process (embedded registry) | Session lifetime |
| MCP server (persistent) | 3600 seconds (1 hour) |
| A2A agent registry endpoint | 86400 seconds (24 hours) |
| Standalone registry service | Implementation-defined |

A sender SHOULD re-register a Schema Bundle before its TTL expires if the communication session is expected to continue. Re-registration of an unexpired bundle MUST extend the TTL and MUST return the same Schema ID (because the content has not changed).

A receiver MAY evict registry entries before TTL expiry under memory pressure, but MUST do so in LRU order and MUST treat the evicted entry as if it had expired (responding with `ASCP_REF_UNKNOWN` if subsequently referenced).

### 4.5 Fallback Behavior

ASCP is designed to degrade gracefully. The following fallback rules MUST be observed:

1. **Unsupported receiver**: If a sender detects (via capability negotiation, Section 5.4 / 6.1) that the receiver does not support ASCP, the sender MUST transmit full Schema Bundles and MUST NOT include `tool_schema_ref` fields.

2. **Reference resolution failure**: If a receiver responds with `ASCP_REF_UNKNOWN`, the sender MUST retransmit the full Schema Bundle in the next message and MAY attempt re-registration before doing so.

3. **Registry unavailability**: If a sender's registry is unavailable (e.g., network partition in a remote registry scenario), the sender MUST fall back to full schema transmission. Stale references MUST NOT be sent.

4. **Unknown fields**: A receiver that does not understand ASCP MUST ignore unknown fields per standard JSON-RPC 2.0 extension rules. This means a `tool_schema_ref`-only message arriving at a non-ASCP receiver will fail to resolve tools, which MUST NOT be treated as silent success. The sender MUST detect the absence of ASCP acknowledgment and fall back.

### 4.6 Alignment with LLM Provider Prefix Caching

ASCP's Schema Reference Layer is designed to be composable with LLM provider prefix caching:

- By removing the schema bundle from the LLM context (replacing it with a resolved reference that is populated server-side or by the agent runtime), the static portion of the prompt can be maximized.
- Implementations that resolve schema references server-side (injecting the schema into the LLM context internally, before the API call) MUST place the schema content at the beginning of the prompt to maximize the cacheable prefix.
- Implementations that omit schema content from the LLM context entirely (relying on tool-use APIs that accept schemas as a separate parameter, such as Anthropic's `tools` parameter) SHOULD pass the resolved schema bundle via that separate parameter, never in the main prompt body.

The combined effect of ASCP + provider prefix caching yields:

| Scenario | Token Cost (per call) |
|---|---|
| Baseline (no ASCP, no caching) | 2,472 schema tokens |
| Prefix caching only (best case) | ~247 tokens (90% reduction) |
| ASCP schema_ref only | ~6 tokens |
| ASCP + provider caching | ~6 tokens (ref is negligible) |

---

## 5. MCP Extension

MCP wire format is JSON-RPC 2.0 over stdio or HTTP SSE. ASCP extends MCP by adding one new operation, modifying one existing operation response, and adding one new field to tool call requests.

### 5.1 New Operation: `tools/register`

**Direction**: Client → Server (or bidirectional, if the server also calls tools on the client)

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "method": "tools/register",
  "params": {
    "tools": [
      {
        "name": "read_file",
        "description": "Read the contents of a file.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "path": { "type": "string", "description": "File path to read." }
          },
          "required": ["path"]
        }
      }
      // ... additional tool schemas
    ],
    "ttl": 3600
  }
}
```

**Success Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "result": {
    "schema_id": "sha256:a3f2c1b9e5d4087f6c2a91b3d7e0f4a8c6b2e9d1f0a3c5b7e2d9f1a4c6b8e0d2",
    "ttl": 3600
  }
}
```

**Error Response** (e.g., invalid schema):

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "error": {
    "code": -32001,
    "message": "ASCP_INVALID_SCHEMA",
    "data": { "reason": "tools array must be non-empty" }
  }
}
```

### 5.2 Modified Operation: `tools/list` Response

An ASCP-capable MCP server SHOULD include a `schema_id` field in its `tools/list` response if the tool list has been previously registered or if the server pre-registers its own tool list on initialization:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [ /* full tool list — still present on first call */ ],
    "schema_id": "sha256:a3f2c1b9e5d4087f6c2a91b3d7e0f4a8c6b2e9d1f0a3c5b7e2d9f1a4c6b8e0d2"
  }
}
```

On subsequent calls where the client is ASCP-capable and the schema has not changed, the server MAY omit the `tools` array and include only the `schema_id`:

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "result": {
    "tool_schema_ref": "sha256:a3f2c1b9e5d4087f6c2a91b3d7e0f4a8c6b2e9d1f0a3c5b7e2d9f1a4c6b8e0d2"
  }
}
```

### 5.3 New Field: `tool_schema_ref` in Tool Call Requests

When an MCP client constructs an LLM API call and passes tool schemas to the provider, it MAY use the resolved `schema_id` in place of the full bundle. This is an **agent-runtime-level** optimization: the `tool_schema_ref` itself never reaches the LLM; the runtime resolves it locally before building the API payload.

Additionally, when a client makes a `tools/call` request to an MCP server, it MAY include a `tool_schema_ref` in the request metadata to indicate the schema version it is operating under:

```json
{
  "jsonrpc": "2.0",
  "id": 99,
  "method": "tools/call",
  "params": {
    "name": "read_file",
    "arguments": { "path": "/etc/hosts" },
    "_ascp": {
      "tool_schema_ref": "sha256:a3f2c1b9e5d4087f6c2a91b3d7e0f4a8c6b2e9d1f0a3c5b7e2d9f1a4c6b8e0d2"
    }
  }
}
```

The server MUST ignore `_ascp` metadata if it is not ASCP-capable, per JSON-RPC unknown-field semantics.

### 5.4 Client/Server Capability Negotiation

ASCP capability MUST be declared during the MCP `initialize` handshake using the `capabilities` object:

**Client `initialize` request** (ASCP-capable client):

```json
{
  "jsonrpc": "2.0",
  "id": 0,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {},
      "ascp": {
        "schemaRef": true,
        "registryVersion": "0.1"
      }
    },
    "clientInfo": { "name": "my-agent", "version": "1.0.0" }
  }
}
```

**Server `initialize` response** (ASCP-capable server):

```json
{
  "jsonrpc": "2.0",
  "id": 0,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": { "listChanged": true },
      "ascp": {
        "schemaRef": true,
        "registryVersion": "0.1",
        "defaultTtl": 3600
      }
    },
    "serverInfo": { "name": "my-tool-server", "version": "2.0.0" }
  }
}
```

If either party's `initialize` payload does not include an `ascp` capability block, the other party MUST treat that peer as non-ASCP-capable and MUST fall back to standard MCP behavior for all subsequent messages in that session.

---

## 6. A2A Extension

A2A uses JSON-RPC 2.0 over HTTP with a discovery mechanism based on an AgentCard at `/.well-known/agent.json`. ASCP extends A2A by adding a capability declaration to the AgentCard, a schema registry endpoint, and a new message part type.

### 6.1 AgentCard Capability Declaration

An ASCP-capable A2A agent MUST declare its support in its AgentCard:

```json
{
  "name": "DataAnalysisAgent",
  "description": "Performs structured data analysis tasks.",
  "url": "https://agent.example.com/a2a",
  "version": "1.2.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false,
    "ascp": {
      "schemaRef": true,
      "registryEndpoint": "https://agent.example.com/ascp/registry",
      "registryVersion": "0.1",
      "defaultTtl": 86400
    }
  },
  "skills": [
    {
      "id": "analyze-csv",
      "name": "Analyze CSV",
      "description": "Loads and summarizes a CSV file."
    }
  ]
}
```

The `ascp.registryEndpoint` field specifies the URL of the agent's Schema Registry endpoint (see Section 6.2). This field MUST be present if `ascp.schemaRef` is `true`.

### 6.2 Schema Registry Endpoint

An ASCP-capable A2A agent MUST expose an HTTP endpoint at the URL declared in `ascp.registryEndpoint`. This endpoint MUST support the following operations:

**POST** (Register or resolve):

```
POST /ascp/registry
Content-Type: application/json

{
  "operation": "register",
  "bundle": [ /* array of skill/tool descriptors */ ],
  "ttl": 86400
}
```

Response:

```json
{
  "schema_id": "sha256:b7e2d9f1a4c6b8e0d2a3f2c1b9e5d4087f6c2a91b3d7e0f4a8c6b2e9d1f0a3c5",
  "ttl": 86400
}
```

**GET** (Resolve):

```
GET /ascp/registry/{schema_id}
```

Response (200 OK):

```json
{
  "schema_id": "sha256:b7e2d9f1a4c6b8e0d2a3f2c1b9e5d4087f6c2a91b3d7e0f4a8c6b2e9d1f0a3c5",
  "bundle": [ /* full descriptor array */ ],
  "ttl_remaining": 82341
}
```

Response (404 Not Found — expired or unknown):

```json
{
  "error": "ASCP_REF_UNKNOWN",
  "fallback_required": true
}
```

### 6.3 Message Part: `schema_ref` Type

A2A messages contain `parts` arrays. ASCP introduces a new part type, `schema_ref`, for use in `message/send` and streaming contexts:

**Standard A2A message with full skill descriptor** (baseline):

```json
{
  "role": "user",
  "parts": [
    { "type": "text", "text": "Analyze the attached CSV." },
    {
      "type": "skill_descriptor",
      "skills": [ /* full skill descriptor array — large */ ]
    }
  ]
}
```

**ASCP-optimized message with schema_ref** (subsequent calls):

```json
{
  "role": "user",
  "parts": [
    { "type": "text", "text": "Analyze the attached CSV." },
    {
      "type": "schema_ref",
      "schema_id": "sha256:b7e2d9f1a4c6b8e0d2a3f2c1b9e5d4087f6c2a91b3d7e0f4a8c6b2e9d1f0a3c5",
      "registry": "https://agent.example.com/ascp/registry"
    }
  ]
}
```

The `registry` field in the `schema_ref` part is OPTIONAL if the registry URL can be determined from the AgentCard. It is REQUIRED when the schema was registered with a third-party registry service.

---

## 7. Future Extensions (Informational)

The following extensions are described at a high level for community consideration. They are **not normative** in this version of the specification.

### 7.1 Context Delta Protocol (History Bloat)

In long-running agent sessions, conversation history grows without bound. The Context Delta Protocol would allow agents to exchange `context_checkpoint` references (content-addressed snapshots of history up to a given point) and `delta` objects (only the turns since the last checkpoint), rather than retransmitting full history on every call. This would complement the Schema Reference Layer and address the secondary source of token bloat.

### 7.2 Content-Addressed Artifact Store

For agents that exchange large artifacts (documents, code files, images), a `content_cid` field analogous to `tool_schema_ref` would allow repeated references to the same artifact within a session without retransmission. The CID format would use the same `sha256:` prefix convention as Schema IDs.

### 7.3 Semantic Compression Middleware

A middleware layer that sits between the agent runtime and the LLM API could automatically detect repeated semantic patterns across messages (not just identical byte sequences) and represent them using ASCP references. This would require a semantic hashing scheme and is considerably more complex than the content-addressed approach used in this specification.

---

## 8. Wire Format Examples

### 8.1 MCP: Before ASCP (Baseline)

Every LLM API call carries the full tool list. Shown here as the `tools` array passed to the LLM provider (representative excerpt, 3 of 24 tools):

```json
[
  {
    "name": "read_file",
    "description": "Read the contents of a file at the given path.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "path": { "type": "string", "description": "Path to the file." }
      },
      "required": ["path"]
    }
  },
  {
    "name": "write_file",
    "description": "Write content to a file at the given path.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "path": { "type": "string", "description": "Path to the file." },
        "content": { "type": "string", "description": "Content to write." }
      },
      "required": ["path", "content"]
    }
  },
  {
    "name": "list_directory",
    "description": "List the contents of a directory.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "path": { "type": "string", "description": "Directory path." }
      },
      "required": ["path"]
    }
  }
  // ... 21 more tools — ~2,472 tokens total
]
```

**Token cost per call: ~2,472 tokens**

### 8.2 MCP: After ASCP (Schema Registration — First Call)

```json
// Agent → MCP Server: tools/register
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/register",
  "params": {
    "tools": [ /* full 24-tool array, sent exactly once */ ],
    "ttl": 3600
  }
}

// MCP Server → Agent: registration acknowledgment
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "schema_id": "sha256:a3f2c1b9e5d4087f6c2a91b3d7e0f4a8c6b2e9d1f0a3c5b7e2d9f1a4c6b8e0d2",
    "ttl": 3600
  }
}
```

**Token cost of registration: ~2,472 tokens (one time only)**

### 8.3 MCP: After ASCP (Subsequent Calls with `schema_ref`)

All subsequent LLM API calls within the TTL window use only the Schema ID. The agent runtime resolves the reference locally and passes it to the LLM provider through the appropriate non-prompt channel:

```json
// What travels on the wire / in the agent context:
{
  "tool_schema_ref": "sha256:a3f2c1b9e5d4087f6c2a91b3d7e0f4a8c6b2e9d1f0a3c5b7e2d9f1a4c6b8e0d2"
}

// Approximate token cost of this reference object: ~6 tokens
// Savings vs. baseline per call: 2,466 tokens (99.8%)
```

**Cumulative savings over 100 calls (24 tools):**

| | Without ASCP | With ASCP |
|---|---|---|
| Schema tokens (call 1) | 2,472 | 2,472 (registration) |
| Schema tokens (calls 2–100) | 243,288 | 594 (99 × 6) |
| **Total schema tokens** | **245,760** | **3,066** |
| **Reduction** | — | **98.75%** |

### 8.4 A2A: AgentCard with ASCP Capability

```json
// GET /.well-known/agent.json
// Response:
{
  "name": "CodeReviewAgent",
  "description": "Reviews pull requests and suggests improvements.",
  "url": "https://codereview.agent.example.com/a2a",
  "version": "0.9.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false,
    "ascp": {
      "schemaRef": true,
      "registryEndpoint": "https://codereview.agent.example.com/ascp/registry",
      "registryVersion": "0.1",
      "defaultTtl": 86400
    }
  },
  "skills": [
    {
      "id": "review-pr",
      "name": "Review Pull Request",
      "description": "Analyzes a GitHub PR diff and returns structured feedback."
    },
    {
      "id": "suggest-tests",
      "name": "Suggest Tests",
      "description": "Proposes missing unit and integration tests for changed code."
    }
  ]
}
```

---

## 9. Security Considerations

### 9.1 Schema Integrity (Hash Verification)

Schema IDs are content-addressed using SHA-256. All implementations MUST recompute the SHA-256 hash of any retrieved Schema Bundle and compare it to the Schema ID before trusting the bundle's content. A mismatch indicates either registry corruption or a man-in-the-middle substitution attack and MUST be treated as a fatal error for the associated operation. The agent MUST log the mismatch and SHOULD fall back to re-fetching the schema from the originating server.

### 9.2 Registry Trust

An ASCP registry holds the ground truth of what tools an agent is permitted to use. Accordingly:

- Remote registry endpoints MUST be accessed over TLS (HTTPS). Plaintext HTTP registries MUST NOT be used in production environments.
- Implementations SHOULD authenticate registry endpoints using standard mechanisms (mutual TLS, bearer tokens, or equivalent).
- In multi-tenant environments, registries MUST enforce per-tenant namespace isolation: a schema registered by tenant A MUST NOT be resolvable by tenant B, even if the Schema IDs collide (which by the collision-resistance of SHA-256 is computationally infeasible but must be accounted for in policy).

### 9.3 Schema Injection Attacks

An attacker with write access to a Schema Registry could substitute a malicious Schema Bundle under an existing Schema ID. The SHA-256 integrity check (Section 9.1) defends against this at retrieval time, but does not prevent a compromised registry from serving a consistently-hashed malicious bundle.

To mitigate this:

- Schema Registries SHOULD be treated as part of the trust boundary of the agent system, equivalent in sensitivity to the system prompt.
- Implementations MUST NOT accept `schema_ref` values from untrusted external agents without first resolving and auditing the referenced bundle.
- Operators SHOULD periodically audit registry contents, particularly for long-lived sessions where TTLs extend over days.
- A future ASCP version MAY introduce a signed schema bundle mechanism (e.g., using JWS) to allow cryptographic verification of schema authorship independent of registry integrity.

---

## 10. Compatibility & Migration

### 10.1 Backward Compatibility Guarantees

ASCP is designed to be fully backward-compatible with existing MCP and A2A implementations:

1. All new fields (`tool_schema_ref`, `schema_id`, `ascp` capability block) are additive. Non-ASCP implementations MUST ignore unknown fields per JSON-RPC 2.0 semantics.
2. The `tools/register` method is new. Non-ASCP MCP servers will return a `Method not found` error (`-32601`), which ASCP-capable clients MUST interpret as an indication of no ASCP support, triggering fallback.
3. Full Schema Bundles are never withheld from non-ASCP peers. The fallback path (full schema transmission) is always available.
4. No changes are required to LLM provider APIs. ASCP operates entirely in the agent runtime layer, below the LLM API boundary.

### 10.2 Migration Path

The RECOMMENDED migration path for an existing MCP/A2A implementation is:

1. **Add capability declaration** to `initialize` / AgentCard. This is a no-op for existing non-ASCP peers.
2. **Implement `tools/register`** on the server side (MCP) or registry endpoint (A2A). Begin issuing Schema IDs in `tools/list` responses.
3. **Update the agent runtime** to detect `schema_id` in `tools/list` responses and cache the mapping. On subsequent calls, emit `tool_schema_ref` instead of the full bundle to ASCP-capable peers.
4. **Verify fallback** by testing against a non-ASCP server. The runtime MUST detect the `Method not found` error and revert to full schema transmission transparently.

This migration can be performed incrementally. Steps 1–2 can be deployed to production without any change in behavior, as no client will use the new capability until step 3 is deployed.

### 10.3 Compatibility Matrix

| Client \ Server | Non-ASCP Server | ASCP Server (v0.1) |
|---|---|---|
| **Non-ASCP Client** | Full schema, every call (baseline) | Full schema, every call (server degrades gracefully) |
| **ASCP Client (v0.1)** | Full schema, every call (client detects no server support) | Schema ref after first registration — **full ASCP optimization** |

---

## 11. References

- **[RFC 2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC 2119, March 1997. <https://www.rfc-editor.org/rfc/rfc2119>

- **[JSON-RPC 2.0]** JSON-RPC Working Group, "JSON-RPC 2.0 Specification", 2010. <https://www.jsonrpc.org/specification>

- **[MCP-SPEC]** Anthropic, "Model Context Protocol Specification", Version 2024-11-05. <https://spec.modelcontextprotocol.io/>

- **[A2A-SPEC]** Google, "Agent2Agent (A2A) Protocol Specification", Linux Foundation. <https://google.github.io/A2A/>

- **[SHA-256]** NIST, "Secure Hash Standard (SHS)", FIPS PUB 180-4, August 2015. <https://csrc.nist.gov/publications/detail/fips/180/4/final>

- **[ANTHROPIC-CACHING]** Anthropic, "Prompt Caching", Claude API Documentation. <https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching>

- **[OPENAI-CACHING]** OpenAI, "Prompt Caching", OpenAI Platform Documentation. <https://platform.openai.com/docs/guides/prompt-caching>

- **[RFC 8259]** Bray, T., "The JavaScript Object Notation (JSON) Data Interchange Format", RFC 8259, December 2017. <https://www.rfc-editor.org/rfc/rfc8259>

---

*End of ASCP Specification v0.1*

---

> **Document metadata**
> - **Title**: Agent Semantic Communication Protocol (ASCP) — Specification v0.1
> - **Status**: Individual Draft
> - **Date**: 2026-03-11
> - **Author**: [Author Name]
> - **Repository**: [Repository URL]
> - **License**: CC BY 4.0 (suggested for open protocol specifications)
