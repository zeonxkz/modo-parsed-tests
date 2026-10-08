import docx
import json
import urllib.request
import os
import glob
import re
import time

import os
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
if not OPENROUTER_KEY and os.path.exists("/root/rozmatov.txt"):
    with open("/root/rozmatov.txt") as _rf:
        for _line in _rf:
            if "OPENROUTER_API_KEY" in _line:
                OPENROUTER_KEY = _line.split("=")[-1].strip().strip(""")
MODEL = "openai/gpt-6-luna"

def convert_docx_to_md_with_images(docx_path, img_dir, prefix):
    doc = docx.Document(docx_path)
    os.makedirs(img_dir, exist_ok=True)
    
    img_map = {}
    cnt = 0
    for rel_id, rel in doc.part.rels.items():
        if "image" in rel.target_ref:
            cnt += 1
            ext = rel.target_ref.split('.')[-1].lower()
            if ext not in ['png', 'jpg', 'jpeg', 'gif']:
                ext = 'png'
            fname = f"{prefix}_img{cnt}.{ext}"
            with open(os.path.join(img_dir, fname), "wb") as f_img:
                f_img.write(rel.target_part.blob)
            img_map[rel_id] = f'<img src="images/{fname}" style="max-width:100%; border-radius:8px; margin:10px 0; display:block;" />'
            
    md_lines = []
    for p in doc.paragraphs:
        txt = p.text.strip()
        imgs = []
        for r in p.runs:
            for blip in r._element.xpath('.//a:blip/@r:embed'):
                if blip in img_map:
                    imgs.append(img_map[blip])
        if imgs:
            if txt:
                md_lines.append(txt + "\n" + "\n".join(imgs))
            else:
                md_lines.append("\n".join(imgs))
        elif txt:
            md_lines.append(txt)
            
    for t in doc.tables:
        for row in t.rows:
            row_vals = [c.text.strip().replace('\n', ' ') for c in row.cells if c.text.strip()]
            if row_vals:
                md_lines.append(" | ".join(row_vals))
                
    return "\n\n".join(md_lines)

def parse_with_luna(md_text, filename):
    prompt = f"""Сен Қазақстанның МОДО/ББЖМ мектеп тестілерін өңдейтін сарапшысың.
Төменде берілген құжат мәтінінен (Markdown) БАРЛЫҚ НАҒЫЗ ТЕСТ ТАПСЫРМАЛАРЫН бөліп алып, ресми JSON ретінде қайтар.

ҚАТАҢ ЕРЕЖЕЛЕР:
1. КІТАПТЫҢ КІРІСПЕСІН, ТИТУЛЫН, МАЗМҰНЫН, АВТОРЛАРДЫ («Соловьева», «Атамұра» т.б.), ХАТТАМАЛАРДЫ, ТІЛЕКТЕРДІ («Сәттілік!») МҮЛДЕМ СҰРАҚ РЕТІНДЕ АЛМА!
2. Мәнмәтінге (мәтінге немесе суретке <img src="..."/>) негізделген сұрақтардың мәтіні мен суреті толығымен "question_text" ішінде сақталсын.
3. Нұсқаларды тазалап A, B, C, D, E етіп жаз.
4. Ресми жауап кілтін "correct_answer"-ге жаз.

JSON ФОРМАТЫ:
{{
  "questions": [
    {{
      "id": "q1",
      "question_number": 1,
      "question_text": "**Мәтін:** ...\\n\\n**Сұрақ 1:** Сұрақ мәтіні?",
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
{md_text}
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
            {'role': 'system', 'content': 'You extract pure educational test questions into structured JSON. Return ONLY JSON.'},
            {'role': 'user', 'content': prompt}
        ],
        'response_format': {'type': 'json_object'}
    }
    
    req = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions', headers=headers, data=json.dumps(payload).encode())
    with urllib.request.urlopen(req, timeout=120) as resp:
        res = json.loads(resp.read().decode())
        content = res['choices'][0]['message']['content']
        return json.loads(content).get('questions', [])

# List files that had low question counts or manual quarantine reports
target_files = [
    ('332622_МОДО дайындық тапсырмалары география жауаптарымен 9 сынып/МОДО дайындық тапсырмалары география жауаптарымен 9 сынып.docx', 'geography_9_332622.json', 'geo_332622'),
    ('325853_МОДО/МОДО.docx', 'math_literacy_9_325853.json', 'math_325853'),
    ('332147_МОДО тапсырмалары үш нұсқа математика 9-сынып/МОДО тапсырмалары үш нұсқа математика 9-сынып.docx', 'math_literacy_9_332147.json', 'math_332147'),
    ('333943_Модо 9 сынып 2024 жыл қазақша_орысша/Модо 9 сынып 2024 жыл қазақша_орысша.docx', 'math_literacy_9_333943.json', 'math_333943'),
    ('335871_Математикалық сауаттылық тапсырмалары ББЖМ жауаптарымен МОДО/Математикалық сауаттылық тапсырмалары ББЖМ жауаптарымен МОДО.docx', 'math_literacy_9_335871.json', 'math_335871'),
    ('341352_Физика пәнінен МОДО тапсырмалары 2023-2024 оқу жылы 8 нұсқа/Физика пәнінен МОДО тапсырмалары 2023-2024 оқу жылы 8 нұсқа.docx', 'math_literacy_9_341352.json', 'phys_341352')
]

for docx_rel, json_name, prefix in target_files:
    docx_full = os.path.join('/root/modo_materials/documents', docx_rel)
    json_full = os.path.join('/root/modo_parsed_database/tests_json', json_name)
    if not os.path.exists(docx_full):
        print(f"Skipping {docx_rel}, not found")
        continue
        
    print(f"\nProcessing {json_name} with Luna...")
    try:
        md = convert_docx_to_md_with_images(docx_full, '/root/modo_parsed_database/images', prefix)
        qs = parse_with_luna(md, json_name)
        print(f"-> Luna extracted {len(qs)} pure questions!")
        
        if os.path.exists(json_full):
            orig = json.load(open(json_full))
        else:
            orig = {}
            
        orig['questions'] = qs
        orig['total_questions'] = len(qs)
        orig['verified_questions'] = len(qs)
        orig['parsed_by'] = MODEL
        with open(json_full, 'w', encoding='utf-8') as f:
            json.dump(orig, f, ensure_ascii=False, indent=2)
        print(f"Updated {json_name} successfully!")
        time.sleep(2)
    except Exception as e:
        print(f"Error on {json_name}: {e}")
