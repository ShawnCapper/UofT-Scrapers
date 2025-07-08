import csv
import re
import json

def parse_cost(text_block):
    """
    Extracts cost information from a block of text using a prioritized sequence of patterns.
    """
    range_decimal_match = re.search(r'(\d+\.\d{2})\s*(?:to|-)\s*(\d+\.\d{2})', text_block)
    if range_decimal_match:
        return {"min": float(range_decimal_match.group(1)), "max": float(range_decimal_match.group(2))}

    range_dollar_match = re.search(r'\$(\d+(?:\.\d{2})?)\s*(?:to|-)\s*\$?(\d+(?:\.\d{2})?)', text_block)
    if range_dollar_match:
        min_val = float(range_dollar_match.group(1))
        max_val_str = range_dollar_match.group(2).replace('$', '')
        max_val = float(max_val_str)
        return {"min": min_val, "max": max_val}

    single_dollar_match = re.search(r'\$(\d+(?:\.\d{2})?)', text_block)
    if single_dollar_match:
        return float(single_dollar_match.group(1))

    cost_line_match = re.search(r'^\s*Cost:\s*\$?(\d+(?:\.\d{2})?)', text_block, re.MULTILINE | re.IGNORECASE)
    if cost_line_match:
        return float(cost_line_match.group(1))

    single_decimal_match = re.search(r'\b(\d+\.\d{2})\b', text_block)
    if single_decimal_match:
        return float(single_decimal_match.group(1))
        
    currency_marker_match = re.search(r'(USD|CAD)\s*(\d+(?:\.\d{2})?)', text_block, re.IGNORECASE)
    if currency_marker_match:
        return float(currency_marker_match.group(2))

    return 0.0

def has_price(text_line):
    """
    Checks if a line of text contains a price, handling both floats and dicts from parse_cost.
    This function fixes the TypeError.
    """
    cost_result = parse_cost(text_line)
    if isinstance(cost_result, dict):
        return True  # A range was found.
    if isinstance(cost_result, (float, int)):
        return cost_result > 0  # A single price was found.
    return False

def merge_split_materials(materials):
    """
    Merges material entries that were incorrectly split.
    """
    if len(materials) <= 1:
        return materials

    merged_list = []
    i = 0
    while i < len(materials):
        current_item = materials[i]
        
        if i + 1 < len(materials):
            next_item = materials[i+1]
            
            if (isinstance(current_item.get('cost'), (int, float)) and current_item.get('cost') == 0.0 and
                isinstance(next_item.get('cost'), (int, float)) and next_item.get('cost') > 0.0):
                
                next_desc_lower = next_item['description'].lower().lstrip()
                if next_desc_lower.startswith('cost:') or next_desc_lower.startswith('used material guidelines:'):
                    current_item['description'] = f"{current_item['description']}\n{next_item['description']}"
                    current_item['cost'] = next_item['cost']
                    current_item['currency'] = next_item['currency']
                    
                    if next_item.get('notes') and next_item['notes'] not in current_item.get('notes', ''):
                         current_item['notes'] = (current_item.get('notes', '') + " " + next_item['notes']).strip()

                    if next_item.get('is_free_alternative_available'):
                        current_item['is_free_alternative_available'] = True
                        current_item['cost'] = 0.0

                    merged_list.append(current_item)
                    i += 2
                    continue
        
        merged_list.append(current_item)
        i += 1
        
    return merged_list

def parse_materials(raw_text):
    materials = []
    
    raw_text_lower = raw_text.lower()
    no_cost_phrases = [
        'no cost', 'no purchases', '0$', '$0', 'n/a', 'no textbook', 'none', 
        'freely available', 'provided for free', 'no materials', 'no additional cost',
        'accessible through uoft library', 'available via the library', 'zero dollars',
        'all materials are provided', 'not applicable'
    ]
    if any(phrase in raw_text_lower for phrase in no_cost_phrases) and len(raw_text) < 100:
        return [{
            "description": raw_text.strip(),
            "cost": 0.0,
            "currency": "CAD",
            "is_free_alternative_available": True,
            "notes": "All materials are provided at no cost."
        }]

    items = re.split(r'\n\s*\n|\n(?=Learning Material:)|(?<=\.)\s*\n(?=Material:)', raw_text, flags=re.IGNORECASE)
    
    processed_items = []
    for item in items:
        lines = item.strip().split('\n')
        # This heuristic splits items that are clearly lists of books, like in CHC370
        if len(lines) > 1:
            # *** THIS IS THE CORRECTED LINE ***
            price_count = sum(1 for line in lines if has_price(line))
            if price_count > 1 and price_count / len(lines) >= 0.5:
                processed_items.extend(lines)
            else:
                processed_items.append(item)
        else:
            processed_items.append(item)

    for item_text in processed_items:
        if not item_text.strip():
            continue

        cost = parse_cost(item_text)
        currency = "USD" if "USD" in item_text or "US$" in item_text else "CAD"
        
        notes = []
        if "used version is acceptable" in item_text.lower() or "used is fine" in item_text.lower() or "used copies acceptable" in item_text.lower():
            notes.append("Used version is acceptable.")
        if "must be new" in item_text.lower() or "is not acceptable" in item_text.lower():
            notes.append("Must be a new version.")
        
        free_alt_phrases = [
            'available via uoft library', 'available through the uoft library',
            'available through u of t library', 'available on course reserve',
            'free e-copy', 'freely available online', 'open access', 'library reading list',
            'syllabus service', 'available online for free', 'available at the library'
        ]
        is_free_alt = any(phrase in item_text.lower() for phrase in free_alt_phrases)
        
        if is_free_alt:
            notes.append("A free alternative is available through the university.")

        effective_cost = 0.0 if is_free_alt else cost

        material_obj = {
            "description": item_text.strip().replace('"',"'"),
            "cost": effective_cost,
            "currency": currency,
            "is_free_alternative_available": is_free_alt,
            "notes": " ".join(notes) if notes else "No specific notes on used versions or alternatives."
        }
        materials.append(material_obj)

    return materials if materials else [{
            "description": raw_text.strip(),
            "cost": 0.0,
            "currency": "CAD",
            "is_free_alternative_available": True,
            "notes": "No specific materials with cost listed."
        }]

def process_csv(file_path):
    all_courses_data = []
    with open(file_path, mode='r', encoding='utf-8-sig') as infile:
        reader = csv.reader(infile)
        header = next(reader)  # Skip header

        for row in reader:
            if not row or not row[0].strip():
                continue
            
            course_code, mandatory_raw, optional_raw = row

            mandatory_parsed = parse_materials(mandatory_raw)
            mandatory_final = merge_split_materials(mandatory_parsed)
            
            optional_parsed = parse_materials(optional_raw)
            optional_final = merge_split_materials(optional_parsed)

            course_data = {
                "course_code": course_code.strip(),
                "mandatory_materials": mandatory_final,
                "optional_materials": optional_final
            }
            all_courses_data.append(course_data)
            
    return all_courses_data


# Main execution
csv_file_path = 'Courses-MaterialCosts/MaterialCost_Winter2025.csv'
structured_data = process_csv(csv_file_path)

# Save to JSON file
output_file_path = 'structured_course_costs.json'
with open(output_file_path, 'w', encoding='utf-8') as outfile:
    json.dump(structured_data, outfile, indent=4)

print(f"Successfully processed {len(structured_data)} courses.")
print(f"Corrected structured data saved to '{output_file_path}'")
