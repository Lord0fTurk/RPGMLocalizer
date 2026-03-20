import json
import codecs
import pathlib

game_dir = pathlib.Path("Oyunlar") / "Peasants Quest NYD395" / "www"
plugins_js = game_dir / "js" / "plugins.js"

with codecs.open(str(plugins_js), "r", "utf-8-sig") as f:
    content = f.read()

json_str = content.split('=', 1)[1].strip().rstrip(';')
data = json.loads(json_str)

params = None
for plugin in data:
    if plugin.get('name') == 'YEP_QuestJournal':
        params = plugin.get('parameters', {})
        break

with open("output2_utf8.txt", "w", encoding="utf-8") as out:
    if params:
        out.write("--------------------------------------------------\n")
        out.write("Keys starting with 'Quest Data':\n")
        qd_format = ""
        for k in params:
            if "Quest Data" in k:
                out.write(f"Key: {k}\n")
                if k == "Quest Data Format":
                    qd_format = params[k]
                    
        out.write("\n--- Quest Data Format Value ---\n")
        out.write(repr(qd_format) + "\n")
        try:
            parsed = json.loads(qd_format)
            out.write(f"Valid JSON! Parsed value length: {len(parsed)}\n")
        except Exception as e:
            out.write(f"JSON Error on Quest Data Format: {e}\n")
        
        # Let's also check the actual structure of Quest Data Window parameter since the plugin accesses Yanfly.Param.QuestDataWindow['Quest Data Format']
        for k in params:
            if "Quest Data Window" in k or k == "Quest Data Window":
                out.write(f"\n--- {k} Value ---\n")
                out.write(repr(params[k]) + "\n")
                try:
                    parsed = json.loads(params[k])
                    out.write(f"Valid JSON! Keys inside: {parsed.keys() if isinstance(parsed, dict) else type(parsed)}\n")
                    if isinstance(parsed, dict) and 'Quest Data Format' in parsed:
                         out.write(f"Quest Data Format inside Window: {repr(parsed['Quest Data Format'])}\n")
                         json.loads(parsed['Quest Data Format'])
                except Exception as e:
                    out.write(f"JSON Error: {e}\n")
