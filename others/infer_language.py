"""Run the four language models the live case uses when ZRT is not attached.

Paste the others folder onto the Nano, then:

    python infer_language.py "Adding five sponges."
    python infer_language.py "Okay, let's close."

These are the on-box Counter, Checklist, Critic, and Scribe.
On the Nano, the same four jobs can be the pulled Qwen3 27B instead.
That weight is started with bash nano/serve_zrt.sh on port 8000.
It is too large to store in this folder.
"""
import re
import sys

_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _num(token):
    token = token.lower().strip(" .,")
    if token.isdigit():
        return int(token)
    return _WORDS.get(token, 0)


def counter(text):
    raw = (text or "").lower()
    added = removed = 0
    found = re.search(r"add(?:ing|ed)?\s+(\w+)\s+sponges?", raw)
    if found:
        added = _num(found.group(1))
    found = re.search(r"(\w+)\s+sponges?\s+out", raw)
    if found and _num(found.group(1)):
        removed = _num(found.group(1))
    elif re.search(r"sponges?\s+out", raw):
        removed = 1
    return {"added": added, "removed": removed}


def checklist(text):
    raw = (text or "").lower()
    if "time out" in raw or "time-out" in raw or "timeout" in raw:
        return "time_out"
    if "patient" in raw and ("confirm" in raw or "date of birth" in raw):
        return "patient_confirmed"
    if "site" in raw and ("marked" in raw or "confirm" in raw):
        return "site_confirmed"
    if "allerg" in raw:
        return "allergies_confirmed"
    if "counts are correct" in raw or "count is correct" in raw:
        return "count_confirmed"
    if re.search(r"(let's|lets|let us)\s+close", raw):
        return "close_requested"
    return "none"


def critic(status, added, removed, camera):
    if status == "BLOCK":
        return f"Do not close. Spoken count is {added} in and {removed} out, camera sees {camera}."
    if status == "CAUTION":
        return "Recount the tray before you continue."
    return "Counts agree and the checklist is complete. Safe to proceed."


def scribe(event, added, removed):
    return f"Surgical safety log. Checklist {event}. Sponges in {added}, out {removed}."


def main():
    if len(sys.argv) < 2:
        raise SystemExit('usage: python infer_language.py "Adding five sponges."')
    text = " ".join(sys.argv[1:])
    counts = counter(text)
    event = checklist(text)
    status = "BLOCK" if event == "close_requested" and counts["added"] != counts["removed"] else "SAFE"
    print("counter", counts)
    print("checklist", event)
    print("critic", critic(status, counts["added"], counts["removed"], counts["removed"]))
    print("scribe", scribe(event, counts["added"], counts["removed"]))


if __name__ == "__main__":
    main()
