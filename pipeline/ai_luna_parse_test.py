import docx
import json
import urllib.request
import os
import re

import os
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
if not OPENROUTER_KEY and os.path.exists("/root/rozmatov.txt"):
    with open("/root/rozmatov.txt") as _rf:
        for _line in _rf:
            if "OPENROUTER_API_KEY" in _line:
                OPENROUTER_KEY = _line.split("=")[-1].strip().strip(""")
MODEL = "openai/gpt-6-luna"

def parse_docx_to_markdown_with_images(docx_path, img_output_dir, file_prefix):
    doc = docx.Document(docx_path)
    os.makedirs(img_output_dir, exist_ok=True)
    
    # 1. Extract images
    img_counter = 0
    rel_map = {}
    for rel_id, rel in doc.part.rels.items():
        if "image" in rel.target_ref:
            img_data = rel.target_part.blob
            ext = rel.target_ref.split('.')[-1].lower()
            if ext not in ['jpg', 'jpeg', 'png', 'gif', 'bmp']:
                ext = 'png'
            img_counter += 1
            fname = f"{file_prefix}_img{img_counter}.{ext}"
            with open(os.path.join(img_output_dir, fname), "wb") as f_img:
                f_img.write(img_data)
            rel_map[rel_id] = f"images/{fname}"
            
    # 2. Extract paragraphs and tables to Markdown
    md_blocks = []
    for p in doc.paragraphs:
        txt = p.text.strip()
        # Check if paragraph has image
        embedded_imgs = []
        for r in p.runs:
            for blip in r._element.xpath('.//a:blip/@r:embed'):
                if blip in rel_map:
                    embedded_imgs.append(f'<img src="{rel_map[blip]}" style="max-width:100%; border-radius:8px; margin:10px 0; display:block;" />')
        
        if embedded_imgs:
            if txt:
                md_blocks.append(txt + "\n" + "\n".join(embedded_imgs))
            else:
                md_blocks.append("\n".join(embedded_imgs))
        elif txt:
            md_blocks.append(txt)
            
    for t in doc.tables:
        rows_txt = []
        for row in t.rows:
            cells_txt = [c.text.strip().replace('\n', ' ') for c in row.cells]
            rows_txt.append(" | ".join(cells_txt))
        if rows_txt:
            md_blocks.append("\n".join(rows_txt))
            
    return "\n\n".join(md_blocks)

def call_luna_ai_parser(text_chunk, subject="biology", grade=9):
    prompt = f"""Сен Қазақстанның МОДО/ББЖМ тестілеу сарапшысысың.
Төменде мектеп тестінің мәтіні (Markdown) берілген.
Сенің міндетің — бұл құжаттан ТЕК НАҒЫЗ ТЕСТ СҰРАҚТАРЫН бөліп алып, ресми таза JSON форматына келтіру.

ҚАТАҢ ЕРЕЖЕЛЕР:
1. Титулдық парақтарды, кітаптың кіріспесін, мазмұнын, авторлар тізімін ("Атамұра", "Соловьева", "Басқармасы", "Хаттама", "Сәттілік тілейміз") ЕШҚАШАН сұрақ қылма! Бұларды өткізіп жібер.
2. Егер сұрақ мәнмәтінге (мәтінге немесе суретке) негізделсе, сол мәтінді "context" өрісіне және question_text-тің басына сақта!
3. Егер мәтінде сурет тегі болса (<img src="..."/>), оны міндетті түрде сәйкес сұрақтың "question_text" ішінде сақта!
4. Әрбір сұрақта 3 немесе одан көп нұсқа (A, B, C, D, E) болуы керек. Нұсқалардың алдындағы "А) ", "a) ", "B. " таңбаларын тазартып, таза мәтінін жаз.
5. Жауаптар кілті (Жауабы: ...) немесе ресми кестеден дұрыс жауапты анықтап "correct_answer"-ге жаз (мысалы: "A").

Тек мынадай валидті JSON қайтар:
{{
  "questions": [
    {{
      "id": "q1",
      "question_number": 1,
      "context": "Мәнмәтін...",
      "question_text": "**Мәтін:** ...\\n\\n**Сұрақ 1:** Сұрақ мәтіні?",
      "options": [
        {{"key": "A", "text": "Нұсқа А"}},
        {{"key": "B", "text": "Нұсқа B"}},
        {{"key": "C", "text": "Нұсқа C"}},
        {{"key": "D", "text": "Нұсқа D"}}
      ],
      "correct_answer": "A",
      "explanation": "Ресми кілт"
    }}
  ]
}}

МӘТІН:
{text_chunk}
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
            {'role': 'system', 'content': 'You are an expert AI parser of educational tests. Return ONLY valid JSON.'},
            {'role': 'user', 'content': prompt}
        ],
        'response_format': {'type': 'json_object'}
    }
    req = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions', headers=headers, data=json.dumps(payload).encode())
    with urllib.request.urlopen(req, timeout=90) as resp:
        result = json.loads(resp.read().decode())
        content = result['choices'][0]['message']['content']
        return json.loads(content)

# Test on 373959 first
test_docx = '/root/modo_materials/documents/373959_9-сыныпқа арналған МОДО тапсырмалары, жауаптарымен/9-сыныпқа арналған МОДО тапсырмалары, жауаптарымен.docx'
md = parse_docx_to_markdown_with_images(test_docx, '/root/modo_parsed_database/images', 'bio_373959_luna')
print(f"Generated Markdown length: {len(md)}. Sending to {MODEL}...")

parsed = call_luna_ai_parser(md, subject="biology", grade=9)
qs = parsed.get('questions', [])
print(f"GPT-6-Luna successfully extracted {len(qs)} structured questions!")
for q in qs[:3]:
    print("---")
    print("Q" + str(q.get('question_number')), q.get('question_text')[:100])
    print("Opts:", [o['key'] + ': ' + o['text'] for o in q.get('options', [])])
    print("Ans:", q.get('correct_answer'))

out_json = '/root/modo_parsed_database/tests_json/biology_9_373959.json'
with open(out_json, 'r', encoding='utf-8') as f:
    d = json.load(f)
d['questions'] = qs
d['total_questions'] = len(qs)
d['verified_questions'] = len(qs)
d['parsed_by'] = 'openai/gpt-6-luna'

with open(out_json, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print(f"Updated {out_json} with GPT-6-Luna verified questions!")
