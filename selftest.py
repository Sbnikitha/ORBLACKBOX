"""Certified checks the Evidence tab runs. Isolated from the live floor."""
import os
import tempfile
import time

import cases
import fusion
import ledger
import local_model
import phi
import photos
import cloud_router
import simulate

DEMO = (
    "Patient Maria Lopez, DOB 03/14/1971, MRN 4471923, left laparoscopic "
    "appendectomy. Which counts are required before closing?"
)


def _check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def run():
    tests = []
    photos.ensure()
    cases.install()

    samples = [
        ("Adding five sponges.", 5, 0, "none"),
        ("Sponge out.", 0, 1, "none"),
        ("Two sponges out.", 0, 2, "none"),
        ("Let's do a time out.", 0, 0, "time_out"),
        ("Patient is John Doe, date of birth confirmed.", 0, 0, "patient_confirmed"),
        ("Laparoscopic appendectomy. Right side, site marked and confirmed.", 0, 0, "site_confirmed"),
        ("No known allergies.", 0, 0, "allergies_confirmed"),
        ("Counts are correct.", 0, 0, "count_confirmed"),
        ("Okay, let's close.", 0, 0, "close_requested"),
        ("Scalpel please.", 0, 0, "none"),
    ]
    bad = []
    for text, added, removed, event in samples:
        counts = local_model.counter(text)
        check = local_model.checklist(text)
        if counts != {"added": added, "removed": removed} or check["event"] != event:
            bad.append(text)
    tests.append(_check("Counter and Checklist on the acted lines", not bad, "missed: " + ", ".join(bad) if bad else "10 lines"))

    now = time.time()
    base = {
        "added": 10, "removed": 10, "vision_count": 10, "checklist": ["time_out"],
        "close_requested": True, "started": now, "speed": 1,
    }
    status, _, _ = fusion.evaluate(dict(base))
    tests.append(_check("Matched close is SAFE", status == "SAFE", status))

    spoken = dict(base, removed=9, vision_count=9)
    status, _, _ = fusion.evaluate(spoken)
    tests.append(_check("Spoken mismatch blocks close", status == "BLOCK", status))

    hidden = dict(base, vision_count=9)
    status, _, _ = fusion.evaluate(hidden)
    tests.append(_check("Camera mismatch blocks close", status == "BLOCK", status))

    early = dict(base, close_requested=False, vision_count=9)
    status, _, _ = fusion.evaluate(early)
    tests.append(_check("Camera mismatch before close is CAUTION", status == "CAUTION", status))

    skipped = dict(base, checklist=[])
    status, _, _ = fusion.evaluate(skipped)
    tests.append(_check("Skipped time-out stays CAUTION", status == "CAUTION", status))

    long_case = dict(base, started=now - 400 * 60)
    status, alerts, _ = fusion.evaluate(long_case)
    tests.append(_check(
        "Six-hour case adds fatigue caution",
        status == "CAUTION" and any("6 hours" in a for a in alerts),
        status,
    ))

    vision_bad = []
    for row in photos.list_photos():
        guess = photos.count_image(os.path.join(photos.config.PHOTO_DIR, row["name"]))
        if guess != row["truth"]:
            vision_bad.append(f"{row['name']} truth {row['truth']} saw {guess}")
    total = len(photos.list_photos())
    exact = total - len(vision_bad)
    tests.append(_check(
        "TrayCount exact on synthetic trays",
        not vision_bad and total >= 32,
        f"{exact}/{total} exact" + ("" if not vision_bad else "; " + "; ".join(vision_bad[:4])),
    ))

    scenario_bad = []
    for case in cases.CATALOG:
        normal = simulate.replay(case["lines"], hidden=False, script_name=case["file"])
        hidden_run = simulate.replay(case["lines"], hidden=True, script_name=case["file"])
        if normal["status"] != case["expect"]:
            scenario_bad.append(f"{case['file']} got {normal['status']} wanted {case['expect']}")
        if hidden_run["status"] != case["hidden_expect"]:
            scenario_bad.append(f"{case['file']} hidden got {hidden_run['status']} wanted {case['hidden_expect']}")
    tests.append(_check("Three acted cases, with and without a hidden tray", not scenario_bad, "; ".join(scenario_bad) or "6/6"))

    cleaned = phi.strip(DEMO)
    tests.append(_check(
        "Demo sentence is de-identified",
        "Maria" not in cleaned and "Lopez" not in cleaned and "4471923" not in cleaned and "03/14/1971" not in cleaned and "<PERSON>" in cleaned,
        cleaned,
    ))

    cloud = cloud_router.reason_for(False, 0.55, False, False)
    urgent = cloud_router.reason_for(True, 0.2, False, False)
    confident = cloud_router.reason_for(False, 0.91, False, False)
    offline = cloud_router.reason_for(False, 0.2, True, False)
    held = cloud_router.reason_for(False, 0.2, False, True)
    tests.append(_check(
        "Router gates: cloud, urgent, confident, offline, PHI hold",
        [cloud, urgent, confident, offline, held] == ["cloud", "urgent", "confident", "cloud offline", "patient data remained"],
        f"{cloud}, {urgent}, {confident}, {offline}, {held}",
    ))

    local_q = cloud_router.reason_for(False, local_model.protocol("What is a retained surgical item?")["confidence"], False, phi.has(phi.strip("What is a retained surgical item?")))
    phi_q = local_model.protocol(DEMO)
    tests.append(_check(
        "Known protocol stays confident; PHI question drops under 0.7",
        local_q == "confident" and phi_q["confidence"] < 0.7 and not phi.has(phi.strip(DEMO)),
        f"local gate {local_q}, phi confidence {phi_q['confidence']:.2f}",
    ))

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "ledger.jsonl")
        ledger.record({"type": "status", "or": 1, "status": "SAFE", "alerts": []}, path)
        ledger.record({"type": "status", "or": 2, "status": "BLOCK", "alerts": ["mismatch"]}, path)
        intact = ledger.verify(path) is None
        broken = ledger.tamper(path)
        tests.append(_check("Hash chain detects a forged entry", intact and broken == 3, f"broke at {broken}"))

    message = local_model.critic({"added": 10, "removed": 10, "vision_count": 9}, "BLOCK", ["Nurse counted 10 out, camera sees 9 on the tray"])
    tests.append(_check("Critic tells the nurse not to close", message.lower().startswith("do not close"), message))

    log = local_model.scribe([{"t": 1, "event": "time_out", "detail": ""}], {"status": "SAFE", "added": 10, "removed": 10, "vision_count": 10, "alerts": []})
    tests.append(_check("Scribe writes a safety log", "time out" in log.lower() and "SAFE" in log, "ok"))

    questions = _questions()
    cloud_n = local_n = leaked = 0
    for question in questions:
        result = local_model.protocol(question)
        why = cloud_router.reason_for(False, result["confidence"], False, phi.has(phi.strip(question)))
        if why == "cloud":
            cloud_n += 1
            if phi.has(phi.strip(question)):
                leaked += 1
        else:
            local_n += 1
    tests.append(_check(
        "20 protocol questions: some escalate, zero PHI in the payload",
        cloud_n > 0 and local_n > 0 and leaked == 0 and len(questions) == 20,
        f"{local_n} local, {cloud_n} cloud, leaked {leaked}",
    ))

    passed = sum(1 for item in tests if item["ok"])
    return {
        "ok": passed == len(tests),
        "passed": passed,
        "failed": len(tests) - passed,
        "total": len(tests),
        "tests": tests,
        "router": {"local": local_n, "cloud": cloud_n, "questions": len(questions)},
        "vision": {"exact": exact, "n": total},
    }


def _questions():
    path = os.path.join(config_root_bench(), "questions.txt")
    with open(path, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


def config_root_bench():
    import config
    return config.BENCH_DIR
