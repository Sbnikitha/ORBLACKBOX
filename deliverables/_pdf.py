"""Write deliverables/OR-Sentinel.pdf."""
import os

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(os.environ["WINDIR"], "Fonts", "segoeui.ttf")
FONTB = os.path.join(os.environ["WINDIR"], "Fonts", "segoeuib.ttf")
OUT = os.path.join(ROOT, "OR-Sentinel.pdf")
GREEN = (7, 90, 62)
INK = (20, 32, 28)
MUTED = (70, 90, 82)


class Doc(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("Segoe", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, "Synthetic demo. Not a medical device. The nurse's count stays official.", align="L")


def line(pdf, text, size=11, bold=False, color=INK, gap=5.6):
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Segoe", "B" if bold else "", size)
    pdf.set_text_color(*color)
    pdf.multi_cell(pdf.epw, gap, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def heading(pdf, text):
    pdf.ln(2)
    line(pdf, text, size=14, bold=True, color=GREEN, gap=8)


def main():
    pdf = Doc()
    pdf.set_auto_page_break(True, 16)
    pdf.set_left_margin(14)
    pdf.set_right_margin(14)
    pdf.add_font("Segoe", "", FONT)
    pdf.add_font("Segoe", "B", FONTB)
    pdf.add_page()
    pdf.set_fill_color(*GREEN)
    pdf.rect(0, 0, 210, 26, "F")
    pdf.set_xy(14, 7)
    pdf.set_font("Segoe", "B", 18)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, "OR Sentinel", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(14)
    pdf.set_font("Segoe", "", 10)
    pdf.cell(0, 6, "HP Edge AI  ·  SJSU  ·  one submission document", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(32)

    line(pdf, "Synthetic demo. Not a medical device. The circulating nurse's count stays official.")
    heading(pdf, "Links")
    line(pdf, "GitHub: https://github.com/Sbnikitha/ORBLACKBOX")
    line(pdf, "YouTube: https://youtube.com/shorts/uQKhbzTK_2s")
    line(pdf, "Video title: How OR Sentinel Stops Surgical Errors. Length 1:20. Public.")

    heading(pdf, "Checklist")
    for item in [
        "Public GitHub, with README, Dockerfile, and setup scripts.",
        "Metrics, in this document.",
        "Demo, in the YouTube video.",
        "Interactive presentation: architecture, benchmarks, and impact, in the video.",
        "Pitch: three minutes plus questions.",
        "LinkedIn post is live, with the video and the GitHub repo.",
        "SJSU Google Drive: upload this PDF.",
    ]:
        line(pdf, "-  " + item)

    heading(pdf, "Problem")
    line(pdf, "Before a surgical wound is closed, the circulating nurse reconciles sponges that went in with sponges that came out. A sponge still inside, or a tray that was misread, means close can happen too early. OR Sentinel does not replace that count. It holds the close when the spoken count and the tray disagree.")

    heading(pdf, "Solution")
    line(pdf, "One edge box watches up to eight operating rooms. Speech updates sponges added, sponges removed, and the time-out. A camera reads the tray. Fixed rules, not the model, choose SAFE, CAUTION, or BLOCK. BLOCK happens only when someone asks to close and the spoken count, the camera, or a tool still inside disagree.")

    heading(pdf, "Metrics")
    for item in [
        "Combined YOLO: 88.4% mAP50. Recall 81.7%. Precision 89.3%. mAP50-95 64.0%.",
        "CountNet: 78.1% exact, MAE 0.219.",
        "ToolNet: 56.7% mask IoU.",
        "TrayCount: 32/32 exact on the demo photos.",
        "Fusion rules: 16/16.",
        "Whisper tiny: 92.5% words. LibriSpeech-clean word error is 7.54%.",
        "Qwen3 27B: 84.8% MMLU on a public NVFP4 27B card.",
        "Qwen2.5-VL: 95.7% DocVQA for the base 7B.",
    ]:
        line(pdf, "-  " + item)

    heading(pdf, "Inference ports on 100.81.221.41")
    for item in [
        "Detector 8002. Already trained.",
        "CountNet 8003. Already trained.",
        "ToolNet 8004. Already trained.",
        "Whisper 8005. Pretrained tiny is loaded. Next set is room audio paired with transcripts.",
        "Language 8006. Live now as a rules reader for spoken lines.",
        "TrayCount 8007. Live now as counting code on the tray photo.",
        "Qwen3 27B 8000. Pulled for Counter, Checklist, Critic, and Scribe. Next set is instruction pairs.",
        "Qwen2.5-VL 8001. Fine-tune was in progress at the last check.",
    ]:
        line(pdf, "-  " + item)

    heading(pdf, "Impact")
    line(pdf, "One station, eight rooms, the chart stays on the box. The nurse still owns the count. Close waits when the tray and the spoken count do not match.")

    photo = os.path.join(ROOT, "proof-linkedin.png")
    if os.path.isfile(photo):
        heading(pdf, "LinkedIn proof")
        with Image.open(photo) as im:
            height = pdf.epw * im.height / im.width
        if pdf.get_y() + height > pdf.h - 18:
            pdf.add_page()
        y = pdf.get_y()
        pdf.image(photo, x=pdf.l_margin, y=y, w=pdf.epw)
        pdf.set_y(y + height + 4)

    pdf.output(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
