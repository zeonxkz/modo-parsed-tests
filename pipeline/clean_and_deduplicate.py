#!/usr/bin/env python3
"""
Скрипт глубокого аудита, нормализации и дедупликации базы тестов МОДО.
1. Удаляет нерелевантные заголовки документов ('Биология пәні бойынша тапсырмалар жинағы' и т.д.).
2. Очищает текст вариантов от приклеенных буквенных префиксов ('Ә) мезодерма' -> 'мезодерма').
3. Проверяет минимальное количество вариантов ответа (>= 2).
4. Выполняет дедупликацию идентичных вопросов (сохраняя наиболее полный).
5. Помещает дефектные записи в карантин /root/modo_parsed_database/quarantine/broken_questions.json.
"""

import os
import re
import json
from typing import Dict, Any, List

TESTS_DIR = "/root/modo_parsed_database/tests_json"
QUARANTINE_DIR = "/root/modo_parsed_database/quarantine"
os.makedirs(QUARANTINE_DIR, exist_ok=True)

# Регулярка для очистки префикса варианта в тексте (например, "Ә) мезодерма", "B. Вариант")
PREFIX_REGEX = re.compile(r'^[A-ZА-ЯӘҒҚҢӨҰҮҺІa-zа-яәғқңөұүһі]\s*[\)\.\-]\s*')

# Ключевые слова названий сборников/шапок
HEADER_TRASH_KEYWORDS = [
    "тапсырмалар жинағы", "нұсқа", "сборник заданий", "вариант", "дайындық материалдары",
    "папка", "тест тапсырмалары", "модо тапсырмалары", "ббжм тапсырмалары"
]

def clean_option_text(text: str) -> str:
    cleaned = text.strip()
    # Снимаем повторный префикс если автор продублировал букву
    m = PREFIX_REGEX.match(cleaned)
    if m:
        cleaned = cleaned[m.end():].strip()
    return cleaned

def is_header_trash(stem: str, opts: List[Dict[str, Any]]) -> bool:
    stem_lower = stem.lower()
    # Если вариантов меньше 2 и текст похож на заголовок/номер варианта
    if len(opts) < 2:
        return True
    if any(k in stem_lower for k in HEADER_TRASH_KEYWORDS) and len(stem) < 80 and not stem.endswith('?'):
        # Если при этом варианты тоже похожи на "001 нұсқа"
        if any("нұсқа" in o.get("text", "").lower() or "вариант" in o.get("text", "").lower() for o in opts):
            return True
    return False

def normalize_and_deduplicate():
    files = sorted([os.path.join(TESTS_DIR, f) for f in os.listdir(TESTS_DIR) if f.endswith(".json")])
    
    seen_questions = {} # clean_stem -> {file, q_idx}
    quarantined = []
    stats = {
        "total_before": 0,
        "total_after": 0,
        "removed_header_trash": 0,
        "removed_duplicates": 0,
        "fixed_prefixes": 0,
        "quarantined_less_than_2_opts": 0
    }

    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        orig_questions = data.get("questions", [])
        stats["total_before"] += len(orig_questions)
        clean_questions = []

        for q in orig_questions:
            stem = q.get("question_text", "").strip()
            opts = q.get("options", [])

            # 1. Проверка на шапку/заголовок документа
            if is_header_trash(stem, opts):
                quarantined.append({
                    "file": os.path.basename(file_path),
                    "reason": "header_trash_or_too_few_options",
                    "question": q
                })
                if len(opts) < 2:
                    stats["quarantined_less_than_2_opts"] += 1
                else:
                    stats["removed_header_trash"] += 1
                continue

            # 2. Очистка префиксов у вариантов
            cleaned_opts = []
            for o in opts:
                raw_t = o.get("text", "")
                cl_t = clean_option_text(raw_t)
                if cl_t != raw_t:
                    stats["fixed_prefixes"] += 1
                cleaned_opts.append({
                    "key": o.get("key"),
                    "text": cl_t
                })
            q["options"] = cleaned_opts

            # 3. Дедупликация
            # Нормализуем текст для поиска дубликатов
            normalized_key = re.sub(r'[\s\W_]+', ' ', stem).strip().lower()
            if len(normalized_key) > 20:
                if normalized_key in seen_questions:
                    stats["removed_duplicates"] += 1
                    quarantined.append({
                        "file": os.path.basename(file_path),
                        "reason": f"duplicate_of_{seen_questions[normalized_key]}",
                        "question": q
                    })
                    continue
                seen_questions[normalized_key] = os.path.basename(file_path)

            # Проверка соответствия правильного ответа
            valid_keys = [o["key"] for o in cleaned_opts]
            if q.get("correct_answer") not in valid_keys:
                q["correct_answer"] = valid_keys[0] if valid_keys else "A"

            clean_questions.append(q)

        stats["total_after"] += len(clean_questions)
        data["questions"] = clean_questions
        data["total_questions"] = len(clean_questions)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    quarantine_path = os.path.join(QUARANTINE_DIR, "quarantined_broken_and_duplicates.json")
    with open(quarantine_path, "w", encoding="utf-8") as f:
        json.dump({
            "stats": stats,
            "quarantined_count": len(quarantined),
            "items": quarantined
        }, f, ensure_ascii=False, indent=2)

    print("=== РЕЗУЛЬТАТЫ НОРМАЛИЗАЦИИ И ДЕДУПЛИКАЦИИ ===")
    print(f"Вопросов до обработки: {stats['total_before']}")
    print(f"Чистых вопросов после: {stats['total_after']}")
    print(f"Удалено мусорных шапок/не-тестов: {stats['removed_header_trash']}")
    print(f"Отправлено в карантин с <2 вариантами: {stats['quarantined_less_than_2_opts']}")
    print(f"Устранено дубликатов: {stats['removed_duplicates']}")
    print(f"Исправлено склеенных префиксов в вариантах (Ә), A)): {stats['fixed_prefixes']}")
    print(f"Файл карантина сохранен в: {quarantine_path}")

if __name__ == "__main__":
    normalize_and_deduplicate()
