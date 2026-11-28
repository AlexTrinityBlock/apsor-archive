"""Process-wide lock around every PDFium call.

PDFium is not thread-safe across threads, even for different documents. Vision
page rendering and thumbnail rendering both take this lock so two renders in
the extraction pool never overlap.
"""

import threading

PDFIUM_RENDER_LOCK = threading.Lock()
