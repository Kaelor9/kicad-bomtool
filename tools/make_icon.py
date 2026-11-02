"""Draws the program icon: a chip on a green board with a check mark - 'parts checked'.
Writes bomtool/web/icon.ico (exe + window), icon.png (favicon). Run: python tools/make_icon.py"""
import os

from PIL import Image, ImageDraw

S = 1024
HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "..", "bomtool", "web")


def draw():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # board
    d.rounded_rectangle((40, 40, S - 40, S - 40), radius=190, fill=(24, 84, 56), outline=(214, 200, 150), width=26)
    # traces
    gold = (212, 169, 60)
    for y in (300, 512, 724):
        d.line((90, y, 250, y), fill=gold, width=26)
        d.ellipse((70, y - 32, 134, y + 32), fill=gold)
    # chip with pins
    cx0, cy0, cx1, cy1 = 290, 230, 740, 800
    for i in range(5):
        y = cy0 + 70 + i * 107
        d.rounded_rectangle((cx0 - 62, y - 26, cx0 + 10, y + 26), radius=8, fill=gold)
        d.rounded_rectangle((cx1 - 10, y - 26, cx1 + 62, y + 26), radius=8, fill=gold)
    d.rounded_rectangle((cx0, cy0, cx1, cy1), radius=46, fill=(28, 32, 38), outline=(70, 78, 88), width=10)
    d.ellipse((cx0 + 50, cy0 + 50, cx0 + 110, cy0 + 110), fill=(90, 98, 110))
    # check mark badge
    bx, by, r = 720, 720, 225
    d.ellipse((bx - r - 22, by - r - 22, bx + r + 22, by + r + 22), fill=(24, 84, 56))
    d.ellipse((bx - r, by - r, bx + r, by + r), fill=(64, 196, 120))
    d.line((bx - 120, by + 5, bx - 30, by + 100, bx + 125, by - 95), fill=(255, 255, 255), width=70, joint="curve")
    return img


def main():
    img = draw()
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(os.path.join(WEB, "icon.ico"), sizes=sizes)
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(WEB, "icon.png"))
    print("ok")


if __name__ == "__main__":
    main()
