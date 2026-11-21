"""Regression: PDFium renders must never overlap across extraction threads.

PDFium is not thread-safe across threads, even for different documents. The
shared extraction pool can render two scanned PDFs at once, so the service must
serialize document creation, page rendering, PNG encoding, and close.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

from app.module.knowledge.service import file_service as file_service_module
from app.module.knowledge.service.file_service import FileService


class _FakeImage:
    def save(self, buffer: Any, format: str) -> None:
        del format
        buffer.write(b"\x89PNG\r\n\x1a\n")


class _FakeBitmap:
    def to_pil(self) -> _FakeImage:
        return _FakeImage()


class _FakePage:
    def render(self, *, scale: float) -> _FakeBitmap:
        # Hold the document open long enough that a second thread would
        # overlap when the lock is missing.
        time.sleep(0.05)
        assert scale == 2.0
        return _FakeBitmap()


class _FakePdfDocument:
    """A fake PDFium document that records concurrent open documents."""

    _guard = threading.Lock()
    open_documents = 0
    max_open_documents = 0

    def __init__(self, data: bytes) -> None:
        assert data == b"%PDF-fake"
        with _FakePdfDocument._guard:
            _FakePdfDocument.open_documents += 1
            _FakePdfDocument.max_open_documents = max(
                _FakePdfDocument.max_open_documents,
                _FakePdfDocument.open_documents,
            )

    def __len__(self) -> int:
        return 2

    def __getitem__(self, index: int) -> _FakePage:
        assert 0 <= index < 2
        return _FakePage()

    def close(self) -> None:
        with _FakePdfDocument._guard:
            _FakePdfDocument.open_documents -= 1


def test_pdfium_renders_are_serialized(monkeypatch: Any) -> None:
    _FakePdfDocument.open_documents = 0
    _FakePdfDocument.max_open_documents = 0
    monkeypatch.setattr(
        file_service_module,
        "pdfium",
        SimpleNamespace(PdfDocument=_FakePdfDocument),
    )

    def render(_: int) -> list[bytes]:
        return FileService._render_pdf_pages(b"%PDF-fake", 2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(render, range(2)))

    assert [len(pages) for pages in results] == [2, 2]
    assert _FakePdfDocument.max_open_documents == 1
    assert _FakePdfDocument.open_documents == 0
