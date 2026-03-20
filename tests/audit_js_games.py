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

game_dirs = [d for d in os.listdir("Oyunlar") if os.path.isdir(os.path.join("Oyunlar", d))]

parser = JsonParser()
parser.translate_notes = False

def audit_js(game_name):
    game_path = pathlib.Path("Oyunlar") / game_name / "www" / "js"
    if not game_path.exists():
        return
        
    print(f"\n{'='*50}\nAuditing JS: {game_name}\n{'='*50}\n")
    
    js_files = list(game_path.rglob("*.js"))
    # Filter out plugins.js
    js_files = [f for f in js_files if f.name.lower() != 'plugins.js']
    
    print(f"[{game_name}] Found {len(js_files)} raw JS files.")
    
    total_extracted = 0
    dangerous = []
    
    for jsf in js_files:
        try:
            extracted = parser.extract_text(str(jsf))
            total_extracted += len(extracted)
            
            for path, text, ctx in extracted:
                text_clean = text.strip('"\' \n\r\t')
                
                # Check for things that look like code
                # JS Assignments
                if re.fullmatch(r'^[a-zA-Z_]\w*\s*[+\-*/]?=\s*.*', text_clean) and text_clean.endswith(';'):
                    dangerous.append((jsf.name, text, "JS Assignment"))
                elif re.fullmatch(r'^[\d\s.+\-*/()>!=|&]+$', text_clean) and len(text_clean) > 3 and any(c in '+-*/><=!|&' for c in text_clean):
                    dangerous.append((jsf.name, text, "JS Eval/Condition"))
                elif text_clean.startswith(('var ', 'let ', 'const ', 'function ', 'return ')):
                    dangerous.append((jsf.name, text, "JS Keyword Start"))
                elif re.fullmatch(r'^[a-zA-Z_]\w*$', text_clean) and len(text_clean) > 1 and text_clean.islower() and " " not in text_clean:
                    # Might be extracting a single variable name or property key incorrectly
                    # Filter out short common strings but keep an eye
                    pass
                    
        except Exception as e:
            print(f"  --> ERROR reading {jsf.name}: {e}")
            
    print(f"[{game_name}] Extracted {total_extracted} strings from JS files.")
    
    if dangerous:
        print(f"  --> WARNING: Found {len(dangerous)} potentially dangerous strings extracted from JS files!")
        # Print top 15
        for f, t, r in dangerous[:15]:
            print(f"      [File: {f}] [{r}] {repr(t)[:50]}")
    else:
        print("  --> JS extraction looks clean from obvious JS code leakages.")

for g in game_dirs:
    audit_js(g)

print("\nJS Audit completed.")
