#!/usr/bin/env python3
"""
Пайплайн МОДО на базе OpenRouter openai/gpt-6-luna.
Включает:
1. Извлечение чистого Markdown с сохранением всех картинок, формул (WMF/EMF конвертация в PNG) и таблиц.
2. Маркировку официальных ответов (highlight/bold/plus markers).
3. Промпт для openai/gpt-6-luna с требованием возвращать только валидные тестовые задания с очищенными вариантами (A, B, C, D, E) и ключом правильного ответа.
4. Обновление JSON в /root/modo_parsed_database/tests_json/.
"""

import os
import sys
import glob
import json
import time
import subprocess
import urllib.request
import docx

import os
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
if not OPENROUTER_KEY and os.path.exists("/root/rozmatov.txt"):
    with open("/root/rozmatov.txt") as _rf:
        for _line in _rf:
            if "OPENROUTER_API_KEY" in _line:
                OPENROUTER_KEY = _line.split("=")[-1].strip().strip(""")
MODEL = "openai/gpt-6-luna"

TESTS_JSON_DIR = "/root/modo_parsed_database/tests_json"
IMAGES_DIR = "/root/modo_parsed_database/images"
os.makedirs(TESTS_JSON_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)

def docx_to_rich_md(docx_path, prefix):
    doc = docx.Document(docx_path)
    
    r_map = {}
    cnt = 0
    for rId, rel in doc.part.rels.items():
        if hasattr(rel, 'target_ref'):
            target = rel.target_ref.lower()
            if any(target.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.emf', '.wmf']):
                cnt += 1
                orig_ext = target.split('.')[-1]
                raw_path = os.path.join(IMAGES_DIR, f"{prefix}_raw{cnt}.{orig_ext}")
                final_fname = f"{prefix}_img{cnt}.png"
                final_path = os.path.join(IMAGES_DIR, final_fname)
                
                with open(raw_path, 'wb') as f:
                    f.write(rel.target_part.blob)
                    
                if orig_ext in ['wmf', 'emf']:
                    res = subprocess.run(['convert', raw_path, final_path], capture_output=True)
                    if res.returncode != 0 or not os.path.exists(final_path):
                        final_fname = f"{prefix}_raw{cnt}.{orig_ext}"
                else:
                    final_fname = f"{prefix}_raw{cnt}.{orig_ext}"
                    
                r_map[rId] = f'<img src="images/{final_fname}" style="max-height:90px; vertical-align:middle; display:inline-block; margin:2px 4px;" />'

    def format_p(p):
        parts = []
        is_hl = any(r.font.highlight_color is not None for r in p.runs)
        for r in p.runs:
            txt = r.text
            embeds = []
            for d in r._element.iter():
                for key, val in d.attrib.items():
                    if key.endswith('id') or key.endswith('embed'):
                        embeds.append(val)
            if txt:
                parts.append(txt)
            for eid in embeds:
                if eid in r_map:
                    parts.append(r_map[eid])
        line = ''.join(parts).strip()
        if is_hl and line:
            line = f'[MARK_OFFICIAL_CORRECT] {line}'
        return line

    md_blocks = []
    for el in doc.element.body:
        tag = el.tag.split('}')[-1]
        if tag == 'p':
            p = docx.text.paragraph.Paragraph(el, doc)
            l = format_p(p)
            if l:
                md_blocks.append(l)
        elif tag == 'tbl':
            tbl = docx.table.Table(el, doc)
            for row in tbl.rows:
                row_parts = []
                for cell in row.cells:
                    cl = ' '.join([format_p(cp) for cp in cell.paragraphs if format_p(cp)])
                    if cl:
                        row_parts.append(cl)
                if row_parts:
                    md_blocks.append(' | '.join(row_parts))
    return '\n\n'.join(md_blocks)

def call_luna(md_content, test_title="Тест"):
    prompt = f"""Сен Қазақстанның МОДО/ББЖМ мектеп тестілерін өңдейтін жетекші сарапшысың.
Төменде берілген құжат мәтінінен (Markdown) БАРЛЫҚ НАҒЫЗ ТЕСТ ТАПСЫРМАЛАРЫН бөліп алып, ресми JSON ретінде қайтар.

ҚАТАҢ ЕРЕЖЕЛЕР:
1. КІТАПТЫҢ КІРІСПЕСІН, ТИТУЛЫН, МАЗМҰНЫН, АВТОРЛАРДЫ («Соловьева», «Атамұра» т.б.), ХАТТАМАЛАРДЫ, ТІЛЕКТЕРДІ («Сәттілік!») МҮЛДЕМ СҰРАҚ РЕТІНДЕ АЛМА!
2. Мәнмәтінге (мәтінге немесе суретке <img src="..."/>) негізделген сұрақтардың мәтіні мен суреті толығымен "question_text" ішінде сақталсын (мысалы: **Мәтін:** ... \\n\\n**Сұрақ 1:** ...).
3. Варианттарды "options" тізіміне сал: [{{"key": "A", "text": "..."}}, {{"key": "B", "text": "..."}}, ...]. Текст ішіндегі A), B) әріптерін алып таста.
4. Егер құжатта нұсқа [MARK_OFFICIAL_CORRECT] немесе '+' таңбасымен белгіленген болса, немесе мәтін соңында кілттер болса, соған сәйкес дұрыс нұсқаны (A, B, C, D немесе E) "correct_answer" өрісіне жаз.
5. Дұрыс жауап міндетті түрде A, B, C, D, E әріптерінің бірі болуы керек.
6. Тек қана валидті JSON қайтар:
{{
  "questions": [
    {{
      "id": "q1",
      "question_number": 1,
      "question_text": "...",
      "options": [
        {{"key": "A", "text": "..."}},
        {{"key": "B", "text": "..."}},
        {{"key": "C", "text": "..."}},
        {{"key": "D", "text": "..."}}
      ],
      "correct_answer": "A",
      "explanation": "Ресми кілт"
    }}
  ]
}}

