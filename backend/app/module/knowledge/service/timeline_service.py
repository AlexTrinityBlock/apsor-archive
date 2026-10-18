"""Timeline reads with proportional sparse sampling."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.module.knowledge.domain.timeline_domain import (
    TimelineEvent,
    TimelineSample,
    sample_timeline,
)
from app.module.knowledge.exception.domain_error import InvalidTimelineRangeError
from app.module.knowledge.protocol.cache_protocol import CacheProtocol
from app.module.knowledge.protocol.file_repository_protocol import FileRepositoryProtocol
from app.module.knowledge.protocol.memory_repository_protocol import MemoryRepositoryProtocol
from app.module.knowledge.protocol.summary_repository_protocol import SummaryRepositoryProtocol
from app.module.knowledge.schema.timeline_schema import (
    TimelineDensitySchema,
    TimelineEventSchema,
    TimelineResponseSchema,
    TimelineSkipSchema,
)
from app.module.knowledge.service.cache_keys import cache_key

MAX_EVENTS_PER_KIND = 2000


class TimelineService:
    """Build the sparse timeline from memories, summaries, and file updates."""

    def __init__(
        self,
        *,
        memory_repository: MemoryRepositoryProtocol,
        summary_repository: SummaryRepositoryProtocol,
        file_repository: FileRepositoryProtocol,
        cache: CacheProtocol,
        cache_ttl_seconds: int,
        timezone_name: str,
        max_day_range: int,
    ) -> None:
        self.memory_repository = memory_repository
        self.summary_repository = summary_repository
        self.file_repository = file_repository
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timezone = ZoneInfo(timezone_name)
        self.max_day_range = max_day_range

    async def get_timeline(
        self,
        *,
        year: int,
        month: int,
        day: int,
        day_range: int,
        include_history: bool,
    ) -> TimelineResponseSchema:
        if day_range < 1 or day_range > self.max_day_range:
            raise InvalidTimelineRangeError(
                f"day_range must be between 1 and {self.max_day_range}."
            )
        try:
            anchor_day = datetime(year, month, day, tzinfo=self.timezone)
        except ValueError as exc:
            raise InvalidTimelineRangeError(str(exc)) from exc
        end_day = anchor_day + timedelta(days=1)
        start_day = end_day - timedelta(days=day_range)
        start_utc = start_day.astimezone(UTC)
        end_utc = end_day.astimezone(UTC)

        version = await self.cache.get_version()
        key = cache_key(
            version,
            "timeline",
            str(year),
            str(month),
            str(day),
            str(day_range),
            str(include_history),
        )
        cached = await self.cache.get_json(key)
        if isinstance(cached, dict):
            return TimelineResponseSchema.model_validate(cached)

        memories = await self.memory_repository.list_in_range(
            start_utc,
            end_utc,
            include_deprecated=include_history,
        )
        summaries = await self.summary_repository.list_in_range(start_utc, end_utc)
        files = await self.file_repository.list_updated_in_range(start_utc, end_utc)

        truncated = (
            len(memories) > MAX_EVENTS_PER_KIND
            or len(summaries) > MAX_EVENTS_PER_KIND
            or len(files) > MAX_EVENTS_PER_KIND
        )
        events: list[TimelineEvent] = []
        for memory in memories[:MAX_EVENTS_PER_KIND]:
            events.append(
                TimelineEvent(
                    kind="memory",
                    source_id=memory.id,
                    time=memory.memory_time,
                    date_label=memory.memory_time.astimezone(self.timezone).date().isoformat(),
                    content=memory.content,
                    status=memory.status,
                )
            )
        for summary in summaries[:MAX_EVENTS_PER_KIND]:
            events.append(
                TimelineEvent(
                    kind="summary",
                    source_id=summary.id,
                    time=summary.period_end,
                    date_label=summary.period_end.astimezone(self.timezone).date().isoformat(),
                    content=summary.content,
                    title=", ".join(summary.themes),
                )
            )
        for file in files[:MAX_EVENTS_PER_KIND]:
            created = abs((file.updated_at - file.created_at).total_seconds()) < 1.0
            events.append(
                TimelineEvent(
                    kind="file_update",
                    source_id=file.id,
                    time=file.updated_at,
                    date_label=file.updated_at.astimezone(self.timezone).date().isoformat(),
                    content=file.file_name,
                    title=file.raw_file_path,
                    action="created" if created else "updated",
                )
            )

        sample = sample_timeline(
            events,
            start=start_day,
            end=end_day,
            anchors=5,
            truncated=truncated,
        )
        response = self._to_response(
            sample,
            start_day=start_day,
            end_day=end_day,
            day_range=day_range,
        )
        await self.cache.set_json(
            key,
            response.model_dump(mode="json"),
            self.cache_ttl_seconds,
        )
        return response

    @staticmethod
    def _to_response(
        sample: TimelineSample,
        *,
        start_day: datetime,
        end_day: datetime,
        day_range: int,
    ) -> TimelineResponseSchema:
        events: list[TimelineEventSchema] = []
        for selection in sample.selections:
            event = selection.event
            events.append(
                TimelineEventSchema(
                    kind=event.kind,
                    anchor=selection.anchor,
                    time=event.time,
                    content=event.content,
                    memory_id=event.source_id if event.kind == "memory" else None,
                    memory_summary_id=event.source_id if event.kind == "summary" else None,
                    file_id=event.source_id if event.kind == "file_update" else None,
                    raw_file_path=event.title if event.kind == "file_update" else None,
                    action=event.action,
                    status=event.status,
                )
            )
        skips = [
            TimelineSkipSchema(
                from_time=skip.from_time,
                to_time=skip.to_time,
                file_number=skip.file_number,
                memory_number=skip.memory_number,
                summary_number=skip.summary_number,
            )
            for skip in sample.skips
        ]
        density = [
            TimelineDensitySchema(
                date=item.date,
                file_count=item.file_count,
                memory_count=item.memory_count,
                summary_count=item.summary_count,
            )
            for item in sample.density
        ]
        return TimelineResponseSchema(
            range_start=start_day,
            range_end=end_day - timedelta(microseconds=1),
            day_range=day_range,
            sampled=len(events),
            total=sample.total,
            skipped=sample.total - len(events),
            truncated=sample.truncated,
            events=events,
            skips=skips,
            density=density,
        )
