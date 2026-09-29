import json
import os
import sys
import time
import urllib.request
import urllib.error
import base64

API_BASE = "https://api.bkeel.com/v1"
API_KEY = os.environ["BKEEL_API_KEY"]  # export BKEEL_API_KEY=sk-...
MODEL = "og-image2-low"

PROMPT = (
    "App logo icon for an English learning mini-program featuring a conversational AI chatbot robot. "
    "Design: a cute, friendly round robot head with a small antenna, large expressive eyes, and a small "
    "speech bubble displaying the word 'Hi' to represent spoken English conversation practice. "
    "Soft gradient background in calming blue and mint green. Flat modern vector style, clean geometric "
    "shapes, centered composition, transparent background, suitable as a mobile app icon, sharp and crisp, "
    "512x512 dimensions, no extra text, minimalist brand mascot."
)

SIZE = "512x512"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo-512.png")


def post_json(url, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + API_KEY)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url):
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", "Bearer " + API_KEY)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download(url):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


# 1) submit
submit = post_json(API_BASE + "/images/generations", {
    "model": MODEL,
    "prompt": PROMPT,
    "size": SIZE,
    "n": 1,
})
print("SUBMIT:", json.dumps(submit, ensure_ascii=False)[:500])

poll_url = submit.get("poll_url") or submit.get("status_url")
if poll_url and not poll_url.startswith("http"):
    poll_url = API_BASE.split("/v1")[0] + poll_url
print("POLL URL:", poll_url)

# 2) poll
done = False
result = None
for i in range(60):
    time.sleep(3)
    try:
        st = get_json(poll_url)
    except urllib.error.HTTPError as e:
        print("poll http err", e.code)
        continue
    status = st.get("status")
    print("poll %d -> status=%s" % (i, status))
    if status in ("succeeded", "completed", "done", "success"):
        done = True
        result = st
        break
    if status in ("failed", "error"):
        print("FAILED:", json.dumps(st, ensure_ascii=False)[:1000])
        sys.exit(1)

if not done:
    print("TIMEOUT waiting for image")
    sys.exit(1)

# 3) extract image
img_url = result.get("image_url") or result.get("download_url")
b64 = result.get("b64_json") or (result.get("data", [{}])[0].get("b64_json") if result.get("data") else None)
if b64:
    with open(OUT, "wb") as f:
        f.write(base64.b64decode(b64))
    print("SAVED b64 ->", OUT)
elif img_url:
    if not img_url.startswith("http"):
        img_url = API_BASE.split("/v1")[0] + img_url
    blob = download(img_url)
    with open(OUT, "wb") as f:
        f.write(blob)
    print("SAVED url ->", OUT, "bytes=", len(blob))
else:
    print("NO IMAGE in result:", json.dumps(result, ensure_ascii=False)[:2000])
    sys.exit(1)
