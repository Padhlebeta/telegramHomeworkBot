import json

with open("service.json", "r", encoding="utf-8") as f:
    data = json.load(f)
    print(json.dumps(data))  # outputs single-line escaped JSON
