"""Runtime builds ordered chains and only wraps when a backup exists."""

import asyncio
from typing import Any

from cryptography.fernet import Fernet

from app.infrastructure.ai.anthropic_client import AnthropicClient
from app.infrastructure.ai.deepseek_client import DeepSeekClient, NullTextGenerator
from app.infrastructure.ai.fallbacks import FallbackEmbedder, FallbackTextGenerator
from app.infrastructure.ai.provider_factory import (
    ProviderFactory,
    provider_defaults_from_settings,
)
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.config.settings import Settings
from app.infrastructure.security.secret_cipher import SecretCipher
from app.module.knowledge.model.provider_config_model import (
    ChatProviderConfigModel,
    EmbeddingProviderConfigModel,
)
from app.module.knowledge.protocol.provider_config import ProviderConfig


class _ChainRepository:
    def __init__(self, chains: dict[str, list[Any]]) -> None:
        self.chains = chains

    async def list_active_chain(self, spec: Any) -> list[Any]:
        return self.chains.get(spec.capability, [])

    async def get_active(self, spec: Any) -> Any:
        chain = self.chains.get(spec.capability, [])
        return chain[0] if chain else None


def _chat_row(
    *,
    ciphertext: str | None,
    priority: int,
    model: str = "deepseek-flash",
    provider: str = "deepseek",
    base_url: str = "https://api.deepseek.com",
) -> ChatProviderConfigModel:
    return ChatProviderConfigModel(
        provider=provider,
        label=f"chat {priority}",
        model=model,
        base_url=base_url,
        api_key_ciphertext=ciphertext,
        dimension=None,
        is_active=True,
        priority=priority,
    )


def test_runtime_wraps_a_multi_row_chain_and_keeps_the_primary_config() -> None:
    settings = Settings(deepseek_api_key="ds-environment-key")
    cipher = SecretCipher(Fernet.generate_key())
    repository = _ChainRepository(
        {
            "chat": [
                _chat_row(ciphertext=None, priority=0, model="deepseek-chat"),
                _chat_row(ciphertext=cipher.encrypt("sk-backup-key"), priority=1),
            ]
        }
    )
    runtime = AiRuntime(
        builder=ProviderFactory(settings),
        cipher=cipher,
        defaults=provider_defaults_from_settings(settings),
    )

    asyncio.run(runtime.reload(repository))  # type: ignore[arg-type]

    assert [config.provider for config in runtime.chat_chain] == [
        "deepseek",
        "deepseek",
    ]
    assert runtime.chat_config is runtime.chat_chain[0]
    assert runtime.chat_config.api_key == "ds-environment-key"
    assert runtime.chat_chain[1].api_key == "sk-backup-key"
    assert isinstance(runtime.text_generator, FallbackTextGenerator)
    assert runtime.text_generator.configured is True


def test_runtime_keeps_the_single_client_path_for_one_row() -> None:
    settings = Settings(deepseek_api_key="ds-environment-key")
    repository = _ChainRepository(
        {
            "chat": [_chat_row(ciphertext=None, priority=0)],
        }
    )
    runtime = AiRuntime(
        builder=ProviderFactory(settings),
        cipher=SecretCipher(Fernet.generate_key()),
        defaults=provider_defaults_from_settings(settings),
    )

    asyncio.run(runtime.reload(repository))  # type: ignore[arg-type]

    assert len(runtime.chat_chain) == 1
    assert isinstance(runtime.text_generator, DeepSeekClient)


def test_runtime_uses_the_environment_only_when_it_is_enabled() -> None:
    settings = Settings(deepseek_api_key=None, embedding_provider="hashing")
    runtime = AiRuntime(
        builder=ProviderFactory(settings),
        cipher=SecretCipher(Fernet.generate_key()),
        defaults=provider_defaults_from_settings(settings),
    )

    asyncio.run(runtime.reload(_ChainRepository({})))  # type: ignore[arg-type]

    assert runtime.chat_chain == ()
    assert isinstance(runtime.text_generator, NullTextGenerator)
    # Hashing needs no credential, so the environment default remains a chain.
    assert [config.provider for config in runtime.embedding_chain] == ["hashing"]


def test_embedding_chain_skips_a_different_vector_space_defensively() -> None:
    settings = Settings(embedding_provider="hashing")
    repository = _ChainRepository(
        {
            "embedding": [
                EmbeddingProviderConfigModel(
                    provider="hashing",
                    label="primary",
                    model="apsor-hash-384",
                    dimension=384,
                    is_active=True,
                    priority=0,
                ),
                EmbeddingProviderConfigModel(
                    provider="hashing",
                    label="backup",
                    model="apsor-hash-384",
                    dimension=384,
                    is_active=True,
                    priority=1,
                ),
                EmbeddingProviderConfigModel(
                    provider="hashing",
                    label="wrong",
                    model="apsor-hash-768",
                    dimension=768,
                    is_active=True,
                    priority=2,
                ),
            ]
        }
    )
    runtime = AiRuntime(
        builder=ProviderFactory(settings),
        cipher=SecretCipher(Fernet.generate_key()),
        defaults=provider_defaults_from_settings(settings),
    )

    asyncio.run(runtime.reload(repository))  # type: ignore[arg-type]

    assert isinstance(runtime.embedder, FallbackEmbedder)
    assert runtime.embedder.model_name == "apsor-hash-384"
    assert runtime.embedder.dimension == 384


