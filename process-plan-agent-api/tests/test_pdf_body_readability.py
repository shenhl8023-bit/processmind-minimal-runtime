"""Real PDF regressions for raster bodies with incidental extractable text."""

import asyncio
from io import BytesIO

import fitz
import pytest
from fastapi import HTTPException, UploadFile

from app.routers import documents as documents_router


BODY_LINES = [
    "Operation 20: grind outer diameter",
    "Equipment: cylindrical grinding machine",
    "Locate on the two center holes",
    "Grind diameter to drawing dimensions",
    "Surface roughness: Ra 0.4 micrometers",
    "Tolerance grade: IT6",
    "Inspect diameter at three positions",
    "Remove grinding burrs and clean part",
]


def _body_image():
    with fitz.open() as source:
        page = source.new_page(width=550, height=650)
        for index, line in enumerate(BODY_LINES):
            page.insert_text((20, 60 + index * 65), line, fontsize=12)
        return page.get_pixmap().tobytes("png")


def _mixed_pdf(decoration, searchable_body=False, logo_only=False, short_body=False, rotation=0):
    with fitz.open() as document:
        first = document.new_page(width=600, height=800)
        first.insert_text((40, 120), "Operation 10: turn the blank")
        page = document.new_page(width=600, height=800)
        image_rect = fitz.Rect(490, 20, 560, 80) if logo_only else fitz.Rect(25, 85, 575, 735)
        page.insert_image(image_rect, stream=_body_image())
        if decoration == "page-number":
            page.insert_text((295, 780), "2")
        elif decoration == "header":
            page.insert_text((40, 40), "MANUFACTURING PROCESS DOCUMENT - CONTROLLED COPY")
        elif decoration == "watermark":
            page.insert_text((40, 400), "CONFIDENTIAL CONTROLLED COPY FOR INTERNAL MANUFACTURING REVIEW ONLY " * 2, fontsize=6)
        elif decoration == "punctuation":
            page.insert_text((40, 400), "... --- ... --- ...")
        if searchable_body or logo_only:
            for index, line in enumerate(BODY_LINES[:1] if short_body else BODY_LINES):
                page.insert_text((45, 145 + index * 65), line, fontsize=12,
                                 render_mode=3 if searchable_body else 0)
        page.set_rotation(rotation)
        return document.tobytes()


@pytest.mark.parametrize(("decoration", "rotation"), [
    ("page-number", 0), ("header", 0), ("watermark", 0), ("punctuation", 0), ("page-number", 90),
])
def test_upload_rejects_large_scanned_body_with_incidental_text(tmp_path, monkeypatch, decoration, rotation):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)
    payload = _mixed_pdf(decoration, rotation=rotation)
    # The body is a real rendered process sheet, not a tiny placeholder image.
    with fitz.open(stream=payload, filetype="pdf") as document:
        page = document[1]
        assert page.get_text("text").strip()
        assert "Surface roughness" not in page.get_text("text")
        assert page.get_image_info()[0]["width"] == 550

    async def run():
        with pytest.raises(HTTPException) as caught:
            await documents_router._stage_uploads([
                UploadFile(filename="mixed-process.pdf", file=BytesIO(payload)),
            ])
        assert caught.value.status_code == 422
        assert "mixed-process.pdf" in str(caught.value.detail)
        assert "第2页" in str(caught.value.detail)
        assert "文字识别" in str(caught.value.detail)

    asyncio.run(run())
    assert list(upload_dir.iterdir()) == []


@pytest.mark.parametrize(("logo_only", "short_body"), [(True, False), (True, True), (False, False)],
                         ids=["readable-body-with-logo", "short-body-with-logo", "existing-searchable-scan"])
def test_upload_accepts_extractable_body_with_images(tmp_path, monkeypatch, logo_only, short_body):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def run():
        staged = await documents_router._stage_uploads([
            UploadFile(filename="readable.pdf", file=BytesIO(
                _mixed_pdf("page-number", searchable_body=not logo_only, logo_only=logo_only, short_body=short_body),
            )),
        ])
        assert len(staged) == 1
        assert staged[0].path.is_file()

    asyncio.run(run())
