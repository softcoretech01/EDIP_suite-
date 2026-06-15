import json

with open("C:\\Users\\kabil\\.gemini\\antigravity-ide\\brain\\78f099b7-bdae-4fd5-afcf-2cc2b808a10f\\.system_generated\\logs\\transcript.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        data = json.loads(line)
        if "replace_file_content" in line and "chat.py" in line:
            print("FOUND A REPLACE_FILE_CONTENT for chat.py")
            if "max_retries" in line or "attempt" in line:
                print("THIS ONE HAS RETRIES!")
                print(line[:500])
