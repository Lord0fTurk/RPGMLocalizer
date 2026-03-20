import os
import pathlib
import json
import codecs
import re
from src.core.parsers.json_parser import JsonParser

games = [
    "A Struggle With Sin 0.6.1.7 Winterhowl Part 2",
    "Aisha’s Futa Diaries EN", # The dir uses ’ instead of '
    "Peasants Quest NYD395"
]

# We might also just scan directories
game_dirs = [d for d in os.listdir("Oyunlar") if os.path.isdir(os.path.join("Oyunlar", d))]

parser = JsonParser()
parser.translate_notes = False

results = []

def audit_game(game_name):
    game_path = pathlib.Path("Oyunlar") / game_name / "www"
    if not game_path.exists():
        return
        
    print(f"\n{'='*50}\nAuditing: {game_name}\n{'='*50}\n")
    
    # 1. Check plugins.js deeply
    plugins_js = game_path / "js" / "plugins.js"
    if plugins_js.exists():
        extracted = parser.extract_text(str(plugins_js))
        total = len(extracted)
        print(f"[{game_name}] plugins.js: Extracted {total} strings.")
        
        # Analyze extracted strings for potential JS code (False Negatives of _is_technical_string)
        # i.e., things that we extracted but maybe we shouldn't have
        dangerous = []
        for path, text, ctx in extracted:
            text_clean = text.strip('"\' \n\r\t')
            # Look for JS assignments missed
            if re.fullmatch(r'^[a-zA-Z_]\w*\s*[+\-*/]?=\s*.*', text_clean) and text_clean.endswith(';'):
                dangerous.append((path, text, "Missed JS Assignment"))
            # Look for pure math or eval
            elif re.fullmatch(r'^[\d\s.+\-*/()>!=]+$', text_clean) and any(c.isdigit() for c in text_clean) and any(c in '+-*/' for c in text_clean):
                 dangerous.append((path, text, "Possible Math Eval"))
            # Look for variable declarations
            elif text_clean.startswith(('var ', 'let ', 'const ')):
                 dangerous.append((path, text, "JS Variable Decl"))
                 
        if dangerous:
            print(f"  --> WARNING: Found {len(dangerous)} potentially dangerous strings extracted from plugins.js!")
            for p, t, r in dangerous[:10]:
                print(f"      [{r}] {t[:50]}")
        else:
            print("  --> plugins.js extraction looks clean from obvious JS code leakages.")
            
    # 2. Check Data JSONs
    data_dir = game_path / "data"
    if data_dir.exists():
        json_files = [f for f in data_dir.iterdir() if f.suffix == '.json']
        print(f"[{game_name}] data/: Found {len(json_files)} JSON files. Scanning...")
        
        extracted_data = []
        for jf in json_files:
            try:
                ext = parser.extract_text(str(jf))
                extracted_data.extend(ext)
            except Exception as e:
                print(f"  --> ERROR reading {jf.name}: {e}")
                
        print(f"[{game_name}] data/: Total extracted strings: {len(extracted_data)}")
        
        # Look for False Positives in our strict checks?
        # Actually we just want to see if any strings contain weird things that might break translator
        # E.g., strings that contain ONLY escape codes
        weird_strings = []
        for path, text, ctx in extracted_data:
            # Check for strings that are completely dense with commands and might be broken
            if re.fullmatch(r'^(\\[a-zA-Z]+\[\d+\])+$', text.strip()):
                weird_strings.append((path, text, "Only Escape Codes"))
        
        if weird_strings:
            print(f"  --> INFO: Found {len(weird_strings)} strings with only escape codes.")
            # Generally safe, just good to know.

for g in game_dirs:
    audit_game(g)

print("\nAudit completed.")