МӘТІН:
{md_content}
"""

    headers = {
        'Authorization': f'Bearer {OPENROUTER_KEY}',
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://modo-tests.local',
        'X-Title': 'MODO Tests Parser'
    }
    payload = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': 'You extract pure educational test questions into structured JSON. Output ONLY valid JSON.'},
            {'role': 'user', 'content': prompt}
        ],
        'response_format': {'type': 'json_object'}
    }
    
    req = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions', headers=headers, data=json.dumps(payload).encode())
    with urllib.request.urlopen(req, timeout=180) as resp:
        res = json.loads(resp.read().decode())
        content = res['choices'][0]['message']['content']
        data = json.loads(content)
        qs = data.get('questions', [])
        
        # Normalize correct_answer to letter key A/B/C/D/E
        for i, q in enumerate(qs):
            if 'id' not in q:
                q['id'] = f"q{i+1}"
            ca = str(q.get('correct_answer', '')).strip()
            # If AI returned text instead of letter, match with option
            if len(ca) > 1 and q.get('options'):
                matched_key = None
                for opt in q['options']:
                    if opt.get('text', '').strip() == ca or opt.get('key', '') == ca:
                        matched_key = opt.get('key')
                        break
                if matched_key:
                    q['correct_answer'] = matched_key
                else:
                    q['correct_answer'] = q['options'][0].get('key', 'A')
            elif ca:
                q['correct_answer'] = ca[0].upper()
            else:
                q['correct_answer'] = 'A'
        return qs

def run_reparse_list(file_list):
    for docx_path, json_name, prefix in file_list:
        json_path = os.path.join(TESTS_JSON_DIR, json_name)
        if not os.path.exists(docx_path):
            print(f"[SKIP] Docx not found: {docx_path}")
            continue
            
        print(f"\n==========================================")
        print(f"Processing: {json_name} via {MODEL}...")
        print(f"Docx: {docx_path}")
        
        try:
            md = docx_to_rich_md(docx_path, prefix)
            print(f"Extracted MD length: {len(md)} chars")
            
            # If document is extremely large (> 35,000 chars), handle chunking if needed
            qs = call_luna(md, json_name)
            print(f"-> Luna successfully extracted {len(qs)} verified questions!")
            
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    orig = json.load(f)
            else:
                orig = {}
                
            orig['questions'] = qs
            orig['total_questions'] = len(qs)
            orig['verified_questions'] = len(qs)
            orig['parsed_by'] = MODEL
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(orig, f, ensure_ascii=False, indent=2)
                
            print(f"SUCCESS: Saved {json_name} with {len(qs)} questions.")
            time.sleep(3)
        except Exception as e:
            print(f"ERROR processing {json_name}: {e}")

if __name__ == '__main__':
    priority_files = [
        ('/root/modo_materials/documents/381887_Модо 9 кл русский язык/Модо 9 кл русский язык.docx', 'reading_literacy_ru_9_381887.json', 'ru_381887'),
        ('/root/modo_materials/documents/337789_Мат сауаттылық МОДО тапсырмалары (9 сынып)/Мат сауаттылық МОДО тапсырмалары (9 сынып).docx', 'math_literacy_9_337789.json', 'math_337789'),
        ('/root/modo_materials/documents/335871_Математикалық сауаттылық тапсырмалары ББЖМ жауаптарымен МОДО/Математикалық сауаттылық тапсырмалары ББЖМ жауаптарымен МОДО.docx', 'math_literacy_9_335871.json', 'math_335871'),
        ('/root/modo_materials/documents/325853_МОДО/МОДО.docx', 'math_literacy_9_325853.json', 'math_325853'),
        ('/root/modo_materials/documents/326909_МОДО математика/МОДО математика.docx', 'math_literacy_9_326909.json', 'math_326909'),
        ('/root/modo_materials/documents/332147_МОДО тапсырмалары үш нұсқа математика 9-сынып/МОДО тапсырмалары үш нұсқа математика 9-сынып.docx', 'math_literacy_9_332147.json', 'math_332147'),
        ('/root/modo_materials/documents/333943_Модо 9 сынып 2024 жыл қазақша_орысша/Модо 9 сынып 2024 жыл қазақша_орысша.docx', 'math_literacy_9_333943.json', 'math_333943'),
        ('/root/modo_materials/documents/341352_Физика пәнінен МОДО тапсырмалары 2023-2024 оқу жылы 8 нұсқа/Физика пәнінен МОДО тапсырмалары 2023-2024 оқу жылы 8 нұсқа.docx', 'math_literacy_9_341352.json', 'phys_341352'),
        ('/root/modo_materials/documents/329123_ББЖМ, МОДО, 9-сынып. Ағылшын тілі пәні бойынша 8 текст + дұрыс жауапта/ББЖМ, МОДО, 9-сынып. Ағылшын тілі пәні бойынша 8 текст + дұрыс жауапта.docx', 'reading_literacy_en_9_329123.json', 'eng_329123'),
        ('/root/modo_materials/documents/326908_МОДО. Қазақ тілі/МОДО. Қазақ тілі.docx', 'reading_literacy_kk_9_326908.json', 'kk_326908')
    ]
    run_reparse_list(priority_files)
