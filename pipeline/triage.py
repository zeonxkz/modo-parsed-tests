#!/usr/bin/env python3
"""
Скрипт первичной сортировки и классификации документов МОДО (Triage).
Анализирует все папки в /root/modo_materials/documents/ и разделяет их на:
1. VALID_TEST - пригодные для парсинга тестовые документы по спецификации МОДО
2. QUARANTINE_SCAN - сканированные PDF/файлы без текстового слоя
3. QUARANTINE_ADMIN - административные документы (циклограммы, планы, протоколы, папки)
4. QUARANTINE_NON_MODO - тесты по предметам, не входящим в МОДО
"""

import os
import json
import re
from typing import Dict, Any, List

MODO_SUBJECT_KEYWORDS = {
    "math_literacy": ["математика", "математикалық", "мат сауаттылық", "мат.сауаттылық", "математическая грамотность"],
    "physics": ["физика", "физикалық", "физике"],
    "chemistry": ["химия", "химиялық"],
    "biology": ["биология", "биологиялық"],
    "geography": ["география", "географиялық"],
    "reading_literacy_kk": ["қазақ тілі", "казахский язык", "оқу сауаттылығы", "оқу сауат"],
    "reading_literacy_ru": ["русский язык", "орыс тілі", "читательская грамотность", "грамотность чтения"],
    "reading_literacy_en": ["ағылшын", "английский", "english", "шетел тілі", "foreign language"],
    "primary_complex": ["бастауыш", "4 сынып", "4-сынып", "4 класс", "4-класс", "начальн"]
}

NON_MODO_KEYWORDS = [
    "тарих", "история", "информатика", "өзін-өзі тану", "самопознание", 
    "көркем еңбек", "трудовое", "дене шынықтыру", "физкультура", "құқық", "право"
]

ADMIN_DOC_KEYWORDS = [
    "циклограмма", "жоспар", "план", "папка", "хаттама", "протокол", 
    "анықтама", "справка", "сараптама", "талдау", "анализ", "бұйрық", 
    "приказ", "ереже", "правила", "ұсыным", "рекомендац", "әдістемелік", "пособие"
]

def detect_subject_and_grade(title: str, text_sample: str) -> Dict[str, Any]:
    full_text = f"{title} {text_sample}".lower()
    
    # Grade detection
    grade = None
    if any(k in full_text for k in ["4 сынып", "4-сынып", "4 класс", "4-класс", "4кл", "4 кл", "бастауыш"]):
        grade = 4
    elif any(k in full_text for k in ["9 сынып", "9-сынып", "9 класс", "9-класс", "9кл", "9 кл"]):
        grade = 9
    
    # Check non-modo subject
    is_non_modo = any(k in full_text for k in NON_MODO_KEYWORDS)
    if is_non_modo and not any(k in full_text for k in ["физика", "химия", "биология", "география", "математика", "қазақ тілі", "русский язык", "english"]):
        return {"grade": grade, "subject": "non_modo", "is_modo": False}

    # Detect subject
    detected_sub = "unknown"
    for sub, kws in MODO_SUBJECT_KEYWORDS.items():
        if any(k in full_text for k in kws):
            detected_sub = sub
            break
            
    if grade == 4 and detected_sub in ["unknown", "reading_literacy_kk", "reading_literacy_ru", "math_literacy"]:
        detected_sub = "primary_complex"

    return {
        "grade": grade or (4 if detected_sub == "primary_complex" else 9),
        "subject": detected_sub,
        "is_modo": detected_sub != "unknown" and not is_non_modo
    }

def inspect_file_content(file_path: str):
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    options_count = 0
    questions_count = 0
    images_count = 0
    is_scan = False

    if ext == ".docx":
        try:
            import docx
            doc = docx.Document(file_path)
            for p in doc.paragraphs:
                t = p.text.strip()
                if t:
                    text += t + "\n"
                    if re.match(r'^[A-DА-ДA-Fa-f]\s*[\)\.]|^\+[A-DА-Д]', t):
                        options_count += 1
                    if re.match(r'^(?:[0-9]{1,3}|№\s*[0-9]{1,3})\s*[\.\)-]', t) or 'сұрақ' in t.lower() or 'вопрос' in t.lower():
                        questions_count += 1
            images_count = len([rel.target_ref for rel in doc.part.rels.values() if 'image' in rel.target_ref])
            if len(text.strip()) < 50 and images_count > 0:
                is_scan = True
        except Exception:
            is_scan = True
    elif ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
            if len(text.strip()) < 100:
                is_scan = True
            else:
                for line in text.split("\n"):
                    line = line.strip()
                    if re.match(r'^[A-DА-ДA-Fa-f]\s*[\)\.]|^\+[A-DА-Д]', line):
                        options_count += 1
                    if re.match(r'^(?:[0-9]{1,3}|№\s*[0-9]{1,3})\s*[\.\)-]', line):
                        questions_count += 1
        except Exception:
            is_scan = True
    elif ext == ".pptx":
        return text, options_count, questions_count, images_count, True # Treat presentation as admin/scan
    elif ext == ".doc":
        return text, options_count, questions_count, images_count, False

    return text, options_count, questions_count, images_count, is_scan

