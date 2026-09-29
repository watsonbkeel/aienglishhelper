import json
import os
import urllib.request

API_BASE = "https://api.bkeel.com/v1"
API_KEY = os.environ["BKEEL_API_KEY"]  # export BKEEL_API_KEY=sk-...
TASK = "imgtask_992db59da6e14768bf0f02cc2e269a17"
url = API_BASE + "/async-images/" + TASK
req = urllib.request.Request(url, method="GET")
req.add_header("Authorization", "Bearer " + API_KEY)
with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.loads(resp.read().decode("utf-8"))
print(json.dumps(data, ensure_ascii=False, indent=2))
