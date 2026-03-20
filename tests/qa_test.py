import re

def is_js_assignment(text):
    text = text.strip()
    
    # 1. Has semicolon -> almost certainly JS (e.g., "show = true;")
    if re.fullmatch(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?\s*(?:[+\-*/]?={1,3}|!==?)\s*(?:true|false|null|undefined|!?[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?)*|\d+);$', text):
        return True
        
    # 2. No semicolon, but RHS is a JS keyword/identifier (true, false, null, undefined)
    # UI doesn't usually say "Status = true" (it might, but very rare compared to JS code)
    if re.fullmatch(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?\s*(?:={1,3}|!==?)\s*(?:true|false|null|undefined)$', text):
        return True
        
    # 3. Compound operators (+=, -=, *=, /=) without semicolon
    if re.fullmatch(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?\s*(?:[+\-*/]={1,2})\s*(?:!?[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?)*|\d+)$', text):
        return True
        
    # 4. Bracket notation or property access on either side (e.g. A[b] = c, a = b.c)
    if re.fullmatch(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])+\s*(?:={1,3}|!==?)\s*(?:!?[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?)*|\d+)$', text):
        return True
    if re.fullmatch(r'^[a-zA-Z_][a-zA-Z0-9_]*\s*(?:={1,3}|!==?)\s*!?[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?)+$', text):
        return True

    return False

tests = [
    # Should be True (Technical JS)
    "show = true;",
    "value += 1;",
    "value += 1",
    "ConfigManager[symbol] = false",
    "config[symbol] = ConfigManager[symbol]",
    "show = true",
    "show = Imported.YEP_StaticTilesOption",
    "ext = 0;",
    
    # Needs escaping/safeguarding from false positives:
    "HP = 100",
    "MP = 50",
    "Score = 0",
    "Level = 1",
    "Name = Aisha",  
    "Status = true", # (We accept sacrificing Status = true if necessary, but actually "Status = Confirmed" should translate. Status=true translates as non-dialogue tech)
    "A = B",
    "Max = 99",
    "Result = 10",
]

with open("test_res_utf8.txt", "w", encoding="utf-8") as f:
    f.write("--- REGEX FALSE POSITIVE REFINED TEST ---\n")
    for t in tests:
        match = is_js_assignment(t)
        f.write(f"{t:<40} -> {'[MATCH! (Technical)]' if match else '[No Match (Translates)]'}\n")
