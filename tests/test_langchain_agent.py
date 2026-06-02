from app.agent.langchain_agent import call_mcp_tool, close_mcp_clients, get_mcp_client, reset_tool_call_state, should_skip_search


def test_mcp_client_cache_reuses_clients() -> None:
    close_mcp_clients()
    first = get_mcp_client("http://127.0.0.1:8765")
    second = get_mcp_client("http://127.0.0.1:8765/mcp")

    assert first is second
    close_mcp_clients()


def test_should_skip_search_for_trivial_prompts() -> None:
    assert should_skip_search("24*7")
    assert should_skip_search("你好")
    assert should_skip_search("")


def test_should_allow_search_for_real_retrieval_queries() -> None:
    assert not should_skip_search("这个 demo 如何使用 MCP 做 RAG")
    assert not should_skip_search("LangChain create_react_agent 官方用法")


def test_call_mcp_tool_skips_duplicate_calls(monkeypatch) -> None:
    class FakeClient:
        calls = 0

        def call_tool(self, name: str, arguments: dict):
            self.calls += 1
            return {"name": name, "arguments": arguments}

    fake_client = FakeClient()
    monkeypatch.setattr("app.agent.langchain_agent.get_mcp_client", lambda server_url=None: fake_client)

    reset_tool_call_state()
    first = call_mcp_tool("calculate", {"expression": "24*7"})
    second = call_mcp_tool("calculate", {"expression": "24*7"})

    assert "result" not in first
    assert "skipped" in second
    assert fake_client.calls == 1
