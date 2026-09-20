"""仅生成公开、合成的视觉验收页；用 .venv-materials/bin/python 运行。"""
import sys
from PIL import Image, ImageDraw, ImageFont

image = Image.new("RGB", (1000, 1050), "white")
draw = ImageDraw.Draw(image)
font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 23)
draw.text((50, 35), "Synthetic document check - no private data", font=font, fill="black")
draw.text((50, 120), "Formula", font=font, fill="black")
draw.text((90, 205), "y =", font=font, fill="black")
draw.text((170, 173), "x", font=font, fill="black")
draw.text((190, 155), "2", font=small, fill="black")
draw.text((220, 173), "+ 3", font=font, fill="black")
draw.line((160, 213, 295, 213), fill="black", width=2)
draw.text((220, 226), "2", font=font, fill="black")
draw.text((50, 320), "Measurements", font=font, fill="black")
for y in (380, 440, 500, 560):
    draw.line((50, y, 700, y), fill="black", width=2)
for x in (50, 360, 700):
    draw.line((x, 380, x, 560), fill="black", width=2)
for y, left, right in ((390, "Sample", "Time (ms)"), (450, "A", "17"), (510, "B", "42")):
    draw.text((65, y), left, font=font, fill="black")
    draw.text((380, y), right, font=font, fill="black")
draw.text((50, 630), "Data flow", font=font, fill="black")
for x, label in ((50, "Input"), (390, "Model"), (730, "Result")):
    draw.rectangle((x, 715, x + 210, 805), outline="black", width=2)
    draw.text((x + 40, 743), label, font=font, fill="black")
for start, end in ((260, 390), (600, 730)):
    draw.line((start, 760, end, 760), fill="black", width=3)
    draw.polygon(((end, 760), (end - 15, 750), (end - 15, 770)), fill="black")
draw.text((50, 900), "Page 1. End of synthetic sample.", font=small, fill="black")
image.save(sys.argv[1], format="PNG")
