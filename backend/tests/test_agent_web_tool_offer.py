"""Web tools are offered to the model only when the account can use them."""

import asyncio

from fastapi.testclient import TestClient

from app.module.agent.domain.agent_domain import ProviderContext
from app.module.agent.domain.agent_status_domain import AgentStatus, render_agent_status
from app.module.agent.domain.tool_catalog import tool_definitions
from app.module.agent.service.agent_service import AgentService
from app.module.agent.test.fake_chat_generator import FakeChatGenerator, text_result


class _Quota:
    def __init__(self, *, search: bool, fetch: bool) -> None:
        self.search = search
        self.fetch = fetch
        self.checks = 0

    async def chat_allowed(self) -> bool:
        return True

    async def web_search_allowed(self) -> bool:
        self.checks += 1
        return self.search

    async def web_fetch_allowed(self) -> bool:
        self.checks += 1
        return self.fetch


def _service(*, search: str, fetch: str, quota: _Quota | None) -> AgentService:
    """Only the attributes the tool-offer helpers read; no database needed."""
    service = object.__new__(AgentService)
    service.web_search_provider = search
    service.web_fetch_provider = fetch
    service.quota = quota
    service._unavailable_tools = {}
    service._withheld_tools = ()
    return service


def _context() -> ProviderContext:
    return ProviderContext(
        system_message={"role": "system", "content": ""},
        tools=tool_definitions(),
        messages=[],
        source_entry_ids=[],
        cache_prefix_hash="x",
    )


def _names(context: ProviderContext) -> set[str]:
    return {tool["function"]["name"] for tool in context.tools}


def test_disabled_account_is_not_offered_web_tools() -> None:
    quota = _Quota(search=False, fetch=False)
    service = _service(search="tavily", fetch="tavily", quota=quota)
    offered = asyncio.run(service._offered_tools_only(_context(), run_id=1))
    assert "web_search" not in _names(offered)
    assert "web_fetch" not in _names(offered)
    assert "search_knowledge" in _names(offered)
    assert service._withheld_tools == ("web_fetch", "web_search")
    # Resolved once per run.
    asyncio.run(service._offered_tools_only(_context(), run_id=1))
    assert quota.checks == 2


def test_enabled_account_is_offered_web_tools() -> None:
    service = _service(search="tavily", fetch="exa", quota=_Quota(search=True, fetch=True))
    offered = asyncio.run(service._offered_tools_only(_context(), run_id=1))
    assert {"web_search", "web_fetch"} <= _names(offered)
    assert service._withheld_tools == ()


def test_each_web_tool_follows_its_own_toggle_and_provider() -> None:
    service = _service(search="tavily", fetch="tavily", quota=_Quota(search=True, fetch=False))
    names = _names(asyncio.run(service._offered_tools_only(_context(), run_id=1)))
    assert "web_search" in names and "web_fetch" not in names

    unconfigured = _service(search="none", fetch="tavily", quota=None)
    names = _names(asyncio.run(unconfigured._offered_tools_only(_context(), run_id=1)))
    assert "web_search" not in names and "web_fetch" in names


def test_status_block_names_withheld_tools() -> None:
    status = AgentStatus(
        max_tool_result_chars=1,
        max_page_context_chars=1,
        max_expression_chars=1,
        output_limit_tokens=0,
        unavailable_tools=("web_search", "web_fetch"),
    )
    assert 'unavailable_tools="web_fetch,web_search"' in render_agent_status(status)
    plain = AgentStatus(
        max_tool_result_chars=1,
        max_page_context_chars=1,
        max_expression_chars=1,
        output_limit_tokens=0,
    )
    assert "unavailable_tools" not in render_agent_status(plain)


def test_run_without_web_providers_offers_no_web_tools(client: TestClient) -> None:
    """The default test deployment has no web provider, so none are offered."""
    chat = FakeChatGenerator([text_result("Done.")])
    client.app.state.agent_chat_generator = chat
    conversation = client.post("/api/v1/agent/conversations", json={"title": "Offer"})
    assert conversation.status_code == 201, conversation.text
    turn = client.post(
        f"/api/v1/agent/conversations/{conversation.json()['id']}/messages",
        json={"content": "hello"},
        headers={"Accept": "application/json"},
    )
    assert turn.status_code == 200, turn.text
    offered = {tool["function"]["name"] for tool in chat.requests[0].tools}
    assert "search_knowledge" in offered
    assert not {"web_search", "web_fetch"} & offered
