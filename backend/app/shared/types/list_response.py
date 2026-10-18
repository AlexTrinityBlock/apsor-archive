"""Generic list envelope used by every collection endpoint."""

from pydantic import BaseModel, ConfigDict


class ListResponseSchema[ResourceT: BaseModel](BaseModel):
    """A stable envelope so collections can grow pagination fields later."""

    model_config = ConfigDict(frozen=True)

    total_results: int
    start_index: int
    items_per_page: int
    resources: list[ResourceT]
