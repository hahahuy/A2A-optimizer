import unittest

from ascp.adapter import A2AAdapter, MCPAdapter


SAMPLE_TOOLS = [
    {"name": "get_weather", "description": "Get weather", "inputSchema": {"type": "object"}},
    {"name": "send_email", "description": "Send email", "inputSchema": {"type": "object"}},
]


class TestMCPAdapterCapabilities(unittest.TestCase):
    def setUp(self):
        self.adapter = MCPAdapter()

    # Test 2
    def test_build_initialize_capabilities_has_schema_ref(self):
        caps = self.adapter.build_initialize_capabilities()
        self.assertTrue(caps["ascp"]["schemaRef"])

    # Test 3
    def test_is_ascp_capable_true(self):
        params = {"capabilities": {"ascp": {"schemaRef": True}}}
        self.assertTrue(self.adapter.is_ascp_capable(params))

    def test_is_ascp_capable_false_missing(self):
        self.assertFalse(self.adapter.is_ascp_capable({}))

    def test_is_ascp_capable_false_false_value(self):
        params = {"capabilities": {"ascp": {"schemaRef": False}}}
        self.assertFalse(self.adapter.is_ascp_capable(params))


class TestMCPAdapterRegister(unittest.TestCase):
    def setUp(self):
        self.adapter = MCPAdapter()

    # Test 4
    def test_tools_register_request_structure(self):
        req = self.adapter.tools_register_request(SAMPLE_TOOLS)
        self.assertEqual(req["jsonrpc"], "2.0")
        self.assertIsInstance(req["id"], int)
        self.assertEqual(req["method"], "tools/register")
        self.assertEqual(req["params"]["tools"], SAMPLE_TOOLS)
        self.assertIn("ttl", req["params"])

    def test_tools_register_request_default_ttl(self):
        req = self.adapter.tools_register_request(SAMPLE_TOOLS)
        self.assertEqual(req["params"]["ttl"], 3600)

    def test_tools_register_request_custom_ttl(self):
        req = self.adapter.tools_register_request(SAMPLE_TOOLS, ttl=7200)
        self.assertEqual(req["params"]["ttl"], 7200)

    def test_tools_register_request_stores_schema_id(self):
        self.adapter.tools_register_request(SAMPLE_TOOLS)
        self.assertIsNotNone(self.adapter._schema_id)

    # Test 5
    def test_tools_register_response_structure(self):
        self.adapter.tools_register_request(SAMPLE_TOOLS)
        resp = self.adapter.tools_register_response(self.adapter._schema_id, 3600)
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertIsInstance(resp["id"], int)
        self.assertIn("result", resp)
        self.assertEqual(resp["result"]["schema_id"], self.adapter._schema_id)
        self.assertEqual(resp["result"]["ttl"], 3600)


class TestMCPAdapterToolsList(unittest.TestCase):
    def setUp(self):
        self.adapter = MCPAdapter()

    # Test 6
    def test_tools_list_response_use_ref_after_registration(self):
        self.adapter.tools_register_request(SAMPLE_TOOLS)
        resp = self.adapter.tools_list_response(SAMPLE_TOOLS, use_ref=True)
        self.assertIn("tool_schema_ref", resp["result"])
        self.assertEqual(resp["result"]["tool_schema_ref"], self.adapter._schema_id)

    # Test 7
    def test_tools_list_response_no_ref_always_full(self):
        self.adapter.tools_register_request(SAMPLE_TOOLS)
        resp = self.adapter.tools_list_response(SAMPLE_TOOLS, use_ref=False)
        self.assertIn("tools", resp["result"])
        self.assertEqual(resp["result"]["tools"], SAMPLE_TOOLS)

    def test_tools_list_response_full_when_not_registered(self):
        resp = self.adapter.tools_list_response(SAMPLE_TOOLS, use_ref=True)
        self.assertIn("tools", resp["result"])
        self.assertEqual(resp["result"]["tools"], SAMPLE_TOOLS)


