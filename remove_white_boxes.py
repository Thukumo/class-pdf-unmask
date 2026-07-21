#!/usr/bin/env python3
"""Remove white-filled rectangles covering text from PDF slides."""

import fitz
import sys
from pathlib import Path


DARK_THRESHOLD = 200
MIN_DARK_RATIO = 2


def is_text_covered(page, r) -> bool:
    margin_x = max(r.width * 0.1, 5)
    margin_y = max(r.height * 0.1, 5)
    inner = fitz.Rect(r.x0 + margin_x, r.y0 + margin_y,
                      r.x1 - margin_x, r.y1 - margin_y)
    if inner.width < 10 or inner.height < 10:
        inner = r
    pix = page.get_pixmap(clip=inner, dpi=72)
    dark = 0
    total = pix.width * pix.height
    step = 2 if total > 20000 else 1
    for y in range(0, pix.height, step):
        for x in range(0, pix.width, step):
            if max(pix.pixel(x, y)) < DARK_THRESHOLD:
                dark += 1
    ratio = dark * total // max((total // (step * step)), 1)
    return ratio < MIN_DARK_RATIO


def process_page(page, doc) -> bool:
    all_drawings = page.get_drawings()
    rects = []
    for d in all_drawings:
        fill = d.get('fill')
        if fill is None:
            continue
        is_white = False
        if isinstance(fill, (list, tuple)):
            if len(fill) == 1 and fill[0] > 0.99:
                is_white = True
            elif len(fill) == 3 and all(c > 0.99 for c in fill):
                is_white = True
            elif len(fill) == 4 and all(c < 0.01 for c in fill):
                is_white = True
        elif isinstance(fill, (int, float)) and fill > 0.99:
            is_white = True
        if not is_white:
            continue
        if d.get('type') not in ('f',):
            continue
        r = d['rect']
        if r.width >= page.rect.width * 0.95 and r.height >= page.rect.height * 0.95:
            continue
        if r.width < 5 and r.height < 5:
            continue
        blocks = page.get_text('blocks', clip=r)
        has_text = any(len(b[4].strip()) > 0 for b in blocks if len(b) > 4)
        if not has_text:
            continue
        if not is_text_covered(page, r):
            continue
        rects.append(r)

    if not rects:
        return False

    for r in rects:
        page.add_redact_annot(r)

    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
        text=fitz.PDF_REDACT_TEXT_NONE
    )
    return True


def main():
    pdf_dir = Path(__file__).parent
    pdfs = sorted(f for f in pdf_dir.glob('Lecture*.pdf') if not f.stem.endswith('_cleaned'))
    if not pdfs:
        print("No PDF files found.")
        sys.exit(1)
    for pdf_path in pdfs:
        print(f"Processing {pdf_path.name}...")
        try:
            doc = fitz.open(str(pdf_path))
        except Exception as e:
            print(f"  Error opening: {e}")
            continue
        mod_pages = 0
        for pno in range(len(doc)):
            if process_page(doc[pno], doc):
                mod_pages += 1
        out_path = pdf_path.parent / f"{pdf_path.stem}_cleaned.pdf"
        doc.save(str(out_path), deflate=True, garbage=4)
        if mod_pages > 0:
            print(f"  Modified {mod_pages} page(s) -> {out_path.name}")
        else:
            print(f"  No white rectangles found -> {out_path.name}")
        doc.close()


if __name__ == '__main__':
    main()
