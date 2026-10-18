"""A curated demo library used by the one-click empty-state action."""

from datetime import UTC, datetime

from app.module.knowledge.exception.domain_error import DemoAlreadySeededError
from app.module.knowledge.protocol.file_repository_protocol import FileRepositoryProtocol
from app.module.knowledge.protocol.memory_repository_protocol import MemoryRepositoryProtocol
from app.module.knowledge.schema.system_schema import DemoSeedSchema
from app.module.knowledge.service.file_service import FileService
from app.module.knowledge.service.memory_service import MemoryService
from app.module.knowledge.service.summary_service import SummaryService

AUTOMOBILE_TEXT = """\
The history of the automobile has two broad phases.

The first phase covers steam and early internal-combustion experiments in the
eighteenth and nineteenth centuries. Engineers tried to shrink steam engines
enough to move a road vehicle, but weight and fuel handling kept the machines
impractical.

The second phase begins in 1886, when Karl Benz patented a gasoline-powered
three-wheeler. Benz's vehicle is widely treated as the first practical modern
car. In the early twentieth century, Henry Ford's Model T and the moving
assembly line turned the car from a craft object into a mass-market product.

By the twenty-first century, the industry was again in transition: electric
drivetrains, batteries, and software-defined vehicles became the main area of
investment. The through-line is the same as in 1886: a better power source and
a cheaper way to build it.
"""

QING_TEXT = """\
The Qing dynasty ruled China from 1644 to 1912.

Its early period consolidated control over a large and diverse territory. The
Kangxi, Yongzheng, and Qianlong reigns are often grouped as a long high point,
with administrative reforms, ambitious mapping projects, and a flourishing
print culture.

The nineteenth century brought external pressure and internal strain. The
Opium War exposed the dynasty's military and diplomatic limits. The Taiping
rebellion and other upheavals weakened the state, while treaty ports changed
the economy.

The dynasty ended in 1912 after the Xinhai Revolution. The last emperor
abdicated, and a republic replaced more than two centuries of Qing rule.
"""

RETRIEVAL_TEXT = """\
Hybrid retrieval combines lexical and vector recall.

Lexical recall uses BM25 over n-grams. For Chinese text, overlapping character
bigrams give a robust index without a word segmenter. For Latin text, word
tokens are enough. BM25 rewards rare terms and saturates repeated terms.

Vector recall embeds a query and every chunk, then ranks chunks by cosine
similarity. The embedding provider can be a hosted model or a deterministic
local hashing vectorizer.

The two result sets are merged with reciprocal rank fusion. A chunk that ranks
high in both paths rises to the top. Deduplication happens by chunk id before
hydration, so the same passage never appears twice.

The design goal is small, inspectable context: a language model should need two
or three tool calls, not a full-library dump, before it can answer.
"""

JOURNAL_TEXT = """\
2026-09-13 parts order

A parts order arrived in the afternoon. The boxes contained suspension bushings,
a replacement 10mm combination wrench, and the chassis mounts.

The chassis assembly started after the inventory check. The 10mm wrench that
slipped earlier was retired. A torque wrench was used for the mounts.

The remaining work is the brake line routing and a road test. The next order
should include two more bushings and a set of flare-nut wrenches.
"""


class DemoService:
    """Seed a small, coherent library only when the database is empty."""

    def __init__(
        self,
        *,
        file_service: FileService,
        memory_service: MemoryService,
        summary_service: SummaryService,
        file_repository: FileRepositoryProtocol,
        memory_repository: MemoryRepositoryProtocol,
    ) -> None:
        self.file_service = file_service
        self.memory_service = memory_service
        self.summary_service = summary_service
        self.file_repository = file_repository
        self.memory_repository = memory_repository

    async def seed(self) -> DemoSeedSchema:
        if (
            await self.file_repository.count_current() > 0
            or await self.memory_repository.count_active() > 0
        ):
            raise DemoAlreadySeededError()

        file_specs = [
            (
                "/history/industry/automobile/history-of-the-automobile.md",
                AUTOMOBILE_TEXT,
                datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
            ),
            (
                "/history/china/qing/qing-dynasty.md",
                QING_TEXT,
                datetime(2026, 9, 3, 10, 0, tzinfo=UTC),
            ),
            (
                "/research/retrieval/hybrid-search-notes.md",
                RETRIEVAL_TEXT,
                datetime(2026, 9, 8, 14, 0, tzinfo=UTC),
            ),
            (
                "/journal/2026-09-13-parts-order.md",
                JOURNAL_TEXT,
                datetime(2026, 9, 13, 15, 0, tzinfo=UTC),
            ),
        ]
        for path, content, occurred_at in file_specs:
            await self.file_service.ingest_text(
                path=path,
                content=content,
                occurred_at=occurred_at,
            )

        manual_car = await self.memory_service.save_memory(
            content="The user prefers a manual-transmission car.",
            supersedes=[],
            occurred_at=datetime(2026, 8, 10, 10, 0, tzinfo=UTC),
            source="manual",
            auto_summary=False,
        )
        colleague_car = await self.memory_service.save_memory(
            content="A colleague recommended a manual-transmission car.",
            supersedes=[],
            occurred_at=datetime(2026, 8, 10, 14, 0, tzinfo=UTC),
            source="manual",
            auto_summary=False,
        )
        await self.memory_service.save_memory(
            content="The user prefers inexpensive wrenches when repairing vehicles.",
            supersedes=[],
            occurred_at=datetime(2026, 9, 2, 9, 30, tzinfo=UTC),
            source="manual",
            auto_summary=False,
        )
        await self.memory_service.save_memory(
            content="The user feels stressed while repairing vehicles.",
            supersedes=[],
            occurred_at=datetime(2026, 9, 8, 20, 0, tzinfo=UTC),
            source="manual",
            auto_summary=False,
        )
        parts_memory = await self.memory_service.save_memory(
            content="A parts order arrived and the user started assembling the chassis.",
            supersedes=[],
            occurred_at=datetime(2026, 9, 14, 11, 20, tzinfo=UTC),
            source="manual",
            auto_summary=False,
        )
        await self.memory_service.save_memory(
            content="The 10mm wrench slipped and the user felt frustrated.",
            supersedes=[],
            occurred_at=datetime(2026, 9, 15, 9, 30, tzinfo=UTC),
            source="manual",
            auto_summary=False,
        )
        automatic = await self.memory_service.save_memory(
            content="The user switched to an automatic-transmission car.",
            supersedes=[manual_car.memory.memory_id, colleague_car.memory.memory_id],
            occurred_at=datetime(2026, 9, 16, 20, 55, tzinfo=UTC),
            source="manual",
            auto_summary=False,
        )
        await self.memory_service.save_memory(
            content="The user planned a brake-line upgrade before the next road test.",
            supersedes=[],
            occurred_at=datetime(2026, 9, 17, 18, 0, tzinfo=UTC),
            source="manual",
            auto_summary=False,
        )

        memory_ids = [
            manual_car.memory.memory_id,
            colleague_car.memory.memory_id,
            parts_memory.memory.memory_id,
            automatic.memory.memory_id,
        ]
        summary = await self.summary_service.create_summary(
            period_start=datetime(2026, 8, 1, tzinfo=UTC),
            period_end=datetime(2026, 9, 18, tzinfo=UTC),
            memory_ids=memory_ids,
            force=True,
        )

        return DemoSeedSchema(
            files_created=len(file_specs),
            memories_created=8,
            summaries_created=1 if summary is not None else 0,
        )
