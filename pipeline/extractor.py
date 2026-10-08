#!/usr/bin/env python3
"""
Модуль извлечения структурированного текста, стилей и изображений из DOCX и PDF.
Извлекает картинки в централизованную папку /root/modo_parsed_database/images/
и встраивает теги <img src="images/..."/> непосредственно в текст абзаца.
"""

import os
import re
import hashlib
from typing import List, Dict, Any, Tuple
import docx
from docx.oxml.ns import qn

IMAGES_DIR = "/root/modo_parsed_database/images"

def get_image_hash(image_bytes: bytes) -> str:
    return hashlib.md5(image_bytes).hexdigest()[:8]

def extract_docx_content(docx_path: str, doc_prefix: str) -> List[Dict[str, Any]]:
    """
    Извлекает список структурированных блоков из DOCX:
    - text: текст абзаца (с встроенными <img src="images/..."/>)
    - runs: данные по каждому run (bold, italic, highlight, color, text)
    - has_bold: флаг наличия полужирного шрифта
    - has_highlight: флаг наличия подсветки
    - has_color: флаг необычного цвета (зеленый/красный)
    - images: список сохраненных изображений в этом абзаце
    """
    os.makedirs(IMAGES_DIR, exist_ok=True)
    doc = docx.Document(docx_path)
    
    # Карта связей для изображений
    rel_map = {}
    for r_id, rel in doc.part.rels.items():
        if "image" in rel.target_ref:
            try:
                rel_map[r_id] = rel.target_part.blob
            except Exception:
                pass

    blocks = []
    img_counter = 1

    for p in doc.paragraphs:
        p_text = ""
        p_images = []
        p_runs_meta = []
        has_bold = False
        has_hl = False
        has_special_color = False

        # Проверяем наличие изображений внутри XML абзаца (w:drawing / a:blip)
        for drawing in p._element.xpath('.//w:drawing'):
            for blip in drawing.xpath('.//a:blip'):
                embed_id = blip.get(qn('r:embed'))
                if embed_id and embed_id in rel_map:
                    img_data = rel_map[embed_id]
                    img_hash = get_image_hash(img_data)
                    img_filename = f"{doc_prefix}_img{img_counter}_{img_hash}.png"
                    img_path = os.path.join(IMAGES_DIR, img_filename)
                    if not os.path.exists(img_path):
                        with open(img_path, "wb") as f_img:
                            f_img.write(img_data)
                    p_images.append(img_filename)
                    # Вставляем тег изображения в позицию
                    p_text += f'<img src="images/{img_filename}"/> '
                    img_counter += 1

        for r in p.runs:
            r_txt = r.text
            if not r_txt:
                continue
            is_b = bool(r.bold)
            is_hl = bool(r.font.highlight_color)
            is_col = False
            if r.font.color and r.font.color.rgb:
                rgb_str = str(r.font.color.rgb).upper()
                # Красный (FF0000), Зеленый (008000, 00B050)
                if rgb_str in ["FF0000", "008000", "00B050", "228B22"]:
                    is_col = True

            if is_b: has_bold = True
            if is_hl: has_hl = True
            if is_col: has_special_color = True

            p_runs_meta.append({
                "text": r_txt,
                "bold": is_b,
                "highlight": is_hl,
                "color": is_col
            })
            p_text += r_txt

        cleaned_text = p_text.strip()
        if cleaned_text or p_images:
            blocks.append({
                "text": cleaned_text,
                "runs": p_runs_meta,
                "has_bold": has_bold,
                "has_highlight": has_hl,
                "has_color": has_special_color,
                "images": p_images
            })

    # Также проверяем таблицы (иногда тесты или ключи ответов сверстаны в таблицах)
    for t in doc.tables:
        for row in t.rows:
            cell_texts = [c.text.strip() for c in row.cells if c.text.strip()]
            if cell_texts:
                blocks.append({
                    "text": " | ".join(cell_texts),
                    "runs": [],
                    "has_bold": False,
                    "has_highlight": False,
                    "has_color": False,
                    "images": [],
                    "is_table_row": True
                })

    return blocks

def extract_pdf_content(pdf_path: str, doc_prefix: str) -> List[Dict[str, Any]]:
    """Извлекает блоки из PDF с помощью pypdf."""
    import pypdf
    blocks = []
    reader = pypdf.PdfReader(pdf_path)
    for p_idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if line:
                blocks.append({
                    "text": line,
                    "runs": [],
                    "has_bold": False,
                    "has_highlight": False,
                    "has_color": False,
                    "images": []
                })
    return blocks
