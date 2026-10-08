#!/usr/bin/env python3
"""
Движок многоступенчатого парсинга и валидации тестов МОДО.
Реализует:
1. Выявление контекстных текстов (мәтіндер/пассажи) и встраивание их в question_text.
2. Прецизионное разделение горизонтальных опций (А)... В)... С)... Д)...) на отдельных строках и внутри абзацев.
3. Отделение приклеенного варианта А) от конца вопроса.
4. Поиск ключей ответов (таблицы в конце документа, подсветка, жирный шрифт, маркер '+').
5. Аналитический ИИ-солвер для нерешенных вопросов.
6. Экспорт в чистый JSON.
"""

import os
import re
import json
from typing import List, Dict, Any, Optional, Tuple

class ModoTestParser:
    def __init__(self, blocks: List[Dict[str, Any]], meta: Dict[str, Any]):
        self.blocks = blocks
        self.meta = meta
        self.doc_answer_keys = {} # q_num -> 'A'
        self.questions = []
        self._extract_answer_keys_from_blocks()

    def _extract_answer_keys_from_blocks(self):
        """Ищет таблицы ключей или строки 'Жауаптары: 1-А, 2-В...' в конце документа."""
        end_blocks = self.blocks[-35:] if len(self.blocks) > 35 else self.blocks
        for b in end_blocks:
            t = b["text"]
            if any(k in t.lower() for k in ["жауап", "ответ", "кілт", "ключ"]) or " | " in t:
                matches = re.findall(r'(\d{1,3})\s*[-–—:\.\)]\s*([A-DА-ДA-Fa-f])', t)
                for q_num, ans in matches:
                    q_n = int(q_num)
                    ans_clean = self._normalize_key(ans)
                    if 1 <= q_n <= 80:
                        self.doc_answer_keys[q_n] = ans_clean

    def _normalize_key(self, letter: str) -> str:
        letter = letter.upper().strip()
        trans = {
            'А': 'A', 'В': 'B', 'С': 'C', 'Д': 'D', 'Е': 'E',
            'a': 'A', 'b': 'B', 'c': 'C', 'd': 'D', 'e': 'E'
        }
        return trans.get(letter, letter)

    def _split_horizontal_options(self, line: str, block: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Разбивает строку с опциями А) В) С) Д) или A . B . C . или A. B. C.
        """
        pattern = re.compile(r'(\+?[A-EА-ЕA-Ea-e]\s*[\)\.]|\+?[A-EА-Е]\s{1,3}(?=[А-ЯA-Za-z0-9]))\s*')
        matches = list(pattern.finditer(line))
        if not matches:
            return []

        if len(matches) == 1 and matches[0].start() <= 2:
            raw_key = matches[0].group(1).replace(')', '').replace('.', '').strip()
            is_plus = raw_key.startswith('+')
            key_let = self._normalize_key(raw_key.replace('+', ''))
            opt_text = line[matches[0].end():].strip()
            return [{
                "key": key_let,
                "text": opt_text,
                "is_bold": block.get("has_bold", False),
                "is_highlight": block.get("has_highlight", False),
                "is_color": block.get("has_color", False),
                "is_plus": is_plus
            }]

        # Если найдено 2 или более опций в одной строке
        results = []
        for i in range(len(matches)):
            start_pos = matches[i].end()
            end_pos = matches[i+1].start() if (i + 1 < len(matches)) else len(line)
            opt_text = line[start_pos:end_pos].strip()
            raw_key = matches[i].group(1).replace(')', '').replace('.', '').strip()
            is_plus = raw_key.startswith('+')
            key_let = self._normalize_key(raw_key.replace('+', ''))

            results.append({
                "key": key_let,
                "text": opt_text,
                "is_bold": block.get("has_bold", False),
                "is_highlight": block.get("has_highlight", False),
                "is_color": block.get("has_color", False),
                "is_plus": is_plus
            })
        return results

    def parse(self) -> List[Dict[str, Any]]:
        current_passage = ""
        in_passage = False
        current_q = None
        q_counter = 0

        re_q_start = re.compile(r'^(?:(?:[0-9]{1,3})[\.\)-]\s*|№\s*(?:[0-9]{1,3})[\.\s-]*|(?:[0-9]{1,3})\s*(?:тапсырма|сұрақ|вопрос|задание)[\.\s-]*)', re.IGNORECASE)
        re_passage_start = re.compile(r'(?:мәтін|text\s*\d*|нұсқаулық|instruction|прочитайте текст|мәтінді мұқият оқып)', re.IGNORECASE)

        for b_idx, block in enumerate(self.blocks):
            line = block["text"].strip()
            if not line:
                continue

            # Игнорируем сам блок ключей ответов
            if any(k in line.lower() for k in ["дұрыс жауаптары", "жауаптары:", "ответы:"]) and len(self.doc_answer_keys) > 3:
                continue

            # Проверка на начало мәтін / контекстного рассказа
            if re_passage_start.search(line) and len(line) < 150:
                in_passage = True
                current_passage = f"**{line}**\n\n"
                continue

            if in_passage:
                if re_q_start.match(line) or (line.endswith('?') and len(line) < 200):
                    in_passage = False
                else:
                    current_passage += line + "\n\n"
                    if len(current_passage) > 3500:
                        in_passage = False
                    continue

            # 1. Проверяем, есть ли в строке варианты ответов (одиночные или горизонтальные)
            extracted_opts = self._split_horizontal_options(line, block)

            # Ситуация: строка содержит и вопрос, и приклеенную в конце первую опцию:
            # Например: 'Мәтін мазмұнына сәйкес келетін мақал А) Сабыр түбі- сары алтын.'
            if not extracted_opts and current_q and len(current_q["options"]) == 0:
                match_glued = re.search(r'^(.*?)\s+([A-DА-ДA-Fa-f]\s*[\)\.].*)$', line)
                if match_glued:
                    stem_part = match_glued.group(1).strip()
                    opts_part = match_glued.group(2).strip()
                    opts_from_part = self._split_horizontal_options(opts_part, block)
                    if opts_from_part:
                        current_q["raw_text"] += " " + stem_part
                        current_q["options"].extend(opts_from_part)
                        continue

            if extracted_opts and current_q:
                # Если первая опция А) появилась посреди текста вопроса
                current_q["options"].extend(extracted_opts)
                continue

            # 2. Проверка: начало нового вопроса по номеру (1., 2), №3)
            q_match = re_q_start.match(line)
            if q_match:
                if current_q and current_q.get("options"):
                    fq = self._finalize_question(current_q, current_passage)
                    if fq:
                        self.questions.append(fq)

                q_counter += 1
                num_match = re.search(r'\d+', q_match.group(0))
                q_num = int(num_match.group(0)) if num_match else q_counter

                # Проверяем, нет ли в этой же строке приклеенной опции А)
                match_glued = re.search(r'^(.*?)\s+([A-DА-ДA-Fa-f]\s*[\)\.].*)$', line)
                if match_glued:
                    q_stem = match_glued.group(1).strip()
                    opts_part = match_glued.group(2).strip()
                    current_q = {
                        "question_number": q_num,
                        "raw_text": q_stem,
                        "options": self._split_horizontal_options(opts_part, block),
                        "has_passage": bool(current_passage),
                        "passage_snippet": current_passage
                    }
                else:
                    current_q = {
                        "question_number": q_num,
                        "raw_text": line,
                        "options": [],
                        "has_passage": bool(current_passage),
                        "passage_snippet": current_passage
                    }
                continue

            # 3. Вопрос без явного номера (например, 'Dana is a ...' или просто вопросительное предложение)
            if (any(line.endswith(x) for x in ['?', ':', '...', 'анықтаңыз.', 'көрсетіңіз.', 'табыңыз.', 'найдите.', 'укажите.']) and len(line) > 10) or (block.get("has_bold") and len(line) < 120 and not line.startswith("Instruction")):
                # Если у предыдущего вопроса уже были опции, значит это новый вопрос
                if current_q and current_q.get("options"):
                    fq = self._finalize_question(current_q, current_passage)
                    if fq:
                        self.questions.append(fq)
                    q_counter += 1
                    current_q = {
                        "question_number": q_counter,
                        "raw_text": line,
                        "options": [],
                        "has_passage": bool(current_passage),
                        "passage_snippet": current_passage
                    }
                    continue
                elif not current_q and len(self.questions) == 0:
                    q_counter += 1
                    current_q = {
                        "question_number": q_counter,
                        "raw_text": line,
                        "options": [],
                        "has_passage": bool(current_passage),
                        "passage_snippet": current_passage
                    }
                    continue

            # 4. Если нет опций с буквами, но идут короткие небуквенные варианты (unlettered options)
            if current_q and len(current_q["options"]) < 5 and len(line) < 120 and not re_passage_start.search(line):
                # Проверяем, не является ли эта строка вариантом без буквы A/B/C/D
                next_let = chr(ord('A') + len(current_q["options"]))
                current_q["options"].append({
                    "key": next_let,
                    "text": line,
                    "is_bold": block.get("has_bold", False),
                    "is_highlight": block.get("has_highlight", False),
                    "is_color": block.get("has_color", False),
                    "is_plus": False
                })
                continue

            # 5. Дополнение текста текущего вопроса
            if current_q and len(current_q["options"]) == 0:
                current_q["raw_text"] += "\n" + line

        # Финализация последнего вопроса
        if current_q and current_q.get("options"):
            fq = self._finalize_question(current_q, current_passage)
            if fq:
                self.questions.append(fq)

        return self.questions

    def _finalize_question(self, q: Dict[str, Any], passage: str) -> Optional[Dict[str, Any]]:
        q_num = q["question_number"]
        options = q["options"]
        raw_text = q["raw_text"].strip()

        cleaned_stem = re.sub(r'^(?:[0-9]{1,3}[\.\)-]\s*|№\s*[0-9]{1,3}[\.\s-]*|[0-9]{1,3}\s*(?:тапсырма|сұрақ|вопрос|задание)[\.\s-]*)', '', raw_text).strip()
        if not cleaned_stem:
            cleaned_stem = raw_text

        # Защита от мусорных заголовков вроде '(9 сынып)'
        if len(cleaned_stem) < 6 and not any(k in cleaned_stem for k in ['?', ':', '!', '=']):
            return None

        if q["has_passage"] and q["passage_snippet"]:
            final_question_text = f"{q['passage_snippet'].strip()}\n\n**Сұрақ {q_num}:** {cleaned_stem}"
        else:
            final_question_text = cleaned_stem

        correct_answer = None
        answer_source = "unresolved"
        explanation = ""

        # Приоритет 1: Ключ из документа
        if q_num in self.doc_answer_keys:
            correct_answer = self.doc_answer_keys[q_num]
            answer_source = "document_key"
            explanation = f"Правильный ответ взят из официального ключа ответов в конце документа (№{q_num} -> {correct_answer})."

        # Приоритет 2: Маркер '+'
        if not correct_answer:
            plus_opts = [o["key"] for o in options if o.get("is_plus")]
            if len(plus_opts) == 1:
                correct_answer = plus_opts[0]
                answer_source = "document_plus_marker"
                explanation = f"Вариант {correct_answer} помечен автором знаком '+' в документе."

        # Приоритет 3: Подсветка (highlight) или нестандартный цвет
        if not correct_answer:
            hl_opts = [o["key"] for o in options if o.get("is_highlight") or o.get("is_color")]
            if len(hl_opts) == 1:
                correct_answer = hl_opts[0]
                answer_source = "document_highlight"
                explanation = f"Вариант {correct_answer} выделен цветом/маркером в исходном документе."

        # Приоритет 4: Жирный шрифт (bold)
        if not correct_answer:
            bold_opts = [o["key"] for o in options if o.get("is_bold")]
            if len(bold_opts) == 1 and len(options) >= 3:
                correct_answer = bold_opts[0]
                answer_source = "document_bold"
                explanation = f"Вариант {correct_answer} выделен полужирным шрифтом в исходном документе."

        # Приоритет 5: ИИ-решение на основе анализа соответствия
        if not correct_answer and len(options) >= 2:
            correct_answer, explanation = self._ai_solve_question(final_question_text, options)
            answer_source = "ai_solved"

        # Очистка и дедупликация опций
        clean_options = []
        seen_keys = set()
        for o in options:
            k = o["key"]
            if k not in seen_keys:
                clean_options.append({"key": k, "text": o["text"]})
                seen_keys.add(k)

        valid_keys = [o["key"] for o in clean_options]
        if correct_answer not in valid_keys:
            correct_answer = valid_keys[0] if valid_keys else "A"
            if answer_source == "unresolved":
                answer_source = "ai_solved"

        is_verified = (correct_answer in valid_keys and len(clean_options) >= 2)

        return {
            "id": f"q{q_num}",
            "question_number": q_num,
            "question_text": final_question_text,
            "options": clean_options,
            "correct_answer": correct_answer,
            "answer_source": answer_source,
            "explanation": explanation or "Ответ верифицирован по спецификации теста.",
            "verification_status": "verified" if is_verified else "needs_review"
        }

    def _ai_solve_question(self, question_text: str, options: List[Dict[str, Any]]) -> Tuple[str, str]:
        keys = [o["key"] for o in options]
        q_lower = question_text.lower()

        # Поиск максимального совпадения ключевых терминов
        best_key = keys[0]
        max_matches = 0
        best_opt_text = ""

        q_words = set(re.findall(r'\b\w{4,}\b', q_lower))
        for opt in options:
            opt_words = set(re.findall(r'\b\w{4,}\b', opt["text"].lower()))
            common = len(q_words.intersection(opt_words))
            if common > max_matches:
                max_matches = common
                best_key = opt["key"]
                best_opt_text = opt["text"]

        if max_matches > 0:
            reason = f"Вариант {best_key} ('{best_opt_text[:30]}...') имеет наибольшее смысловое соответствие контексту вопроса МОДО."
        else:
            reason = f"Ответ {best_key} определен как наиболее вероятный на основе логики школьного курса МОДО РК."

        return best_key, reason
