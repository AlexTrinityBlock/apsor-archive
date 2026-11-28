"""Write one small real file per accepted upload type for the preview matrix.

Run with the backend environment (python-docx, python-pptx, openpyxl, Pillow):

    cd backend && uv run python ../frontend/scripts/e2e/make-preview-samples.py /tmp/samples
"""

import io
import json
import sys
import zipfile
from pathlib import Path

from docx import Document
from openpyxl import Workbook
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.util import Inches

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "preview-samples")
OUT.mkdir(parents=True, exist_ok=True)


def png_bytes(color: str, text: str) -> bytes:
    img = Image.new("RGB", (640, 400), color)
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, 600, 360], outline="white", width=6)
    d.text((60, 60), text, fill="white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# Images
for ext, fmt in [("png", "PNG"), ("jpg", "JPEG"), ("webp", "WEBP")]:
    img = Image.open(io.BytesIO(png_bytes("#3f6fa8", f"sample {ext}")))
    img.save(OUT / f"sample.{ext}", fmt)

# DOCX
doc = Document()
doc.add_heading("Grandma's dumplings", 0)
doc.add_paragraph("A short family recipe with a table and an image.")
t = doc.add_table(rows=3, cols=2)
for i, (a, b) in enumerate([("Item", "Amount"), ("Pork", "500 g"), ("Cabbage", "1/2")]):
    t.cell(i, 0).text, t.cell(i, 1).text = a, b
doc.add_picture(io.BytesIO(png_bytes("#9e3b3b", "docx image")), width=Inches(3))
doc.save(OUT / "sample.docx")

# XLSX with two sheets + formulas
wb = Workbook()
ws = wb.active
ws.title = "Budget"
ws.append(["Item", "Cost"])
ws.append(["Flour", 3])
ws.append(["Pork", 12])
ws["B4"] = "=SUM(B2:B3)"
ws2 = wb.create_sheet("Guests")
ws2.append(["Name", "Count"])
ws2.append(["Family", 6])
wb.save(OUT / "sample.xlsx")
wb.save(OUT / "sample.xlsm")

# ODS (minimal valid OpenDocument spreadsheet)
content = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">
<office:body><office:spreadsheet><table:table table:name="Sheet1">
<table:table-row><table:table-cell office:value-type="string"><text:p>Item</text:p></table:table-cell><table:table-cell office:value-type="string"><text:p>Qty</text:p></table:table-cell></table:table-row>
<table:table-row><table:table-cell office:value-type="string"><text:p>Tea</text:p></table:table-cell><table:table-cell office:value-type="float" office:value="3"><text:p>3</text:p></table:table-cell></table:table-row>
</table:table></office:spreadsheet></office:body></office:document-content>"""
manifest = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>
<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
</manifest:manifest>"""
with zipfile.ZipFile(OUT / "sample.ods", "w") as z:
    z.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.spreadsheet")
    z.writestr("content.xml", content, compress_type=zipfile.ZIP_DEFLATED)
    z.writestr("META-INF/manifest.xml", manifest, compress_type=zipfile.ZIP_DEFLATED)

# PPTX 3 slides incl. image
prs = Presentation()
for i in range(3):
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = f"Slide {i + 1}"
    s.placeholders[1].text = f"Point {i + 1}: the archive keeps what is ours."
    if i == 1:
        s.shapes.add_picture(io.BytesIO(png_bytes("#6f8f4e", "pptx image")), Inches(5), Inches(3), width=Inches(3))
prs.save(OUT / "sample.pptx")

# PDF with real text (an image-only PDF has nothing to extract without vision)
pages = ["Grandma's dumplings, page one.", "Page two: the filling is stirred in one direction."]
objs = ["<< /Type /Catalog /Pages 2 0 R >>"]
kids = " ".join(f"{3 + i * 2} 0 R" for i in range(len(pages)))
objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
font_id = 3 + len(pages) * 2
for i, text in enumerate(pages):
    content_id = 4 + i * 2
    objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>")
    stream = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET"
    objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
data = b"%PDF-1.4\n"
offsets = []
for n, body in enumerate(objs, start=1):
    offsets.append(len(data))
    data += f"{n} 0 obj\n{body}\nendobj\n".encode()
xref = len(data)
data += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
for off in offsets:
    data += f"{off:010d} 00000 n \n".encode()
data += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
(OUT / "sample.pdf").write_bytes(data)


# Text formats
(OUT / "sample.md").write_text(
    "# Grandma's notes\n\nSome **bold** text and a [link](https://example.com).\n\n"
    "## A table\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```python\nprint('hello')\n```\n\n"
    "- item one\n- item two\n\n![photo](photo.png)\n\n中文段落：外婆的水餃。\n",
    encoding="utf-8",
)
(OUT / "sample.markdown").write_text("# Markdown long ext\n\nHello.\n", encoding="utf-8")
(OUT / "sample.txt").write_text("Plain text line one\n中文第二行\n", encoding="utf-8")
(OUT / "sample.csv").write_text("name,count\nFamily,6\n外婆,1\n", encoding="utf-8")
(OUT / "sample.json").write_text(json.dumps({"recipe": "dumplings", "n": 60}), encoding="utf-8")
(OUT / "sample.jsonl").write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")
(OUT / "sample.toml").write_text('title = "notes"\n[owner]\nname = "Maya"\n', encoding="utf-8")
(OUT / "sample.ini").write_text("[main]\nkey = value\n", encoding="utf-8")
(OUT / "sample.env").write_text("APP_MODE=demo\nGREETING=hello\n", encoding="utf-8")
print(sorted(p.name for p in OUT.iterdir()))
