# OR Sentinel — one submission document

HP Edge AI, SJSU Applied Data Science / HackSJSU. Synthetic demo. Not a medical device. The circulating nurse’s count stays official.

## Links

| What | Link |
| --- | --- |
| GitHub (code, README, Dockerfile, setup scripts) | https://github.com/Sbnikitha/ORBLACKBOX |
| YouTube video | https://youtube.com/shorts/uQKhbzTK_2s |

## Checklist

- [x] Public GitHub — https://github.com/Sbnikitha/ORBLACKBOX
- [x] Metrics — in this document
- [x] Demo — in the YouTube video
- [x] YouTube — https://youtube.com/shorts/uQKhbzTK_2s
- [x] Interactive presentation — architecture, benchmarks, and impact, shown in the video
- [x] Pitch notes — ready to say. Three minutes plus questions.
- [ ] SJSU Google Drive — upload `deliverables/OR-Sentinel.pdf`
- [x] Socials — LinkedIn post is live, with the video, the GitHub repo, and the required tags. Proof: `deliverables/proof-linkedin.png`

## Other deliverables

| Deliverable | Where it is |
| --- | --- |
| Repo and how to run it | https://github.com/Sbnikitha/ORBLACKBOX |
| Video, demo, and presentation | https://youtube.com/shorts/uQKhbzTK_2s — public, title “How OR Sentinel Stops Surgical Errors,” 1:20. Proof: `deliverables/proof-youtube.png` |
| Spoken pitch and Q&A | Ready with the judges. Problem, solution, architecture, benchmarks, impact. |
| LinkedIn post | Live, with the video and https://github.com/Sbnikitha/ORBLACKBOX. Proof: `deliverables/proof-linkedin.png` |

## Problem

Before a surgical wound is closed, the circulating nurse reconciles sponges that went in with sponges that came out. A sponge still inside, or a tray that was misread, means close can happen too early. One nurse may cover more than one room. OR Sentinel does not replace that count. It holds the close when the spoken count and the tray disagree.

## Solution

One edge box watches up to eight operating rooms. Speech updates sponges added, sponges removed, and the time-out. A camera reads the tray. Fixed rules, not the model, choose SAFE, CAUTION, or BLOCK. BLOCK happens only when someone asks to close and the spoken count, the camera, or a tool still inside disagree. Patient questions stay on the box unless the question is not urgent, the local model is unsure, the link is up, and a second check finds no name, birth date, age, or record number left.

## Metrics

| Model | Result |
| --- | --- |
| Combined YOLO | 88.4% mAP50 (recall 81.7%, precision 89.3%, mAP50-95 64.0%) |
| CountNet | 78.1% exact, MAE 0.219 |
| ToolNet | 56.7% mask IoU |
| TrayCount | 32/32 exact on the demo photos |
| Fusion rules | 16/16 |
| Whisper tiny | 92.5% words. LibriSpeech-clean word error is 7.54%. |
| Qwen3 27B | 84.8% MMLU on a public NVFP4 27B card. |
| Qwen2.5-VL | 95.7% DocVQA for the base 7B. |

## Inference ports

Host 100.81.221.41.

| Entry | Port | Training status |
| --- | --- | --- |
| Detector | 8002 | Already trained |
| CountNet | 8003 | Already trained |
| ToolNet | 8004 | Already trained |
| Whisper | 8005 | Pretrained tiny is loaded. Next set is room audio paired with transcripts. |
| Language | 8006 | Live now as a rules reader for spoken lines. |
| TrayCount | 8007 | Live now as counting code on the tray photo. |
| Qwen3 27B | 8000 | Pulled for Counter, Checklist, Critic, and Scribe. Next set is instruction pairs. |
| Qwen2.5-VL | 8001 | Fine-tune was in progress at the last check. |

## Impact

One station, eight rooms, the chart stays on the box. The nurse still owns the count. Close waits when the tray and the spoken count do not match.

## Proof

YouTube Studio shows the video public: “How OR Sentinel Stops Surgical Errors,” 1:20, https://youtube.com/shorts/uQKhbzTK_2s. Screenshot: `deliverables/proof-youtube.png`.

The LinkedIn post is live. It links the minute and the GitHub repo, and tags @SJSUAppliedDataScience @SJSUAIInstitute @HackSJSU @HPInc @ZbyHP @NVIDIA @Arm @Canonical @Salesforce @iTradeNetwork @EdgeAI @LocalAgentic. Screenshot: `deliverables/proof-linkedin.png`.
