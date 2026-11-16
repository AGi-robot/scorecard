#!/usr/bin/env python3
"""Build side-by-side contact sheets from the canvas eval renders.

One PNG per task: every run's render for that task in a row, labelled with
the model and arm, so the differences are readable at a glance.

Usage:
    python contact_sheet.py [--renders renders] [--out renders/sheets]
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Display order: think-off arms first, then the think-on / forced arms.
DEFAULT_ORDER = [
    "swift", "ministral3-14b", "neohorse-1-4b", "agents-a1-4b", "minicpm5-2b",
    "swift-force", "swift-thinkon", "neohorse-1-4b-thinkon",
    "agents-a1-4b-thinkon", "minicpm5-2b-thinkon",
]

CELL_W = 380
LABEL_H = 26


def font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--renders", default="renders")
    ap.add_argument("--out", default="renders/sheets")
    args = ap.parse_args()

    renders = Path(args.renders)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    labels = [d.name for d in sorted(renders.iterdir())
              if d.is_dir() and (d / "T1-apple.png").is_file()]
    labels.sort(key=lambda n: (DEFAULT_ORDER.index(n)
                                if n in DEFAULT_ORDER else 99, n))

    tasks = []
    for label in labels:
        for png in sorted((renders / label).glob("T*.png")):
            if ".pass2." in png.name:
                continue
            task = png.stem
            if task not in tasks:
                tasks.append(task)
    tasks.sort()

    f = font(15)
    total_w = CELL_W * len(labels)
    for task in tasks:
        cells = []
        for label in labels:
            p = renders / label / f"{task}.png"
            if not p.is_file():
                continue
            img = Image.open(p).convert("RGB")
            h = int(img.height * CELL_W / img.width)
            cells.append((label, img.resize((CELL_W, h))))
        if not cells:
            continue
        row_h = max(c[1].height for c in cells)
        sheet = Image.new("RGB", (total_w, row_h + LABEL_H), "white")
        draw = ImageDraw.Draw(sheet)
        x = 0
        for label, img in cells:
            sheet.paste(img, (x, LABEL_H))
            draw.rectangle([x, 0, x + CELL_W - 1, LABEL_H - 1], fill="#111111")
            draw.text((x + 8, 5), label, fill="white", font=f)
            draw.rectangle([x, 0, x + CELL_W - 1, row_h + LABEL_H - 1],
                           outline="#cccccc")
            x += CELL_W
        path = out / f"{task}.png"
        sheet.save(path)
        print(f"{path}  ({len(cells)} runs)")


if __name__ == "__main__":
    main()
