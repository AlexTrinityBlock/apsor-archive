"""The companion story configuration provider.

Every tunable of companion stories (unlock runs, story-moment cadence, recall
thresholds and bonuses, self-query phrases, and the guidance texts the model
reads) lives in one :class:`CompanionStoryConfig` value. Services ask a provider
for it per operation instead of reading module constants, so root
administration can store and edit the live values. Until that store exists,
:class:`StaticStoryConfigProvider` serves the seed defaults.
"""

from app.module.companion.domain.story_domain import DEFAULT_STORY_CONFIG, CompanionStoryConfig


class StaticStoryConfigProvider:
    """Serve one fixed configuration (the seed defaults unless given one)."""

    def __init__(self, config: CompanionStoryConfig = DEFAULT_STORY_CONFIG) -> None:
        self.config = config

    async def load(self) -> CompanionStoryConfig:
        """Return the configuration."""
        return self.config


__all__ = ["StaticStoryConfigProvider"]
