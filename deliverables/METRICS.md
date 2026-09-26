# Benchmarks

| Model | Main result | Why this is the one we show |
| --- | --- | --- |
| Combined YOLO | 88.4% mAP50 | Best checkpoint, epoch 39 of 40, on 7,201 composite trays. The logged run, not a rounded slide. |
| CountNet | 78.1% exact-count accuracy | 25 of 32 held-out trays. The rule compares integers. MAE is 0.219. |
| ToolNet | 56.7% mask IoU | 89 Kvasir test frames. Enough to draw a box, not enough to decide a tool is inside. |
| Fusion rules | 16/16 | The model does not lock the room. |
| TrayCount | 32/32 exact on the demo photos | Separate from CountNet. This is the counter the evidence suite checks. |
| Whisper tiny | 92.5% words | LibriSpeech-clean word error is 7.54%. |
| Qwen3 27B | 84.8% MMLU | Public NVFP4 27B card. |
| Qwen2.5-VL | 95.7% DocVQA | Base 7B publisher score. |

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

OR Sentinel is a close interlock. A model score does not lock the room. These numbers answer two different questions: can the camera see the tray, and do the rules hold the close only when the count is actually wrong?

Source files: `runs/detect/runs/combined-new/results.csv` (40-epoch detector log), `models/report.json` (CountNet and ToolNet), `app/selftest.py` (the 16 evidence checks). Hardware for the detector run: local NVIDIA GPU, YOLOv8s, image size 640, batch 16, seed 0. CountNet and ToolNet were measured on CUDA. This is not a clinical study.

## Why these metrics

| Metric | What it measures | Why it was chosen | What it does not claim |
| --- | --- | --- | --- |
| Recall | Share of real objects the detector found | A missed sponge is the failure that matters for a retained item. A high score with poor recall would still miss cotton. | It is not a rate of retained items in a hospital. |
| Precision | Share of detector boxes that are real objects | A false sponge can hold a close the nurse already reconciled. | It is not a false-alarm rate on a live operating room. |
| mAP50 | Detection quality at IoU 0.5 | Standard “did we find the object” score. Comparable to other detectors. | A box at IoU 0.5 can still be loose. |
| mAP50-95 | Detection quality averaged from IoU 0.5 to 0.95 | This is the fitness that selected `best.pt`. Tight boxes matter when cotton, hands, and tools overlap. | It is not a count. |
| Exact count and MAE | Integer sponge count on held-out trays | The rule compares integers. Off by one is enough to BLOCK. Exact match is the product decision. MAE is how far the miss is when it is wrong. | 25/32 on generated trays is not clinical accuracy. |
| IoU | Overlap of the predicted instrument region with the label | ToolNet’s job is “where is the instrument,” not a class score. | 0.567 is a modest overlap. It is a research baseline. |
| Rule checks (16/16) | SAFE, CAUTION, and BLOCK on known cases | The close decision is a rule. A strong detector does not prove the interlock. A weak detector does not get to invent BLOCK. | The acted lines are written. They are not operating-room audio. |

BLOCK is allowed only when someone has asked to close and at least one of these is true: sponges added minus sponges removed is not zero, the camera count does not match the sponges removed, or a tool is still marked inside. A missed time-out is CAUTION. A monitor alert is CAUTION. Neither one blocks by itself. That rule is in `app/fusion.py`.

## Detector

YOLOv8s, started from `yolov8s.pt`, 40 epochs. Dataset `data/composites_real`: IGauze tray photos as the background, HOSPI instrument cutouts under the cotton. 7,201 train images, 341 valid images. Classes: gauze, red gauze, stained gauze, hand, stained hand, instrument. There is no needle class. The Real demo draws the Mayo Needle Holder from the photo label when the instrument box does not already cover it.

Ultralytics keeps `best.pt` at the epoch with the best fitness, about `0.1 * mAP50 + 0.9 * mAP50-95`. That epoch is 39.

| Epoch | Precision | Recall | mAP50 | mAP50-95 |
| --- | --- | --- | --- | --- |
| 1 | 0.659 | 0.646 | 0.672 | 0.444 |
| 39 (checkpoint used) | 0.893 | 0.817 | 0.884 | 0.640 |
| 40 (end of the run) | 0.877 | 0.824 | 0.881 | 0.640 |

Weight used at inference: `nano/weights/detector.pt`.

Recall 0.817 means roughly one in six labeled objects is still missed on the valid composites. That is why the nurse’s count stays official and the detector is not allowed to close the room by itself.

## CountNet

Small color-threshold network, 160×160, trained on trays drawn by `app/photos.py`. It did not train on IGauze. Held-out set: 32 generated trays.

- Exact count: 25/32
- Mean absolute error: 0.219

Seven trays were off. Because the error is usually a fraction of a sponge, MAE stays under one, but the interlock treats any integer disagreement as a real mismatch. The live Synthetic path uses TrayCount (`photos.count_image`) on those drawn photos. The evidence suite requires that counter to be exact on the demo set (32/32). That is a different model from CountNet. Both numbers are reported so they are not mixed up.

## ToolNet

Small convolutional mask, 128×128, threshold 0.7. Kvasir-Instrument: 501 train frames, 89 test frames.

- Mean IoU on the test frames: 0.567

The instrument is found in the right area often enough to draw a box. The overlap is not tight enough to call a tool in or out of the body. Tool-inside is a scripted state in the acted case, not this mask.

## Rules, privacy, and the evidence tab

`app/selftest.py` is what the Evidence tab runs. The suite that was green on this station is 16/16. The checks that carry the safety claim:

- Ten acted lines: added, removed, and the checklist event match.
- Matched close is SAFE.
- Spoken 10 in / 9 out blocks only once close is requested.
- Camera one short of the spoken count blocks once close is requested.
- The same camera miss before close is CAUTION, not BLOCK.
- A skipped time-out is CAUTION.
- A case past six hours adds a fatigue caution and does not block a matched count.
- Three acted cases, plain and with a hidden tray, match the expected status (6/6).
- The demo sentence loses the name, birth date, and record number.
- Urgent, confident, offline, and leftover patient data never take the cloud path.
