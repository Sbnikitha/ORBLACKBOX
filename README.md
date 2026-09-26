# OR Sentinel

One edge station watches up to eight operating rooms. It listens to the sponge count, looks at the tray, and holds the close when those two disagree. The circulating nurse’s count stays the official record. Fixed rules choose SAFE, CAUTION, or BLOCK. The models only read, count, and explain.

Synthetic acted cases and generated trays. Not a medical device. Not for clinical use.

Public repo: https://github.com/Sbnikitha/ORBLACKBOX

## Run

Python 3.11. No GPU is required for the command center.

Windows:

```powershell
.\setup.ps1
```

Linux or the HP ZGX Nano:

```sh
sh setup.sh
```

Or directly:

```bash
pip install -r requirements.txt
python -m unittest tests.test_sentinel -v
python -m uvicorn app.server:app --host 0.0.0.0 --port 8501
```

Docker:

```bash
docker build -t or-sentinel .
docker run --rm -p 8501:8501 or-sentinel
```

Open http://127.0.0.1:8501 for the demo. Open http://127.0.0.1:8501/pitch for the interactive presentation (problem, architecture, benchmarks, impact).

On the Nano, SSH in and either run the server on `0.0.0.0:8501` or tunnel it:

```bash
ssh -L 8501:127.0.0.1:8501 <nano-user>@<nano-host>
```

## What to click

| Tab | What it shows |
| --- | --- |
| Synthetic Live | A full acted procedure. Tray photos are drawn in `data/photos`. Speech, counts, rules, and the black box all run. |
| Synthetic demo | The same procedure. Only the picture changes, to a frame from `data/composites/train`. |
| Real demo | No procedure. Object detection on a real composite tray. The detector address is `100.81.221.41:8002`. If that port is down, this machine runs `nano/weights/detector.pt` and still draws the boxes. |
| Privacy | Next living Synthea chart. Name, birth date, age, and record number are stripped before a question can leave the box. |
| Evidence | The 16 certified checks, including the fusion rules. |
| Architecture | Each model’s input and output, animated. |

The eight-room floor is `POST /api/simulate` with `{"ors": 8, "speed": 1, "problem": 7}`. Rooms 1 and 4 expect SAFE. Rooms 2, 5, and 8 expect BLOCK (10 spoken in, 9 spoken out). Rooms 3 and 6 expect CAUTION (no time-out). Room 7 expects BLOCK (audio matches, the camera is short one sponge).

## Inference ports

Hardcoded host `100.81.221.41` in `app/config.py`. Override the language and vision URLs with `LLM_URL` and `VLM_URL` if you serve them somewhere else. Set `LLM_URL=local` to force the on-box stand-in.

| Model | Port | Role |
| --- | --- | --- |
| Qwen3 27B (`Inferact/Qwen3.8-27B-NVFP4`) | 8000 | Counter, Checklist, Critic, Scribe. Pulled, not fine-tuned. |
| Qwen2.5-VL-7B | 8001 | Tray question. Pulled. Fine-tune script is `nano/train_on_nano.sh`. |
| Detector (YOLOv8s) | 8002 | Cotton, hands, instruments. |
| CountNet | 8003 | Sponge count. |
| ToolNet | 8004 | Instrument region. |
| Whisper tiny | 8005 | Wav to text. Weight is in the repo. The live tab speaks written lines in the browser. |
| Language stand-in | 8006 | Same jobs as the 27B when port 8000 is down (`app/local_model.py`). |
| TrayCount | 8007 | Sponge count from a drawn photo when the vision model is down (`app/photos.py`). |

`GET /api/models/live` is green only when that port accepts a connection.

## Benchmarks

How the numbers were chosen, and the values, are in [deliverables/METRICS.md](deliverables/METRICS.md).

| Check | Result | Why this number |
| --- | --- | --- |
| Detector, epoch 39 of 40, best checkpoint | Precision 0.893, recall 0.817, mAP50 0.884, mAP50-95 0.640 | Recall is a missed sponge. mAP50-95 is what selected the checkpoint. |
| CountNet, 32 held-out generated trays | 25 exact, MAE 0.219 | The rule compares integer counts. One sponge off is a block. |
| ToolNet, Kvasir-Instrument | IoU 0.567 on 89 test frames (501 train) | The question is whether the instrument region is in the right place. |
| Fusion rules | 16/16 evidence checks | The model does not decide BLOCK. |

## Data the demo actually uses

| Data | Where | Used for |
| --- | --- | --- |
| Synthea April 2020 sample | `data/synthea/patients.csv`, `allergies.csv` | One living chart per room and per Privacy button. 1,171 charts, deceased rows skipped. |
| Drawn trays | `data/photos`, created on startup | Synthetic Live pictures and TrayCount. |
| Composite trays | `data/composites/train` | Synthetic demo pictures. Not in git. |
| IGauze backgrounds + HOSPI cutouts | `data/composites_real`, 7,201 train / 341 valid | Detector training and the Real demo. Not in git. |
| Kvasir-Instrument | `data/external/kvasir-instrument` | ToolNet. Not in git. |

Weights that are trained and checked in: `nano/weights/detector.pt`, `models/count.pt`, `models/tool.pt`, `nano/weights/whisper/tiny.pt`. Paths and train commands are in `MODELS.txt`.

## Edge rule

A question stays on the box unless every one of these is true: it is not urgent, local confidence is under 0.7, the cloud link is up, and a second pass finds no name, birth date, age, or record number left. Every status is appended to a hash chain in `state/ledger.jsonl`.

## Pitch materials

| File | What it is |
| --- | --- |
| [deliverables/BRIEF.md](deliverables/BRIEF.md) | One-page project brief for Drive. |
| [deliverables/METRICS.md](deliverables/METRICS.md) | Benchmarks and why each metric was chosen. |
| [deliverables/PITCH.md](deliverables/PITCH.md) | Three-minute spoken pitch and likely questions. |
| [deliverables/VIDEO.md](deliverables/VIDEO.md) | Two-minute YouTube script. |
| [deliverables/SOCIALS.md](deliverables/SOCIALS.md) | Posts with the required tags. |
| http://127.0.0.1:8501/pitch | Interactive presentation. Also `web/pitch.html`. |
