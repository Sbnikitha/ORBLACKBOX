"""Patient charts from the Synthea sample the privacy demo names.

Source: synthetichealth/synthea-sample-data, synthea_sample_data_csv_apr2020.
Each case takes the next living chart. The same name is not reused until the table wraps.
"""
import csv
import threading
from datetime import date
from pathlib import Path

import config


_LOCK = threading.Lock()
_ROWS = None
_ALLERGIES = None
_CURSOR = 0


def _load():
    global _ROWS, _ALLERGIES
    if _ROWS is not None:
        return _ROWS
    root = Path(config.DATA_DIR) / "synthea"
    allergies = {}
    allergy_path = root / "allergies.csv"
    if allergy_path.is_file():
        with allergy_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("STOP"):
                    continue
                allergies.setdefault(row["PATIENT"], [])
                text = (row.get("DESCRIPTION") or "").strip()
                if text and text not in allergies[row["PATIENT"]]:
                    allergies[row["PATIENT"]].append(text)
    rows = []
    with (root / "patients.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("DEATHDATE"):
                continue
            if not row.get("FIRST") or not row.get("LAST"):
                continue
            rows.append(row)
    _ALLERGIES = allergies
    _ROWS = rows
    return rows


def _age(birth):
    year, month, day = (int(part) for part in birth.split("-"))
    today = date.today()
    return today.year - year - ((today.month, today.day) < (month, day))


def chart_from(row):
    birth = row["BIRTHDATE"]
    return {
        "id": row["Id"],
        "name": f"{row['FIRST']} {row['LAST']}".strip(),
        "birthdate": birth,
        "age": _age(birth),
        "gender": row.get("GENDER") or "",
        "city": row.get("CITY") or "",
        "state": row.get("STATE") or "",
        "allergies": (_ALLERGIES or {}).get(row["Id"], [])[:3],
    }


def take(count=1):
    """Next unused living charts. Wraps only after every row has been used."""
    global _CURSOR
    rows = _load()
    if not rows:
        raise RuntimeError("No living Synthea charts in data/synthea/patients.csv")
    picked = []
    with _LOCK:
        for _ in range(count):
            if _CURSOR >= len(rows):
                _CURSOR = 0
            picked.append(chart_from(rows[_CURSOR]))
            _CURSOR += 1
    return picked


def confirm_line(chart):
    return f"Patient is {chart['name']}, birth date {chart['birthdate']} confirmed."


def allergy_line(chart):
    names = chart.get("allergies") or []
    if names:
        return "Allergies: " + ", ".join(names) + "."
    return "No known allergies."


def bind(lines, chart):
    """Put this chart on the time-out lines. Counts and close lines stay as written."""
    if not chart:
        return lines
    bound = []
    for line in lines:
        text = line["text"]
        low = text.lower()
        if "date of birth" in low or "birth date" in low:
            text = confirm_line(chart)
        elif "allerg" in low:
            text = allergy_line(chart)
        bound.append(dict(line, text=text))
    return bound


def question(chart, procedure="laparoscopic appendectomy"):
    allergy = ", ".join(chart.get("allergies") or []) or "none listed"
    return (
        f"Synthea patient {chart['name']}, birthDate {chart['birthdate']}, "
        f"MRN {chart['id']}, age {chart['age']}, allergies {allergy}. "
        f"{procedure}. Which counts are required before closing?"
    )
