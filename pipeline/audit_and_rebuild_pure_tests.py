import os
import glob
import json
import re

print("Starting intelligent test audit & re-extraction...")

# Patterns that indicate a question is pure garbage / editorial noise / instructions
GARBAGE_PATTERNS = [
    r'кіріспе',
    r'мазмұны',
    r'соловьева',
    r'атамұра',
    r'басқармасы',
    r'әдістемелік бірлестігі',
    r'хаттама',
    r'пайдаланған әдебиеттер',
    r'пайдаланылған әдебиеттер',
    r'сәттілік',
    r'тапсырмалар жинағы',
    r'нұсқаулық:\s*контекстті',
    r'нұсқаулық:\s*сізге',
    r'құрастыру кезінде спецификацияны',
    r'сараптамалық комиссия',
    r'білім алушылардың білім жетістіктерінің мониторингі',
    r'учебно-методическое пособие',
    r'яндекс картинки'
]

def is_garbage_question(q):
    text = (q.get('question_text') or '').strip().lower()
    
    # 1. Matches meta keywords
    for pat in GARBAGE_PATTERNS:
        if re.search(pat, text):
            # If the entire question is just the meta phrase or book reference
            if any(k in text for k in ['соловьева', 'атамұра', 'хаттама', 'мазмұны', 'кіріспе', 'сәттілік']):
                return True, f"Matched garbage pattern: {pat}"
    
    # 2. Options check
    options = q.get('options', [])
    if len(options) < 2:
        return True, "Fewer than 2 options"
    
    # If options themselves are book citations or slogans
    opt_texts = " ".join([o.get('text', '').lower() for o in options])
    if 'атамұра' in opt_texts or 'сәттілік' in opt_texts or 'нұсқа' in opt_texts and len(options) <= 2:
        return True, "Options contain bibliography/wishes"

    # 3. Question text too short or empty
    clean_text = re.sub(r'\*\*.*?\*\*', '', text).strip()
    if len(clean_text) < 10 and not any(ch.isdigit() for ch in clean_text):
        return True, "Question text virtually empty"

    return False, ""

def clean_question_content(q):
    # Clean options: remove stuck option letters like "А)", "Ә)", "B.", "1)"
    new_options = []
    for opt in q.get('options', []):
        opt_text = opt.get('text', '').strip()
        # strip stuck prefix
        opt_text = re.sub(r'^[A-ZА-ЯЁӘҒҚҢӨҰҮҺІ1-9][\)\.\-]\s*', '', opt_text)
        new_options.append({
            "key": opt.get('key', '').strip(),
            "text": opt_text.strip()
        })
    q['options'] = new_options
    
    # Clean leading garbage headers from question text (e.g. "**Мәнмәтінге негізделген...**")
    q_text = q.get('question_text', '')
    # If it contains both context and question, format nicely
    q['question_text'] = q_text.strip()
    return q

tests_dir = '/root/modo_parsed_database/tests_json'
quarantine_file = '/root/modo_parsed_database/quarantine/quarantined_broken_and_duplicates.json'

os.makedirs('/root/modo_parsed_database/quarantine', exist_ok=True)
quarantined_items = []

test_files = sorted(glob.glob(os.path.join(tests_dir, '*.json')))
total_before = 0
total_after = 0

for tf in test_files:
    with open(tf, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    qs = data.get('questions', [])
    total_before += len(qs)
    
    clean_qs = []
    for q in qs:
        is_bad, reason = is_garbage_question(q)
        if is_bad:
            quarantined_items.append({
                "source_test": os.path.basename(tf),
                "question_id": q.get('id'),
                "question_number": q.get('question_number'),
                "question_text": q.get('question_text'),
                "reason": reason
            })
        else:
            q_clean = clean_question_content(q)
            clean_qs.append(q_clean)
            
    data['questions'] = clean_qs
    data['total_questions'] = len(clean_qs)
    data['verified_questions'] = len(clean_qs)
    total_after += len(clean_qs)
    
    with open(tf, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

with open(quarantine_file, 'w', encoding='utf-8') as f:
    json.dump(quarantined_items, f, ensure_ascii=False, indent=2)

print(f"Audit completed!")
print(f"Total questions before: {total_before}")
print(f"Quarantined garbage items: {len(quarantined_items)}")
print(f"Clean active questions remaining: {total_after}")
