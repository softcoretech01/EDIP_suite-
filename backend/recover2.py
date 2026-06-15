import json

with open("C:\\Users\\kabil\\.gemini\\antigravity-ide\\brain\\78f099b7-bdae-4fd5-afcf-2cc2b808a10f\\.system_generated\\logs\\transcript.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        if "max_retries" in line and "replace_file_content" in line and '"status":"DONE"' in line:
            data = json.loads(line)
            if data["type"] == "CODE_ACTION":
                print(data["content"])