def triage_folder(folder_path: str) -> Dict[str, Any]:
    folder_id = os.path.basename(folder_path)
    meta_path = os.path.join(folder_path, "metadata.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

    title = meta.get("title", folder_id)
    doc_files = [f for f in os.listdir(folder_path) if f != "metadata.json"]
    
    if not doc_files:
        return {
            "folder_id": folder_id,
            "status": "QUARANTINE_SCAN",
            "reason": "Папка пуста (нет файлов документа)",
            "title": title
        }

    target_file = None
    for f in doc_files:
        if f.endswith(".docx") or f.endswith(".pdf") or f.endswith(".doc"):
            target_file = f
            break
    if not target_file:
        target_file = doc_files[0]

    target_path = os.path.join(folder_path, target_file)
    text, opts_cnt, qs_cnt, imgs_cnt, is_scan = inspect_file_content(target_path)

    sub_info = detect_subject_and_grade(title, text[:1500])

    # Categorize
    if is_scan and opts_cnt == 0:
        status = "QUARANTINE_SCAN"
        reason = f"Скан/изображение без текстового слоя ({imgs_cnt} картинок, текст < 50 симв.)"
    elif not sub_info["is_modo"]:
        status = "QUARANTINE_NON_MODO"
        reason = f"Предмет не входит в официальную спецификацию МОДО РК: {sub_info['subject']}"
    elif any(k in title.lower() for k in ADMIN_DOC_KEYWORDS) and opts_cnt < 4:
        status = "QUARANTINE_ADMIN"
        reason = f"Административный документ (план/циклограмма/папка/протокол/талдау, опций теста={opts_cnt})"
    elif opts_cnt >= 4:
        status = "VALID_TEST"
        reason = f"Тестовые задания МОДО: опций={opts_cnt}, вопросов~{qs_cnt}, картинок={imgs_cnt}"
    elif any(k in text[:500].lower() for k in ADMIN_DOC_KEYWORDS) or len(text) < 200:
        status = "QUARANTINE_ADMIN"
        reason = f"Административный/недостаточный контент (опций теста: {opts_cnt})"
    else:
        status = "QUARANTINE_ADMIN"
        reason = f"Недостаточно признаков теста (найдено опций: {opts_cnt}, вопросов: {qs_cnt})"

    return {
        "folder_id": folder_id,
        "title": title,
        "target_file": target_file,
        "target_path": target_path,
        "status": status,
        "reason": reason,
        "grade": sub_info["grade"],
        "subject": sub_info["subject"],
        "options_count": opts_cnt,
        "questions_count": qs_cnt,
        "images_count": imgs_cnt,
        "text_length": len(text)
    }

def main():
    base_dir = "/root/modo_materials/documents"
    reports_dir = "/root/modo_parsed_database/pipeline_reports"
    os.makedirs(reports_dir, exist_ok=True)

    results = []
    summary = {
        "VALID_TEST": 0,
        "QUARANTINE_SCAN": 0,
        "QUARANTINE_ADMIN": 0,
        "QUARANTINE_NON_MODO": 0
    }

    folders = sorted([os.path.join(base_dir, d) for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))])
    print(f"Запуск триажа {len(folders)} папок в {base_dir}...")

    for fld in folders:
        res = triage_folder(fld)
        results.append(res)
        summary[res["status"]] += 1

    report_path = os.path.join(reports_dir, "triage_summary.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "items": results}, f, ensure_ascii=False, indent=2)

    print("\n=== ИТОГИ ТРИАЖА ПАПКИ DOCUMENTS ===")
    for k, v in summary.items():
        print(f"  {k}: {v} папок")
    print(f"Полный отчет сохранен в: {report_path}")

if __name__ == "__main__":
    main()
