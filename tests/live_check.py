"""Hit the running command center and assert the demo floor."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8501"


def call(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode())


def main():
    html = urllib.request.urlopen(BASE + "/", timeout=10).read().decode()
    assert "OR Sentinel" in html and "ARM" in html
    css = urllib.request.urlopen(BASE + "/static/styles.css", timeout=10).read()
    js = urllib.request.urlopen(BASE + "/static/app.js", timeout=10).read()
    assert b".bay" in css and b"ARM" in js
    print("page", len(html), "css", len(css), "js", len(js))

    report = call("/api/selftest")
    print("selftest", report["passed"], "/", report["total"], "ok", report["ok"])
    assert report["ok"]

    probe = call("/api/probe", {"text": "Adding five sponges."})
    print("probe", probe["counter"], probe["checklist"]["event"])
    assert probe["counter"] == {"added": 5, "removed": 0}

    photos = call("/api/photos")
    shot = call("/api/vision/count", {"name": photos["photos"][7]["name"]})
    print("vision", shot)
    assert shot["match"]

    print("sim", call("/api/simulate", {"ors": 8, "speed": 30, "problem": 7}))
    final = None
    deadline = time.time() + 25
    while time.time() < deadline:
        rooms = call("/api/state")["rooms"]
        if len(rooms) == 8 and all(room.get("done") for room in rooms):
            final = rooms
            break
        time.sleep(0.3)
    assert final, "rooms did not finish"
    for room in final:
        flag = "PASS" if room["status"] == room["expected"] else "MISS"
        print(
            f"OR{room['or']} {room['status']} expect {room['expected']} {flag} "
            f"in {room['added']} out {room['removed']} cam {room['vision_count']}"
        )
    assert all(room["status"] == room["expected"] for room in final)

    question = (
        "Patient Maria Lopez, DOB 03/14/1971, MRN 4471923, left laparoscopic "
        "appendectomy. Which counts are required before closing?"
    )
    ask = call("/api/ask", {"question": question, "urgent": False})
    print("route", ask["route"], "sent", ask["sent"][:90])
    assert ask["reason"] == "cloud"
    assert "Maria" not in ask["sent"] and "4471923" not in ask["sent"]
    assert "<PERSON>" in ask["sent"]

    urgent = call("/api/ask", {"question": question, "urgent": True})
    print("urgent", urgent["route"])
    assert urgent["sent"] == "" and "urgent" in urgent["reason"]

    call("/api/cloud", {"cut": True})
    offline = call("/api/ask", {
        "question": "Which surgical specialties most often skip instrument counts?",
        "urgent": False,
    })
    print("offline", offline["route"])
    assert "offline" in offline["reason"] and offline["sent"] == ""
    call("/api/cloud", {"cut": False})

    log = call("/api/scribe", {"room": 7})
    print("scribe starts", log["log"].splitlines()[0])
    assert "BLOCK" in log["log"]

    forged = call("/api/tamper", {})
    print("tamper", forged)
    ledger = call("/api/state")["ledger"]
    assert ledger["ok"] is False and ledger["broken_at"] == 3
    call("/api/ledger/reset", {})
    assert call("/api/state")["ledger"]["ok"] is True
    print("ALL LIVE CHECKS PASSED")


if __name__ == "__main__":
    main()
