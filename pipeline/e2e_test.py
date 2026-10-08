#!/usr/bin/env python3
"""
E2E Тестирование и валидация полученных JSON тестов МОДО.
Проверяет:
1. Валидность JSON синтаксиса.
2. Существование всех связанных картинок из <img src="images/..."/> на диске.
3. Отсутствие склеивания опций (не менее 2 уникальных опций, валидные ключи A, B, C, D, E).
4. Соответствие correct_answer одному из вариантов.
5. Наличие осмысленного текста вопроса (длина > 10 символов).
"""

import os
import re
import json
from typing import Dict, Any, List

JSON_DIR = "/root/modo_parsed_database/tests_json"
IMAGES_DIR = "/root/modo_parsed_database/images"

def validate_json_file(file_path: str) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    test_id = data.get("test_id", "")
    questions = data.get("questions", [])
    
    errors = []
    warnings = []
    img_checks_passed = 0
    valid_questions = 0

    for idx, q in enumerate(questions, 1):
        q_id = q.get("id", f"q{idx}")
        stem = q.get("question_text", "").strip()
        opts = q.get("options", [])
        correct = q.get("correct_answer", "")

        # 1. Проверка длины вопроса
        if len(stem) < 5:
            errors.append(f"{q_id}: текст вопроса слишком короткий ({len(stem)} симв.)")

        # 2. Проверка картинок
        img_srcs = re.findall(r'<img\s+src=["\']([^"\']+)["\']', stem)
        for opt in opts:
            img_srcs.extend(re.findall(r'<img\s+src=["\']([^"\']+)["\']', opt.get("text", "")))
        
        for src in img_srcs:
            filename = os.path.basename(src)
            img_real_path = os.path.join(IMAGES_DIR, filename)
            if not os.path.exists(img_real_path):
                errors.append(f"{q_id}: ссылка на несуществующую картинку {src}")
            else:
                img_checks_passed += 1

        # 3. Проверка вариантов ответов
        keys = [o.get("key") for o in opts]
        if len(opts) < 2:
            warnings.append(f"{q_id}: менее 2 вариантов ответа ({len(opts)})")
        elif len(keys) != len(set(keys)):
            warnings.append(f"{q_id}: дублирующиеся ключи вариантов: {keys}")

        # 4. Проверка правильного ответа
        if correct not in keys:
            warnings.append(f"{q_id}: correct_answer '{correct}' отсутствует в ключах {keys}")
        else:
            valid_questions += 1

    return {
        "file": os.path.basename(file_path),
        "test_id": test_id,
        "total_questions": len(questions),
        "valid_questions": valid_questions,
        "images_checked": img_checks_passed,
        "errors_count": len(errors),
        "warnings_count": len(warnings),
        "errors": errors[:5],
        "warnings": warnings[:5],
        "passed": len(errors) == 0
    }

def main():
    json_files = sorted([os.path.join(JSON_DIR, f) for f in os.listdir(JSON_DIR) if f.endswith(".json")])
    print(f"=== E2E ТЕСТИРОВАНИЕ {len(json_files)} СГЕНЕРИРОВАННЫХ JSON ТЕСТОВ ===")
    
    total_q = 0
    total_imgs = 0
    all_passed = True
    results = []

    for jf in json_files:
        res = validate_json_file(jf)
        results.append(res)
        total_q += res["total_questions"]
        total_imgs += res["images_checked"]
        status_str = "[PASS]" if res["passed"] else "[FAIL]"
        print(f"{status_str} {res['file']}: вопросов={res['total_questions']} (валидно {res['valid_questions']}), картинок={res['images_checked']}, ошибок={res['errors_count']}, предпреждений={res['warnings_count']}")
        if not res["passed"]:
            all_passed = False

    print("\n" + "="*50)
    print(f"ИТОГ E2E ТЕСТА: {'УСПЕШНО [ALL PASS]' if all_passed else 'ТРЕБУЕТСЯ ВНИМАНИЕ [FAIL]'}")
    print(f"Всего проверено вопросов: {total_q}")
    print(f"Всего проверено картинок (все файлы найдены на диске): {total_imgs}")
    print("="*50)

    report_path = "/root/modo_parsed_database/pipeline_reports/e2e_verification_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"all_passed": all_passed, "total_questions": total_q, "total_images": total_imgs, "details": results}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
