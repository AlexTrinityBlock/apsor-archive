"""Runtime builds ordered chains and only wraps when a backup exists."""

import asyncio
from typing import Any

from cryptography.fernet import Fernet

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
) -> ChatProviderConfigModel:
    return ChatProviderConfigModel(
        provider="deepseek",
        label=f"chat {priority}",
        model=model,
        base_url="https://api.deepseek.com",
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
