import json
import os
import urllib.request

API_BASE = "https://api.bkeel.com/v1"
API_KEY = os.environ["BKEEL_API_KEY"]  # export BKEEL_API_KEY=sk-...
TASK = "imgtask_992db59da6e14768bf0f02cc2e269a17"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo-512.png")

# 1) get task status -> upstreamImageUrl
url = API_BASE + "/async-images/" + TASK
req = urllib.request.Request(url, method="GET")
req.add_header("Authorization", "Bearer " + API_KEY)
with urllib.request.urlopen(req, timeout=60) as resp:
    st = json.loads(resp.read().decode("utf-8"))

img_url = st.get("upstreamImageUrl") or st.get("data", {}).get("upstreamImageUrl")
if not img_url:
    img_url = st["data"]["rawResult"]["data"][0]["url"]
print("IMAGE URL:", img_url)

# 2) download
req2 = urllib.request.Request(img_url, method="GET")
with urllib.request.urlopen(req2, timeout=120) as r2:
    blob = r2.read()

with open(OUT, "wb") as f:
    f.write(blob)

# 3) verify PNG dimensions
with open(OUT, "rb") as f:
    head = f.read(33)
assert head[:8] == b"\x89PNG\r\n\x1a\n", "not a png"
w = int.from_bytes(head[16:20], "big")
h = int.from_bytes(head[20:24], "big")
print("SAVED:", OUT, "bytes=", len(blob), "size=", w, "x", h)
