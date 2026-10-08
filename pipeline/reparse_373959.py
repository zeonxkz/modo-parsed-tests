import docx
import re
import json

doc = docx.Document('/root/modo_materials/documents/373959_9-сыныпқа арналған МОДО тапсырмалары, жауаптарымен/9-сыныпқа арналған МОДО тапсырмалары, жауаптарымен.docx')
paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

questions = []
current_context = ""
i = 0
while i < len(paras):
    p = paras[i]
    if len(p) > 120 and not re.match(r'^\d+[\.\)]', p):
        current_context = p
        i += 1
        continue
    
    m = re.match(r'^(\d+)[\.\)]\s*(.*)', p)
    if m:
        q_num = int(m.group(1))
        q_text = m.group(2).strip()
        i += 1
        options = []
        answer_text = ""
        
        while i < len(paras):
            next_p = paras[i]
            ans_m = re.match(r'^жауаб[ыі]:\s*(.*)', next_p, re.IGNORECASE)
            if ans_m:
                answer_text = ans_m.group(1).strip()
                i += 1
                break
            
            if re.match(r'^\d+[\.\)]', next_p):
                break
                
            opt_matches = list(re.finditer(r'([А-ЯЁӘҒҚҢӨҰҮҺІA-Z])[\)\.\-]\s*([^А-ЯЁӘҒҚҢӨҰҮҺІA-Z\n\)]+)', next_p))
            single_opt = re.match(r'^([А-ЯЁӘҒҚҢӨҰҮҺІA-Z])[\)\.\-]\s*(.*)', next_p)
            
            if len(opt_matches) > 1:
                for om in opt_matches:
                    options.append({"key": om.group(1), "text": om.group(2).strip()})
                i += 1
            elif single_opt:
                options.append({"key": single_opt.group(1), "text": single_opt.group(2).strip()})
                i += 1
            else:
                if len(options) == 0 and len(next_p) > 100:
                    current_context = next_p
                i += 1
                break
        
        correct_key = "A"
        if answer_text:
            for opt in options:
                if opt['text'].lower() == answer_text.lower() or opt['key'].lower() == answer_text.lower() or answer_text.lower() in opt['text'].lower():
                    correct_key = opt['key']
                    break
        
        if len(options) >= 2:
            questions.append({
                "id": f"q{len(questions)+1}",
                "question_number": q_num,
                "context": current_context,
                "question_text": f"**Мәтін:** {current_context}\n\n**Сұрақ {q_num}:** {q_text}" if current_context else q_text,
                "options": options,
                "correct_answer": correct_key,
                "answer_source": "document_key" if answer_text else "ai_solved",
                "explanation": f"Ресми кілт: {answer_text}" if answer_text else "",
                "verification_status": "verified"
            })
    else:
        if len(p) > 120:
            current_context = p
        i += 1

with open('/root/modo_parsed_database/tests_json/biology_9_373959.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

d['questions'] = questions
d['total_questions'] = len(questions)
d['verified_questions'] = len(questions)

with open('/root/modo_parsed_database/tests_json/biology_9_373959.json', 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print(f"biology_9_373959.json successfully re-written with {len(questions)} pure test questions!")
