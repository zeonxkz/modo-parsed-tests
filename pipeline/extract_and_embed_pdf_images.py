import fitz
import os
import glob
import json
import re

print("Starting automatic PDF image extraction and question linking...")

output_img_dir = "/root/modo_parsed_database/images"
os.makedirs(output_img_dir, exist_ok=True)

# Map pdf documents to tests_json
# Find all PDF files in modo_materials
pdf_files = glob.glob("/root/modo_materials/**/*.pdf", recursive=True)
print(f"Found {len(pdf_files)} PDF files in modo_materials.")

for pdf_path in pdf_files:
    pdf_basename = os.path.basename(pdf_path)
    # Find matching json
    parent_dir = os.path.basename(os.path.dirname(pdf_path))
    # Extract ID from parent dir or filename e.g. "321395"
    m = re.search(r'(\d{6})', parent_dir) or re.search(r'(\d{6})', pdf_basename)
    if not m:
        continue
    file_id = m.group(1)
    
    # Find corresponding JSON file in tests_json
    matching_jsons = glob.glob(f"/root/modo_parsed_database/tests_json/*_{file_id}.json")
    if not matching_jsons:
        print(f"No json found for file_id {file_id}")
        continue
        
    json_path = matching_jsons[0]
    with open(json_path, 'r', encoding='utf-8') as f:
        test_data = json.load(f)
        
    doc = fitz.open(pdf_path)
    print(f"\nProcessing {pdf_basename} ({len(doc)} pages) -> {os.path.basename(json_path)}")
    
    # Extract images per page
    # Map page number (1-indexed) to list of extracted image paths
    page_images = {}
    for pno in range(len(doc)):
        page = doc[pno]
        img_list = page.get_images(full=True)
        if not img_list:
            continue
            
        page_img_paths = []
        for img_idx, img_info in enumerate(img_list):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            # Filter out tiny icon / decoration images (< 500 bytes or < 50px)
            if len(image_bytes) < 1000 or base_image.get("width", 0) < 60:
                continue
                
            img_filename = f"pdf_{file_id}_p{pno+1}_img{img_idx+1}.{image_ext}"
            img_disk_path = os.path.join(output_img_dir, img_filename)
            with open(img_disk_path, "wb") as f_img:
                f_img.write(image_bytes)
            page_img_paths.append(img_filename)
            
        if page_img_paths:
            page_images[pno + 1] = page_img_paths

    print(f"Extracted images for {len(page_images)} pages in {pdf_basename}.")
    
    # Now link images into questions!
    # A question with "Суретте", "суреттен", "диаграмма", "график", "сурет" on or near that page gets the image!
    questions = test_data.get('questions', [])
    updated_q_count = 0
    
    # Match questions in text to their pages
    # Or match based on question text search in page text
    for q in questions:
        q_text = q.get('question_text', '')
        # Check if question text mentions an image
        has_image_ref = any(w in q_text.lower() for w in ['сурет', 'суретте', 'суреттен', 'диаграмма', 'сызба', 'график', 'рисунок', 'рисунке'])
        
        # Search which page this question appears on in the PDF
        q_snippet = re.sub(r'[*_\n]', ' ', q_text).strip()
        # take first 40 distinct chars of the actual question
        # remove prefix "Сұрақ X:"
        search_snippet = re.sub(r'^.*?Сұрақ\s*\d+:\s*', '', q_snippet)[:35].strip()
        
        matched_page = None
        for pno in range(len(doc)):
            page_txt = doc[pno].get_text()
            if search_snippet and search_snippet.lower() in page_txt.lower():
                matched_page = pno + 1
                break
                
        if matched_page and matched_page in page_images:
            imgs = page_images[matched_page]
            # Embed image into question_text if not already present
            img_tags = "".join([f"\n\n<img src=\"images/{img_name}\" style=\"max-width:100%; border-radius:8px; margin:10px 0; display:block;\" />" for img_name in imgs])
            if "<img" not in q['question_text']:
                q['question_text'] = q['question_text'] + img_tags
                updated_q_count += 1
        elif has_image_ref:
            # If search_snippet failed, look for nearby pages
            pass

    test_data['questions'] = questions
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(test_data, f, ensure_ascii=False, indent=2)
    print(f"Successfully linked images to {updated_q_count} questions in {os.path.basename(json_path)}!")

print("\nPDF image extraction and linking finished!")