def test_row_config_carries_row_identity_and_no_effort() -> None:
    settings = Settings(deepseek_api_key="ds-environment-key")
    cipher = SecretCipher(Fernet.generate_key())
    row = _chat_row(ciphertext=cipher.encrypt("sk-row-key"), priority=0)
    row.id = 41
    row.max_output_tokens = 32_000
    runtime = AiRuntime(
        builder=ProviderFactory(settings),
        cipher=cipher,
        defaults=provider_defaults_from_settings(settings),
    )

    asyncio.run(runtime.reload(_ChainRepository({"chat": [row]})))  # type: ignore[arg-type]

    config = runtime.chat_chain[0]
    assert config.row_id == 41
    # Effort is a per-account assignment, never read from the shared row.
    assert config.reasoning_effort is None
    assert config.max_output_tokens == 32_000
    assert config.api_key == "sk-row-key"


def test_environment_default_has_no_row_identity() -> None:
    settings = Settings(deepseek_api_key="ds-environment-key")
    runtime = AiRuntime(
        builder=ProviderFactory(settings),
        cipher=SecretCipher(Fernet.generate_key()),
        defaults=provider_defaults_from_settings(settings),
    )

    assert runtime.chat_config.row_id is None
    assert runtime.chat_config.reasoning_effort is None
    assert runtime.chat_config.api_key == "ds-environment-key"


def test_anthropic_row_without_ciphertext_gets_only_the_anthropic_key() -> None:
    settings = Settings(
        deepseek_api_key="ds-environment-key",
        anthropic_api_key="an-environment-key",
    )
    row = _chat_row(
        ciphertext=None,
        priority=0,
        provider="anthropic",
        model="claude-haiku-5-5",
        base_url="https://api.anthropic.com",
    )
    runtime = AiRuntime(
        builder=ProviderFactory(settings),
        cipher=SecretCipher(Fernet.generate_key()),
        defaults=provider_defaults_from_settings(settings),
    )

    asyncio.run(runtime.reload(_ChainRepository({"chat": [row]})))  # type: ignore[arg-type]

    config = runtime.chat_chain[0]
    assert config.api_key == "an-environment-key"
    assert config.api_key != "ds-environment-key"
    assert isinstance(runtime.text_generator, AnthropicClient)


def test_decryption_failure_stays_keyless_instead_of_using_the_environment() -> None:
    settings = Settings(deepseek_api_key="ds-environment-key")
    row = _chat_row(ciphertext="not-a-valid-fernet-token", priority=0)
    runtime = AiRuntime(
        builder=ProviderFactory(settings),
        cipher=SecretCipher(Fernet.generate_key()),
        defaults=provider_defaults_from_settings(settings),
    )

    asyncio.run(runtime.reload(_ChainRepository({"chat": [row]})))  # type: ignore[arg-type]

    config = runtime.chat_chain[0]
    # The row is active but has no usable key; falling back to the deployment
    # key would hide the corrupted ciphertext.
    assert config.api_key is None
    assert config.enabled is True
    assert isinstance(runtime.text_generator, NullTextGenerator)


def test_factory_passes_effort_and_row_output_cap_to_the_clients() -> None:
    settings = Settings(anthropic_api_key="an-key", deepseek_api_key="ds-key")
    factory = ProviderFactory(settings)

    anthropic_config = ProviderConfig(
        capability="chat",
        provider="anthropic",
        label="claude",
        model="claude-haiku-5-5",
        base_url="https://api.anthropic.com",
        api_key="an-key",
        dimension=None,
        enabled=True,
        source="database",
        reasoning_effort="low",
        max_output_tokens=32_000,
    )
    anthropic = factory.build_text_generator(anthropic_config)
    assert isinstance(anthropic, AnthropicClient)
    assert anthropic.reasoning_effort == "low"
    assert anthropic.max_output_tokens == 32_000
    assert anthropic.max_tokens == settings.anthropic_max_tokens
    assert anthropic.anthropic_version == settings.anthropic_version

    deepseek_config = anthropic_config.model_copy(
        update={
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "api_key": "ds-key",
            "reasoning_effort": "max",
        }
    )
    deepseek = factory.build_text_generator(deepseek_config)
    assert isinstance(deepseek, DeepSeekClient)
    assert deepseek.reasoning_effort == "max"
    # DeepSeek keeps its deployment caps; the row cap is Anthropic-only.
    assert deepseek.chat_max_tokens == settings.deepseek_chat_max_tokens
