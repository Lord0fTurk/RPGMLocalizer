import json
import codecs
import os
import pathlib

# Path to the game
game_dir = pathlib.Path("Oyunlar") / "Peasants Quest NYD395" / "www"
plugins_js = game_dir / "js" / "plugins.js"

if not plugins_js.exists():
    print(f"Error: {plugins_js} not found.")
    exit(1)

with codecs.open(str(plugins_js), "r", "utf-8-sig") as f:
    content = f.read()

# Extract JSON
json_str = content.split('=', 1)[1].strip().rstrip(';')
try:
    data = json.loads(json_str)
except Exception as e:
    print("Cannot parse outer plugins.js JSON:", e)
    exit(1)

errors = []
target_plugins = ['YEP_QuestJournal']

for plugin in data:
    if plugin.get('name') in target_plugins:
        print(f"Found {plugin.get('name')}!")
        params = plugin.get('parameters', {})
        for key, val in params.items():
            if isinstance(val, str) and (val.startswith('{') or val.startswith('[')):
                try:
                    json.loads(val)
                except json.JSONDecodeError as e:
                    errors.append((key, val, str(e)))

print(f"Found {len(errors)} JSON decode errors in {target_plugins} parameters.")
with open("debug_output.txt", "w", encoding="utf-8") as out:
    out.write(f"Found {len(errors)} JSON decode errors.\n\n")
    for key, val, err in errors:
        out.write(f"--- Key: {key} ---\n")
        out.write(f"Error: {err}\n")
        out.write(f"Value:\n{val[:300]}...\n\n")

print("Done. Check debug_output.txt")
