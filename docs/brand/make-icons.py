"""Cut the shield out of the generated logo and produce the app's icon set.

Run from the repository root with Pillow available:

    python docs/brand/make-icons.py

The source is an AI render on a near-white canvas with a stray sparkle artefact
in one corner, so the mark is isolated by its own colour rather than trimmed by
alpha: every row of the shield is a single contiguous span, which makes a
scanline fill an exact silhouette. The span is pulled in by two pixels so the
row of half-blended edge pixels does not survive as a pale fringe on a dark
background.

The source is stored as **lossless** WebP, not lossy and not PNG. Lossy is
unusable here for a reason specific to this script: the silhouette is found by
thresholding on `b - r > 45 and b > 110`, so a compressor that moves an edge
pixel by a few levels moves the crop with it. Lossless halves the file — 4.3 MB
to 2.1 MB, which every clone of this repository pays for — and leaves every
pixel identical, which the icons below are checked against.

The favicon is not merely unpadded, it overflows the top of its square. A
browser tab gives every icon the same square box, and the shield is a fifth
taller than it is wide, so fitting it whole leaves a tenth of the box empty down
each side and the mark reads small next to square favicons. Letting it run off
the top costs the rounded top corners — a pixel of radius at the size this is
actually seen at — and buys a tenth more of everything that matters. The point
at the bottom keeps its margin: a tip touching the edge reads as a crop, a
straight top edge does not.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "brand" / "logo-source.webp"
WEB = ROOT / "web"

INSET = 2

im = Image.open(SRC).convert("RGB")
w, h = im.size
px = im.load()

spans: dict[int, tuple[int, int]] = {}
for y in range(h):
    first = last = None
    for x in range(w):
        r, g, b = px[x, y]
        if b - r > 45 and b > 110:
            if first is None:
                first = x
            last = x
    if first is not None and last - first > 2 * INSET:
        spans[y] = (first + INSET, last - INSET)

ys = sorted(spans)
top, bottom = ys[0] + INSET, ys[-1] - INSET
left = min(s[0] for s in spans.values())
right = max(s[1] for s in spans.values())

mark = Image.new("RGBA", (w, h), (0, 0, 0, 0))
mp = mark.load()
for y in range(top, bottom + 1):
    if y not in spans:
        continue
    x0, x1 = spans[y]
    for x in range(x0, x1 + 1):
        mp[x, y] = (*px[x, y], 255)

mark = mark.crop((left, top, right + 1, bottom + 1))
print(f"mark {mark.width}x{mark.height} (aspect {mark.width / mark.height:.3f})")


def square(size: int, pad: float, background=None) -> Image.Image:
    """Centre the mark on a square canvas, `pad` of the canvas left as margin."""
    inner = int(size * (1 - 2 * pad))
    scale = inner / max(mark.size)
    fitted = mark.resize(
        (max(1, round(mark.width * scale)), max(1, round(mark.height * scale))),
        Image.LANCZOS,
    )
    canvas = Image.new("RGBA", (size, size), background or (0, 0, 0, 0))
    canvas.paste(
        fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2), fitted
    )
    return canvas


# The header mark: no canvas of its own, so layout controls its spacing.
logo = mark.resize((round(mark.width * 256 / mark.height), 256), Image.LANCZOS)
logo.save(WEB / "public" / "logo.png", optimize=True)

# The same mark beside its source, for the READMEs. Generated rather than
# copied by hand: a brand asset that drifts from the one the app ships is worse
# than no brand asset, and the README is the first thing anyone sees.
logo.save(ROOT / "docs" / "brand" / "logo.png", optimize=True)


def favicon(size: int, scale: float = 1.10, bottom: float = 0.015) -> Image.Image:
    """The mark, scaled past the canvas height and hung from the bottom edge."""
    height = round(size * scale)
    width = round(mark.width * height / mark.height)
    fitted = mark.resize((width, height), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # A negative y is what crops the top; Pillow clips the paste for us.
    canvas.paste(
        fitted, ((size - width) // 2, size - round(size * bottom) - height), fitted
    )
    return canvas


icon = favicon(256)
icon.save(WEB / "app" / "icon.png", optimize=True)
icon.save(WEB / "app" / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

# Apple crops its own rounded rectangle out of this and does not respect
# transparency, so it gets the paper colour behind it and enough margin that the
# corner mask cannot bite into the shield.
square(180, 0.07, background=(247, 249, 253, 255)).convert("RGB").save(
    WEB / "app" / "apple-icon.png", optimize=True
)

for path in (
    WEB / "public/logo.png",
    WEB / "app/icon.png",
    WEB / "app/favicon.ico",
    WEB / "app/apple-icon.png",
    ROOT / "docs/brand/logo.png",
):
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")