class TestMCPAdapterToolCall(unittest.TestCase):
    def setUp(self):
        self.adapter = MCPAdapter()

    # Test 8
    def test_tool_call_request_with_schema_id_has_ascp(self):
        req = self.adapter.tool_call_request(
            "get_weather", {"city": "Hanoi"}, schema_id="sha256:abc123"
        )
        self.assertEqual(req["jsonrpc"], "2.0")
        self.assertEqual(req["method"], "tools/call")
        self.assertEqual(req["params"]["name"], "get_weather")
        self.assertEqual(req["params"]["arguments"], {"city": "Hanoi"})
        self.assertIn("_ascp", req["params"])
        self.assertEqual(req["params"]["_ascp"]["tool_schema_ref"], "sha256:abc123")

    # Test 9
    def test_tool_call_request_without_schema_id_no_ascp(self):
        req = self.adapter.tool_call_request("get_weather", {"city": "Hanoi"})
        self.assertNotIn("_ascp", req["params"])

    def test_tool_call_request_ids_increment(self):
        req1 = self.adapter.tool_call_request("a", {})
        req2 = self.adapter.tool_call_request("b", {})
        self.assertGreater(req2["id"], req1["id"])

    # Test 10
    def test_handle_ref_unknown(self):
        resp = self.adapter.handle_ref_unknown("sha256:deadbeef")
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertIsInstance(resp["id"], int)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32001)
        self.assertEqual(resp["error"]["message"], "ASCP_REF_UNKNOWN")
        self.assertEqual(resp["error"]["data"]["schema_id"], "sha256:deadbeef")
        self.assertTrue(resp["error"]["data"]["fallback_required"])


class TestA2AAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = A2AAdapter(base_url="https://agent.example.com")

    # Test 11
    def test_agent_card_has_ascp_capabilities(self):
        card = self.adapter.agent_card(
            "WeatherBot",
            "Provides weather data",
            [{"name": "get_weather"}],
        )
        self.assertTrue(card["capabilities"]["ascp"]["schemaRef"])
        self.assertIn("registryEndpoint", card["capabilities"]["ascp"])
        self.assertIn("registryVersion", card["capabilities"]["ascp"])
        self.assertEqual(card["capabilities"]["ascp"]["defaultTtl"], 86400)

    def test_agent_card_basic_fields(self):
        card = self.adapter.agent_card("MyBot", "desc", [])
        self.assertEqual(card["name"], "MyBot")
        self.assertEqual(card["description"], "desc")
        self.assertIn("url", card)

    # Test 12
    def test_schema_ref_part(self):
        part = self.adapter.schema_ref_part("sha256:abc")
        self.assertEqual(part["type"], "schema_ref")
        self.assertEqual(part["schema_id"], "sha256:abc")
        self.assertIn("registry", part)
        self.assertIn("/ascp/registry", part["registry"])

    # Test 13
    def test_send_message_with_ref_parts(self):
        msg = self.adapter.send_message_with_ref("Hello", "sha256:abc")
        self.assertEqual(msg["role"], "user")
        parts = msg["parts"]
        self.assertEqual(len(parts), 2)
        text_part = next(p for p in parts if p.get("type") == "text")
        ref_part = next(p for p in parts if p.get("type") == "schema_ref")
        self.assertEqual(text_part["text"], "Hello")
        self.assertEqual(ref_part["schema_id"], "sha256:abc")

    # Test 14
    def test_is_ascp_capable_true(self):
        card = {"capabilities": {"ascp": {"schemaRef": True}}}
        self.assertTrue(self.adapter.is_ascp_capable(card))

    def test_is_ascp_capable_false(self):
        self.assertFalse(self.adapter.is_ascp_capable({}))
        self.assertFalse(self.adapter.is_ascp_capable({"capabilities": {}}))
        card = {"capabilities": {"ascp": {"schemaRef": False}}}
        self.assertFalse(self.adapter.is_ascp_capable(card))


class TestEndToEndMCPHandshake(unittest.TestCase):
    # Test 15
    def test_full_handshake(self):
        adapter = MCPAdapter()

        # Step 1: register tools
        reg_req = adapter.tools_register_request(SAMPLE_TOOLS, ttl=3600)
        self.assertEqual(reg_req["method"], "tools/register")

        # Step 2: simulate server response with schema_id
        schema_id = adapter._schema_id
        reg_resp = adapter.tools_register_response(schema_id, 3600)
        self.assertEqual(reg_resp["result"]["schema_id"], schema_id)

        # Step 3: second tools/list call uses ref
        list_resp = adapter.tools_list_response(SAMPLE_TOOLS, use_ref=True)
        self.assertIn("tool_schema_ref", list_resp["result"])
        ref_id = list_resp["result"]["tool_schema_ref"]
        self.assertEqual(ref_id, schema_id)

        # Step 4: verify schema_id resolves in registry
        resolved = adapter.registry.resolve(ref_id)
        self.assertEqual(resolved, SAMPLE_TOOLS)


if __name__ == "__main__":
    unittest.main()
