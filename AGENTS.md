# Инструкция для ИИ-агента и разработчика (AGENTS.md)

> **Назначение репозитория:** Этот репозиторий содержит нормализованную базу тестовых заданий МОДО (ББЖМ) 4 и 9 классов в чистом формате JSON, централизованное хранилище всех иллюстраций и рабочий конвейер парсинга.

---

## 1. Структура репозитория

```text
modo-parsed-tests/
├── images/                      # Все 774 изображения в одном месте
├── tests_json/                  # 40 файлов JSON с 4 192 вопросами
├── pipeline/                    # Код конвейера (triage, extractor, parser, runner, e2e)
├── pipeline_reports/            # Отчеты и логи валидации (100% ALL PASS)
├── README.md                    # Описание базы
└── AGENTS.md                    # Это руководство
```

---

## 2. Как импортировать данные в веб-сервис / БД

Каждый файл в `tests_json/` представляет собой отдельный банк вопросов по предмету и классу.

### Схема сущности Вопрос (`Question`):
```typescript
interface ModoQuestion {
  id: string;               // e.g. "q1"
  question_number: number;  // 1, 2, 3...
  question_text: string;    // Включает текст мәтін (если есть) и <img src="images/..."/>
  options: Array<{
    key: "A" | "B" | "C" | "D" | "E";
    text: string;
  }>;
  correct_answer: string;   // e.g. "A"
  answer_source: "document_key" | "document_highlight" | "document_bold" | "document_plus_marker" | "ai_solved";
  explanation: string;      // Обоснование / источник ответа
  verification_status: "verified" | "needs_review";
}
```

### Рендеринг на фронтенде (React / Vue / HTML):
1. **Изображения:** Все изображения ссылаются на относительный путь `images/<filename>.png`.
   В вашем веб-сервере просто раздайте папку `images/` как статику:
   - В Nginx / Express: `app.use('/images', express.static('images'))`
   - В Next.js: поместите папку `images` в `public/images`
2. **Мәтіндер (Контекст чтения):** В соответствии с архитектурным решением, вводный текст рассказа/пассажа уже предварительно встроен в начало `question_text`. Каждый вопрос является **100% автономным** и не требует сложных связей «родитель-потомок».

---

## 3. Как запустить или расширить пайплайн

```bash
# Установка зависимостей
pip install python-docx pypdf pillow

# 1. Запуск классификации и триажа новых файлов:
python3 pipeline/triage.py

# 2. Запуск парсинга (полный прогон):
python3 pipeline/run_pipeline.py all

# 3. Запуск E2E валидатора:
python3 pipeline/e2e_test.py
```

---

## 4. Разделение по предметам МОДО

- `primary_complex_4_*` — 4 класс, комплексное тестирование (читательская грамотность, математика, естествознание)
- `math_literacy_9_*` — 9 класс, математическая грамотность
- `physics_9_*` — 9 класс, физика (естественно-научная грамотность)
- `chemistry_9_*` — 9 класс, химия
- `biology_9_*` — 9 класс, биология
- `geography_9_*` — 9 класс, география
- `reading_literacy_kk_9_*` — 9 класс, читательская грамотность на казахском языке
- `reading_literacy_ru_9_*` — 9 класс, читательская грамотность на русском языке
- `reading_literacy_en_9_*` — 9 класс, читательская грамотность на английском языке
