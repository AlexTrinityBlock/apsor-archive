"""The one policy for when a companion's own memories enter a run.

Every input site of a run reaches the companion through
:meth:`CompanionContextContributor.contribute` (the agent slice adapts its
``ContextSignal`` onto these plain arguments in its composition root):

- **The user's message** — a question about the librarian itself ("tell me
  about yourself", a librarian's name, "your past") is answered first with the
  next untold fragments; otherwise a paced story moment is offered when one is
  due; otherwise nothing. The message never draws topical asides, so ordinary
  questions are not decorated with lore before any evidence is read.
- **Page context and attachment names** — semantic, topical recall against the
  page the person is viewing or the names of what they attached.
- **Tool results** — semantic, topical recall against the result (never for
  ``search_knowledge``, which searches only the person's archive).

Nothing is locked: each memory carries a weight the librarian judges for
herself, and the block tells her how long the two of them have known each
other.

Every offer is capped per run (``max_contributions_per_run``), never repeats a
fragment already offered in the run, and is recorded in the progress table by
the recall service. Thresholds, cadence, and guidance come from the config
provider; this module holds no story wording.
"""

from typing import Literal

from app.module.companion.domain.story_domain import CompanionRuntimeConfig, Relationship
from app.module.companion.protocol.companion_story_protocol import (
    CompanionStoryConfigProviderProtocol,
)
from app.module.companion.service.lore_recall import CompanionLoreRecall, RecalledLore

ContributionSite = Literal["user_message", "page_context", "attachment", "tool_result"]

# Used only when a provider serves a plain story config without a run cap.
_FALLBACK_RUN_CAP = 2


class CompanionContextContributor:
    """Decide which of one companion's memories to offer for each input."""

    def __init__(
        self,
        *,
        recall: CompanionLoreRecall,
        config: CompanionStoryConfigProviderProtocol,
        user_id: int | None = None,
    ) -> None:
        self.recall = recall
        self.config = config
        self.user_id = user_id

    async def contribute(
        self,
        *,
        site: ContributionSite,
        text: str,
        query: str | None = None,
        offered: frozenset[str] = frozenset(),
    ) -> list[RecalledLore]:
        """Return the memories to offer for one input (possibly none).

        ``offered`` lists the fragment ids already offered in this run; they
        count toward the per-run cap and are never offered again.
        """
        config = await self.config.load(self.user_id)
        cap = (
            config.max_contributions_per_run
            if isinstance(config, CompanionRuntimeConfig)
            else _FALLBACK_RUN_CAP
        )
        remaining = cap - len(offered)
        if remaining <= 0:
            return []
        limit = min(config.max_recalled_fragments, remaining)
        if site == "user_message":
            answered = await self.recall.recall(
                query or text,
                (),
                limit=limit,
                exclude=offered,
                allow_self_query=True,
                allow_topical=False,
            )
            if answered:
                return answered
            moment = await self.recall.story_moment(exclude=offered)
            return [moment] if moment is not None else []
        return await self.recall.recall(
            query or "",
            (text,),
            limit=limit,
            exclude=offered,
            allow_self_query=query is not None,
            allow_topical=True,
        )

    async def relationship(self) -> Relationship | None:
        """Return how long the person and this companion have known each other."""
        return await self.recall.relationship()


__all__ = ["CompanionContextContributor", "ContributionSite"]
