"""Web provider defaults and DeepSeek wiring, without external requests.

Both web search and web fetch select DeepSeek first, then Tavily, then Exa.
A saved database row still wins, but a row without its own key falls back to
the environment key for that provider.
"""

import asyncio
from typing import Any, cast

from app.infrastructure.ai.provider_factory import (
    ProviderFactory,
    provider_defaults_from_settings,
)
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.config.settings import Settings
from app.infrastructure.web.deepseek_client import DeepSeekWebClient
from app.module.agent.dependencies import _available_web_provider
from app.module.knowledge.domain.provider_config_domain import (
    CAPABILITY_WEB_FETCH,
    CAPABILITY_WEB_SEARCH,
)
from app.module.knowledge.model.provider_config_model import (
    WebSearchProviderConfigModel,
)
from app.module.knowledge.protocol.provider_config import ProviderConfig
from app.module.web_research.dependencies import WebClientFactory


class _Repository:
    """Return only the configured active row for each capability."""

    def __init__(self, rows: dict[Any, Any]) -> None:
        self.rows = rows

    async def list_active_chain(self, spec: Any) -> list[Any]:
        row = self.rows.get(spec.capability)
        return [row] if row is not None else []

    async def get_active(self, spec: Any) -> Any:
        return self.rows.get(spec.capability)


def test_deepseek_only_environment_selects_deepseek_for_both_web_capabilities() -> None:
    defaults = provider_defaults_from_settings(
        Settings(
            tavily_api_key=None,
            exa_api_key=None,
            deepseek_api_key="ds-test-key",
        )
    )

    for provider, base_url, key in (
        (defaults.web_search_provider, defaults.web_search_base_url, defaults.web_search_api_key),
        (defaults.web_fetch_provider, defaults.web_fetch_base_url, defaults.web_fetch_api_key),
    ):
        assert provider == "deepseek"
        assert base_url == "https://api.deepseek.com"
        assert key == "ds-test-key"


def test_tavily_and_deepseek_keys_default_both_capabilities_to_deepseek() -> None:
    defaults = provider_defaults_from_settings(
        Settings(
            tavily_api_key="tvly-test",
            exa_api_key=None,
            deepseek_api_key="ds-test-key",
        )
    )

    assert defaults.web_search_provider == "deepseek"
    assert defaults.web_search_api_key == "ds-test-key"
    assert defaults.web_fetch_provider == "deepseek"
    assert defaults.web_fetch_api_key == "ds-test-key"


def test_exa_and_deepseek_keys_default_both_capabilities_to_deepseek() -> None:
    defaults = provider_defaults_from_settings(
        Settings(
            tavily_api_key=None,
            exa_api_key="exa-test",
            deepseek_api_key="ds-test-key",
        )
    )

    assert defaults.web_search_provider == "deepseek"
    assert defaults.web_fetch_provider == "deepseek"


def test_tavily_and_exa_without_deepseek_default_to_tavily() -> None:
    defaults = provider_defaults_from_settings(
        Settings(
            tavily_api_key="tvly-test",
            exa_api_key="exa-test",
            deepseek_api_key=None,
        )
    )

    assert defaults.web_search_provider == "tavily"
    assert defaults.web_fetch_provider == "tavily"


def test_no_web_key_keeps_the_capabilities_disabled() -> None:
    defaults = provider_defaults_from_settings(
        Settings(tavily_api_key=None, exa_api_key=None, deepseek_api_key=None)
    )

    assert defaults.web_search_provider == "none"
    assert defaults.web_fetch_provider == "none"
    assert defaults.web_search_api_key is None


def test_deepseek_database_row_without_a_key_uses_the_environment_key() -> None:
    settings = Settings(deepseek_api_key="ds-test-key")
    defaults = provider_defaults_from_settings(settings)
    runtime = AiRuntime(
        builder=ProviderFactory(settings),
        cipher=cast(Any, None),
        defaults=defaults,
    )
    row = WebSearchProviderConfigModel(
        provider="deepseek",
        label="DeepSeek search",
        base_url="https://api.deepseek.com",
        model=None,
        dimension=None,
        is_active=True,
    )

    async def reload_runtime() -> None:
        await runtime.reload(
            cast(Any, _Repository({CAPABILITY_WEB_SEARCH: row})),
        )

    asyncio.run(reload_runtime())

    assert runtime.web_search_config.provider == "deepseek"
    assert runtime.web_search_config.api_key == "ds-test-key"
    assert runtime.web_search_client.provider == "deepseek"
    assert runtime.web_search_client.configured is True


def test_provider_factory_ignores_stale_web_defaults_for_deepseek() -> None:
    settings = Settings(deepseek_api_key="ds-test-key")
    factory = ProviderFactory(settings)
    config = ProviderConfig(
        capability=CAPABILITY_WEB_FETCH,
        provider="deepseek",
        label="DeepSeek fetch",
        model=None,
        base_url="https://api.exa.ai",
        api_key="ds-test-key",
        dimension=None,
        enabled=True,
        source="database",
    )

    client = factory.build_web_client(config)

    assert isinstance(client, DeepSeekWebClient)
    assert client.provider == "deepseek"
    assert client.base_url == "https://api.deepseek.com"
    assert client.timeout_seconds == settings.web_fetch_timeout_seconds


def test_web_client_factory_builds_deepseek_search_and_fetch() -> None:
    settings = Settings(web_search_timeout_seconds=11, web_fetch_timeout_seconds=22)
    factory = WebClientFactory(settings)
    config = ProviderConfig(
        capability=CAPABILITY_WEB_SEARCH,
        provider="deepseek",
        label="DeepSeek",
        model=None,
        base_url="https://api.tavily.com",
        api_key="ds-test-key",
        dimension=None,
        enabled=True,
        source="database",
    )

    search = factory.build_search(config)
    fetch = factory.build_fetch(config)

    assert isinstance(search, DeepSeekWebClient)
    assert isinstance(fetch, DeepSeekWebClient)
    assert search.base_url == "https://api.deepseek.com"
    assert fetch.base_url == "https://api.deepseek.com"
    assert search.timeout_seconds == 11.0
    assert fetch.timeout_seconds == 22.0


def test_agent_treats_deepseek_as_an_available_web_provider() -> None:
    config = ProviderConfig(
        capability=CAPABILITY_WEB_SEARCH,
        provider="deepseek",
        label="DeepSeek",
        model=None,
        base_url="https://api.deepseek.com",
        api_key="ds-test-key",
        dimension=None,
        enabled=True,
        source="database",
    )

    assert _available_web_provider(config) == "deepseek"
