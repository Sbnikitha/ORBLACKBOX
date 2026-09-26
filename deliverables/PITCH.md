# Three-minute pitch

Speak this. The slides are the live page at `/pitch`, not a deck. Have three visuals up: architecture, benchmarks, impact. Leave the rule panel ready for questions.

## 0:00 Problem

Closing a surgical wound depends on a sponge count a circulating nurse says out loud. Sponges in, sponges out, and a tray someone has to look at. One missed sponge is a retained item. One nurse may be covering more than one room. We do not replace that nurse. We give the count a second pair of eyes that cannot wave the close through.

## 0:35 Solution

OR Sentinel is one edge box for eight operating rooms. It listens to the count and looks at the tray. Speech updates how many sponges went in and came out, and whether the time-out was said. The camera counts what is actually on the tray. A fixed rule, not the model, chooses SAFE, CAUTION, or BLOCK. The room blocks only when someone asks to close and the numbers disagree. If the model misreads a line, it still cannot block on its own.

## 1:15 Architecture (visual 1)

Show the architecture panel. Audio goes to Whisper, then to Counter and Checklist. The photo goes to the detector, CountNet, and ToolNet. Those outputs are numbers and events. The rules engine is the only step that can say BLOCK. The critic writes one sentence for the nurse. Names and record numbers stay on the box. The 27B and the vision model sit on the Nano at `100.81.221.41`, each on its own port. If a port is down, a small local stand-in keeps the demo honest instead of pretending the big model answered.

## 1:50 Evidence (visual 2)

Show the benchmark bars. The detector, a YOLOv8s trained for 40 epochs on 7,201 composite trays, lands at recall 0.817 and mAP50 0.884. We publish recall because a missed sponge is the failure that matters. CountNet is exact on 25 of 32 held-out trays, MAE 0.219. ToolNet’s instrument overlap is 0.567 on 89 Kvasir frames. Then the number that actually locks the room: the fusion checks are 16 for 16. A short tray before close is a caution. The same short tray at close is a block.

## 2:30 Impact (visual 3)

One station, eight rooms, chart stays local. The nurse’s count remains the record. What changes is the close: it waits when the spoken count and the camera do not match. Say the limit in the same breath. These are acted cases and composite trays. This is not a medical device.

## 3:00 Stop talking

Hand the laptop over. The rule panel is the prop for questions.

## Questions to expect

**Is this FDA cleared?**  
No. Synthetic cases, generated and composite trays. The nurse’s count stays official. We would need a clinical protocol, real operating-room data, and a quality system before anyone called it a device.

**Why not let the 27B decide the close?**  
A language model can explain a mismatch. It should not be the lock. `app/fusion.py` blocks only for a requested close plus a count mismatch, a camera mismatch, or a tool still inside. We can show that on the pitch page by moving the counts.

**What if the detector is wrong?**  
It will be wrong some of the time. Recall is 0.817 on our valid composites, so about one in six labeled objects is missed. That is why BLOCK also requires the spoken count, and why we do not block on a camera miss before anyone asks to close.

**Where is the patient data?**  
Synthea charts, fake records. The privacy tab takes the next living chart and strips name, birth date, age, and record number. Urgent questions, confident answers, a down link, and any leftover identifier stay on the box.

**What runs on the Nano versus this laptop?**  
The laptop is the command center. The Nano is the inference host: Qwen3 27B on 8000, Qwen2.5-VL on 8001, detector on 8002, then CountNet, ToolNet, Whisper, the language stand-in, and TrayCount. Lamps in the header are green only when the port is open. The 27B is pulled, not fine-tuned. The vision fine-tune script is in the repo and has not been run as the live model.

**Why these metrics?**  
Recall for missed sponges. Precision so a false sponge does not cry wolf. mAP50-95 because that selected the checkpoint. Exact count and MAE because the rule compares integers. IoU because a tool is a region. The 16 rule checks because the product decision is not a model score.
