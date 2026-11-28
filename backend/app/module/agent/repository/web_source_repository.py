"""Owner-scoped numbering of the web pages one conversation has seen."""

from collections.abc import Sequence

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.module.agent.domain.web_source_domain import (
    MAX_WEB_SOURCE_URL_CHARS,
    WebSource,
    clean_title,
)
from app.module.agent.model.agent_model import AgentWebSourceModel


class WebSourceRepository:
    """Assign and read ``[web:wN]`` numbers for one conversation.

    Parallel tool calls of the same run open separate sessions, so assignment
    takes a transaction-scoped advisory lock keyed by the conversation before it
    reads the highest number. The lock ends with the tool call's transaction.
    """

    def __init__(self, session: AsyncSession, user_id: int, conversation_id: int) -> None:
        self.session = session
        self.user_id = user_id
        self.conversation_id = conversation_id

    async def assign(self, pages: Sequence[tuple[str, str | None]]) -> dict[str, int]:
        """Return ``url -> number``, numbering new urls after the current highest."""
        urls = [url for url, _ in pages if 0 < len(url) <= MAX_WEB_SOURCE_URL_CHARS]
        if not urls:
            return {}
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"agent_web_source:{self.user_id}:{self.conversation_id}"},
        )
        known = {
            row.url: row
            for row in (
                await self.session.scalars(
                    select(AgentWebSourceModel).where(
                        AgentWebSourceModel.user_id == self.user_id,
                        AgentWebSourceModel.conversation_id == self.conversation_id,
                        AgentWebSourceModel.url.in_(urls),
                    )
                )
            ).all()
        }
        highest = await self.session.scalar(
            select(func.coalesce(func.max(AgentWebSourceModel.ref_no), 0)).where(
                AgentWebSourceModel.user_id == self.user_id,
                AgentWebSourceModel.conversation_id == self.conversation_id,
            )
        )
        next_no = int(highest or 0)
        refs: dict[str, int] = {}
        for url, title in pages:
            if url not in urls or url in refs:
                continue
            row = known.get(url)
            if row is None:
                next_no += 1
                row = AgentWebSourceModel(
                    user_id=self.user_id,
                    conversation_id=self.conversation_id,
                    ref_no=next_no,
                    url=url,
                    title=clean_title(title),
                )
                self.session.add(row)
                known[url] = row
            elif row.title is None and clean_title(title) is not None:
                row.title = clean_title(title)
            refs[url] = row.ref_no
        await self.session.flush()
        return refs

    async def list_sources(self) -> list[WebSource]:
        """Return every numbered page of the conversation, in number order."""
        rows = await self.session.scalars(
            select(AgentWebSourceModel)
            .where(
                AgentWebSourceModel.user_id == self.user_id,
                AgentWebSourceModel.conversation_id == self.conversation_id,
            )
            .order_by(AgentWebSourceModel.ref_no)
        )
        return [WebSource(ref_no=row.ref_no, url=row.url, title=row.title) for row in rows]
