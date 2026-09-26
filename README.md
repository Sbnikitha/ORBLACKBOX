<<<<<<< HEAD
# OR Sentinel

Live surgical sponge-count interlock for a circulating nurse. One station watches up to eight operating rooms. Speech tracks sponges and the WHO checklist. A camera counts the tray. Fixed rules block closing when the count is wrong. Patient details stay on the box unless a question is non-urgent, the local model is unsure, the link is up, and a second check finds nothing identifiable left.

This tree runs here on local edge models (Counter, Checklist, Critic, Scribe, TrayCount, and the cloud router). On an HP ZGX Nano, set `LLM_URL` and `VLM_URL` to ZRT and the same code talks to the 27B and vision models.

## Run

```bash
pip install -r requirements.txt
python -m unittest tests.test_sentinel -v
python -m uvicorn app.server:app --host 127.0.0.1 --port 8501
```

Open http://127.0.0.1:8501 and press **ARM 8 ROOMS**. Room 7 is the hidden tray: audio balances, the camera sees one fewer sponge, close is blocked.

## What the floor shows

| Rooms | Case | Expect |
| --- | --- | --- |
| 1, 4 | Full time-out, 10 in / 10 out | SAFE |
| 2, 5, 8 | 10 spoken in, 9 spoken out | BLOCK |
| 3, 6 | Time-out never said | CAUTION |
| 7 | Audio matches, tray is short one | BLOCK |

Chaos controls: sever the cloud, kill the camera, forge the ledger, reset the chain.

## Edge rule

Local unless all of these are true: not urgent, confidence under 0.7, cloud reachable, and the de-identified text still has no patient data. Every decision is appended to the hash chain.

## Limits

Acted speech and generated tray photos. Not a medical device. The nurse’s count stays official.

## Public data for the real fine-tune

The demo does not download these. They are the next training and pitch sources.

| Set | Use |
| --- | --- |
| FSC-147 | Extra object-counting practice in the vision fine-tune |
| MVOR, 4D-OR | Real and simulated operating-room views for the pitch |
| MM-OR | Operating-room audio and speech, the closest public match |
| Cholec80, CholecT50, EndoVis, Kvasir-Instrument | Instrument recognition later; several need a request form |
| Synthea | Fake charts for the privacy stripper |
| Freesound | Monitor beeps under the acted audio, after a license check |
