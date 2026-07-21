#!/usr/bin/env python3
"""Remove white-filled rectangles covering text from PDF slides."""

import fitz
import sys
from pathlib import Path


def is_white_fill(fill) -> bool:
    if fill is None:
        return False
    if isinstance(fill, (int, float)):
        return fill > 0.99
    if isinstance(fill, (list, tuple)):
        if len(fill) == 1:
            return fill[0] > 0.99
        if len(fill) == 3:
            return all(c > 0.99 for c in fill)
        if len(fill) == 4:
            return all(c < 0.01 for c in fill)
    return False


def has_content(page, rect) -> bool:
    margin = max(min(rect.width, rect.height) * 0.1, 3)
    inner = fitz.Rect(rect.x0 + margin, rect.y0 + margin,
                      rect.x1 - margin, rect.y1 - margin)
    if inner.width < 10 or inner.height < 10:
        inner = rect
    pix = page.get_pixmap(clip=inner, dpi=72)
    w, h = pix.width, pix.height
    step = 2 if w * h > 10000 else 1
    dark = 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            if max(pix.pixel(x, y)) < 200:
                dark += 1
    total = ((w + step - 1) // step) * ((h + step - 1) // step)
    return (dark * 100 // max(total, 1)) >= 2


def text_is_covered(page, rect) -> bool:
    blocks = page.get_text('dict', clip=rect, flags=fitz.TEXT_PRESERVE_WHITESPACE)
    for b in blocks.get('blocks', []):
        if b.get('type') != 0:
            continue
        for line in b.get('lines', []):
            for span in line.get('spans', []):
                t = span['text'].strip()
                if not t:
                    continue
                bbox = span['bbox']
                bw = bbox[2] - bbox[0]
                bh = bbox[3] - bbox[1]
                if bw < 2 or bh < 2:
                    continue
                area = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
                pix = page.get_pixmap(clip=area, dpi=72)
                w, h = pix.width, pix.height
                step = 2 if w * h > 5000 else 1
                dark = 0
                for x in range(0, w, step):
                    for y in range(0, h, step):
                        if max(pix.pixel(x, y)) < 200:
                            dark += 1
                if dark == 0:
                    return True
    if not has_content(page, rect):
        return True
    return False


def is_design_element(all_drawings, rect) -> bool:
    has_shadow = False
    for d in all_drawings:
        fill = d.get('fill')
        if fill is None or not isinstance(fill, (list, tuple)):
            continue
        if len(fill) == 1 and not (0.7 < fill[0] < 0.95):
            continue
        if len(fill) == 3 and not all(0.7 < c < 0.95 for c in fill):
            continue
        dr = d['rect']
        ox = max(0, min(rect.x1, dr.x1) - max(rect.x0, dr.x0))
        oy = max(0, min(rect.y1, dr.y1) - max(rect.y0, dr.y0))
        if ox > rect.width * 0.3 or oy > rect.height * 0.3:
            has_shadow = True
            break

    has_stroke = False
    for d in all_drawings:
        if d.get('type') not in ('s', 'fs'):
            continue
        r = d['rect']
        if abs(r.x0 - rect.x0) > 3 or abs(r.y0 - rect.y0) > 3:
            continue
        if abs(r.width - rect.width) > 3 or abs(r.height - rect.height) > 3:
            continue
        has_stroke = True
        break

    if has_shadow:
        return True
    if has_stroke and (rect.width > 200 or rect.height > 60):
        return True
    return False


def process_page(page, doc) -> bool:
    all_drawings = page.get_drawings()
    rects = []
    for d in all_drawings:
        if not is_white_fill(d.get('fill')):
            continue
        if d.get('type') not in ('f',):
            continue
        r = d['rect']
        if r.width >= page.rect.width * 0.95 and r.height >= page.rect.height * 0.95:
            continue
        if r.width < 5 or r.height < 5:
            continue
        if is_design_element(all_drawings, r):
            continue
        if not text_is_covered(page, r):
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
