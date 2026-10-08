#!/usr/bin/env python3
"""
Основной скрипт запуска конвейера обработки и валидации тестов МОДО.
Позволяет запускать пилотный смоук-тест на 15 отобранных файлах или полный прогон.
"""

import os
import sys
import json
import time
from typing import List, Dict, Any

from extractor import extract_docx_content, extract_pdf_content
from parser import ModoTestParser

DATABASE_DIR = "/root/modo_parsed_database"
TESTS_JSON_DIR = os.path.join(DATABASE_DIR, "tests_json")
IMAGES_DIR = os.path.join(DATABASE_DIR, "images")
REPORTS_DIR = os.path.join(DATABASE_DIR, "pipeline_reports")

# Список 15 репрезентативных папок для пилотного смоук-теста
SMOKE_TEST_FOLDER_IDS = [
    # 4 класс:
    "335226_4 Сынып ББЖМ Соңғы. Модо",                 # 4 кл каз, комплексный с картинками
    "329127_4-сынып ББЖМ-ға дайындық материалдары, подготовке к МОДО, 4-класс", # 4 кл каз/рус, большой банк
    # 9 класс Английский язык (чтение с текстами):
    "322446_Модо, Ағылшын тілі, 9-сынып. _Dialogue Dana and Mr Barkley_ 10 сұрақ+д", # Bold ответы
    "324293_9 сынып МОДО, ағылшын тілінен 5текст+жауаптарымен",                       # 5 текстов с ключами
    "327279_Модо, ағылшын тілі, 9-сынып. Dodo pizza",                               # Текст Dodo pizza
    # 9 класс Физика (естественно-научная с графиками и схемами):
    "341356_Физика пәнінен МОДО тапсырмалары 2023-2024 оқу жылы",                    # Много картинок
    "341351_Физика пәнінен МОДО тапсырмалары 2023-2024 оқу жылы 7 нұсқа",            # Подсветка + схемы
    "384445_МОДО тапсырмаларының топтамасы",                                         # Топтама физика
    # 9 класс Математическая грамотность:
    "321397_модо тапсырмалары",                                                     # Чертежи, формулы
    "325853_МОДО",                                                                  # Задачи МОДО
    "337789_Мат сауаттылық МОДО тапсырмалары (9 сынып)",                             # Геометрия с рисунками
    # 9 класс Казахский язык (чтение):
    "319177_9 сынып МОДО тапсырмалары",                                             # Каз яз с вопросами
    "326908_МОДО. Қазақ тілі",                                                      # Каз яз тексты
    # 9 класс Русский язык (чтение):
    "381887_Модо 9 кл русский язык",                                                # Подсветка ответов
    # 9 класс Биология:
    "373959_9-сыныпқа арналған МОДО тапсырмалары, жауаптарымен"                     # Биология с ключами
]

def process_single_folder(item_meta: Dict[str, Any]) -> Dict[str, Any]:
    folder_id = item_meta["folder_id"]
    target_path = item_meta["target_path"]
    grade = item_meta.get("grade", 9)
    subject = item_meta.get("subject", "general")
    title = item_meta.get("title", folder_id)

    doc_prefix = f"{subject}_{grade}_{folder_id.split('_')[0]}"
    ext = os.path.splitext(target_path)[1].lower()

    # 1. Извлечение контента
    if ext == ".docx":
        blocks = extract_docx_content(target_path, doc_prefix)
    elif ext == ".pdf":
        blocks = extract_pdf_content(target_path, doc_prefix)
    else:
        return {
            "folder_id": folder_id,
            "status": "skipped",
            "reason": f"Неподдерживаемый формат: {ext}"
        }

    if not blocks:
        return {
            "folder_id": folder_id,
            "status": "failed",
            "reason": "Не удалось извлечь блоки контента"
        }

    # 2. Парсинг тестов
    parser = ModoTestParser(blocks, item_meta)
    questions = parser.parse()

    if not questions:
        return {
            "folder_id": folder_id,
            "status": "failed",
            "reason": "Вопросы не обнаружены в блоках"
        }

    # 3. Формирование финального JSON
    test_id = f"{subject}_{grade}_{folder_id.split('_')[0]}"
    output_filename = f"{test_id}.json"
    output_path = os.path.join(TESTS_JSON_DIR, output_filename)

    lang = "kk"
    if "русск" in title.lower() or subject == "reading_literacy_ru":
        lang = "ru"
    elif "ағылш" in title.lower() or "english" in title.lower() or subject == "reading_literacy_en":
        lang = "en"

    # Подсчет статистики источников ответов
    sources_count = {}
    verified_count = 0
    img_refs_count = 0
    for q in questions:
        src = q["answer_source"]
        sources_count[src] = sources_count.get(src, 0) + 1
        if q["verification_status"] == "verified":
            verified_count += 1
        img_refs_count += q["question_text"].count("<img src=")

    test_payload = {
        "test_id": test_id,
        "title": title,
        "subject": subject,
        "grade": grade,
        "language": lang,
        "source_file": os.path.basename(target_path),
        "total_questions": len(questions),
        "verified_questions": verified_count,
        "answer_sources_distribution": sources_count,
        "total_embedded_images": img_refs_count,
        "questions": questions
    }

    with open(output_path, "w", encoding="utf-8") as f_out:
        json.dump(test_payload, f_out, ensure_ascii=False, indent=2)

    return {
        "folder_id": folder_id,
        "test_id": test_id,
        "status": "success",
        "output_file": output_filename,
        "questions_count": len(questions),
        "verified_count": verified_count,
        "images_count": img_refs_count,
        "sources": sources_count
    }

