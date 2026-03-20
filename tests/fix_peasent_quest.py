import json
import codecs
import re
import pathlib

game_dir = pathlib.Path("Oyunlar") / "Peasants Quest NYD395" / "www"
plugins_js = game_dir / "js" / "plugins.js"

with codecs.open(str(plugins_js), "r", "utf-8-sig") as f:
    content = f.read()

prefix = content.split('=', 1)[0] + "="
json_str = content.split('=', 1)[1].strip().rstrip(';')
suffix = content[len(prefix) + len(json_str):]

data = json.loads(json_str)

def fix_json_string(val):
    if not isinstance(val, str): return val, False
    
    # It might be a dict {}, array [], or string ""
    if not (val.startswith('{') or val.startswith('[') or val.startswith('"')):
        return val, False
        
    fixed = False
    try:
        parsed = json.loads(val)
    except json.JSONDecodeError:
        # Fix bad backslash spaces like "\\ n", "\\ c", "\\ \\ "
        new_val = re.sub(r'\\ \s*([a-zA-Z{}])', r'\\\1', val)
        new_val = re.sub(r'\\\\ \s*([a-zA-Z{}])', r'\\\\\1', new_val)
        try:
            parsed = json.loads(new_val)
            print("Successfully recovered broken JSON string!")
            # Recurse
            if isinstance(parsed, dict):
                for k in parsed:
                    v, f = fix_json_string(parsed[k])
                    if f: parsed[k] = v
            elif isinstance(parsed, list):
                for idx, item in enumerate(parsed):
                    v, f = fix_json_string(item)
                    if f: parsed[idx] = v
            # If it was just a string '"something"', we just re-dump it after fix
            return json.dumps(parsed, ensure_ascii=False), True
        except json.JSONDecodeError as e:
            return val, False
    else:
        # Check recursively
        if isinstance(parsed, dict):
            for k in parsed:
                v, f = fix_json_string(parsed[k])
                if f:
                    parsed[k] = v
                    fixed = True
        elif isinstance(parsed, list):
            for idx, item in enumerate(parsed):
                v, f = fix_json_string(item)
                if f:
                    parsed[idx] = v
                    fixed = True
                    
        if fixed:
            return json.dumps(parsed, ensure_ascii=False), True
            
    return val, False

total_fixed = 0
for plugin in data:
    if plugin.get('name') == 'YEP_QuestJournal':
        params = plugin.get('parameters', {})
        for key, val in params.items():
            new_val, fixed = fix_json_string(val)
            if fixed:
                params[key] = new_val
                total_fixed += 1
                print(f"Fixed parameter '{key}'!")

if total_fixed > 0:
    new_json_str = json.dumps(data, separators=(',', ':'))
    new_content = prefix + new_json_str + ";"
    with codecs.open(str(plugins_js), "w", "utf-8") as f:
        f.write(new_content)
    print("Fix applied to game successfully!")
else:
    print("Nothing to fix.")