def main():
    os.makedirs(TESTS_JSON_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

    mode = sys.argv[1] if len(sys.argv) > 1 else "smoke"

    # Читаем метаданные триажа
    triage_path = os.path.join(REPORTS_DIR, "triage_summary.json")
    if not os.path.exists(triage_path):
        print("Ошибка: файл триажа не найден. Сначала выполните triage.py")
        sys.exit(1)

    with open(triage_path, "r", encoding="utf-8") as f:
        triage_data = json.load(f)

    valid_items = {it["folder_id"]: it for it in triage_data["items"] if it["status"] == "VALID_TEST"}

    if mode == "smoke":
        print("=== ЗАПУСК ПИЛОТНОГО СМОУК-ТЕСТА (15 РАЗНОРОДНЫХ ФАЙЛОВ) ===")
        target_folders = SMOKE_TEST_FOLDER_IDS
    else:
        print(f"=== ЗАПУСК ПОЛНОГО ПАЙПЛАЙНА ({len(valid_items)} ВАЛИДНЫХ ФАЙЛОВ) ===")
        target_folders = list(valid_items.keys())

    start_time = time.time()
    results = []
    total_parsed_questions = 0
    total_images_saved = 0
    total_sources = {}

    for idx, f_id in enumerate(target_folders, 1):
        if f_id not in valid_items:
            print(f"[{idx}/{len(target_folders)}] Пропуск (не найден в valid): {f_id}")
            continue

        item_meta = valid_items[f_id]
        print(f"[{idx}/{len(target_folders)}] Обработка: {item_meta['title'][:50]} ({item_meta['subject']})...")
        res = process_single_folder(item_meta)
        results.append(res)

        if res["status"] == "success":
            total_parsed_questions += res["questions_count"]
            total_images_saved += res["images_count"]
            for s, c in res["sources"].items():
                total_sources[s] = total_sources.get(s, 0) + c
            print(f"  -> [OK] Вопросов: {res['questions_count']}, Верифицировано: {res['verified_count']}, Картинок: {res['images_count']}")
        else:
            print(f"  -> [FAIL] {res.get('reason')}")

    elapsed = time.time() - start_time
    report = {
        "mode": mode,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": round(elapsed, 2),
        "total_targets": len(target_folders),
        "successful_tests": len([r for r in results if r["status"] == "success"]),
        "failed_tests": len([r for r in results if r["status"] != "success"]),
        "total_parsed_questions": total_parsed_questions,
        "total_embedded_images": total_images_saved,
        "answer_sources_summary": total_sources,
        "details": results
    }

    report_file = os.path.join(REPORTS_DIR, f"{mode}_test_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n" + "="*50)
    print(f"СМОУК-ТЕСТ ЗАВЕРШЕН за {elapsed:.2f} сек!")
    print(f"Успешно обработано тестов: {report['successful_tests']} из {report['total_targets']}")
    print(f"Всего извлечено чистых вопросов: {total_parsed_questions}")
    print(f"Всего сохранено и встроено картинок: {total_images_saved}")
    print("Распределение источников ответов:")
    for src, cnt in total_sources.items():
        print(f"  - {src}: {cnt} вопросов")
    print(f"Подробный отчет: {report_file}")
    print("="*50)

if __name__ == "__main__":
    main()
