"""Бот расписания: листы PDF последнего дня -> OCR -> расписание класса -> Telegram."""
import os, re, io, csv, subprocess, tempfile
import numpy as np
import requests
import pymupdf
from PIL import Image

TOKEN = os.environ["BOT_TOKEN"]
CHAT = int(os.environ["CHAT_ID"])
CLASS = (os.environ.get("MY_CLASS") or "11а").strip()
PDF_URL = os.environ.get("PDF_URL") or (
    "https://kirovskschool5.gosuslugi.ru/netcat_files/userfiles/raspisanie2026.pdf")
DPI = 300
TMP = tempfile.mkdtemp()


def log(*a):
    print(*a, flush=True)


def fetch_pdf():
    last = None
    for _ in range(3):
        try:
            r = requests.get(PDF_URL, timeout=60,
                             headers={"User-Agent": "Mozilla/5.0 schedule-bot"})
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                raise ValueError("по ссылке не PDF")
            return r.content
        except Exception as e:
            last = e
    raise last


def tg(method, data, files=None):
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}",
                      data=data, files=files, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Telegram {method}: {r.status_code} {r.text[:200]}")
    return r.json()


# ---------- OCR ----------
def ocr(arr, psm="6", whitelist=None, scale=2):
    im = Image.fromarray(arr)
    if scale != 1:
        im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
    pad = Image.new("L", (im.width + 40, im.height + 40), 255)
    pad.paste(im, (20, 20))
    p = os.path.join(TMP, "cell.png")
    pad.save(p)
    cmd = ["tesseract", p, "stdout", "-l", "rus", "--psm", psm]
    if whitelist:
        cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def to_gray(pix):
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    return np.array(Image.fromarray(a).convert("L"))


def ocr_words(arr):
    p = os.path.join(TMP, "page.png")
    Image.fromarray(arr).save(p)
    out = os.path.join(TMP, "page")
    subprocess.run(["tesseract", p, out, "-l", "rus", "--psm", "6", "tsv"],
                   capture_output=True)
    words = []
    with open(out + ".tsv", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            t = (r.get("text") or "").strip()
            if t and r.get("conf", "-1") != "-1" and int(r["top"]) > 0:
                x, y = int(r["left"]), int(r["top"])
                w, h = int(r["width"]), int(r["height"])
                words.append((x, y, x + w, y + h, t))
    return words


# ---------- геометрия ----------
def groups(idx, tol=3):
    g = []
    for i in idx:
        if g and i - g[-1][-1] <= tol:
            g[-1].append(int(i))
        else:
            g.append([int(i)])
    return [(x[0], x[-1]) for x in g]


def bbox(ink):
    rr = np.where(ink.mean(axis=1) > 0.004)[0]
    cc = np.where(ink.mean(axis=0) > 0.004)[0]
    return int(rr[0]), int(rr[-1]), int(cc[0]), int(cc[-1])


def strip_lines(arr, ink, box):
    t, b, l, r = box
    clean = arr.copy()
    reg = ink[t:b + 1, l:r + 1]
    for y in np.where(reg.mean(axis=1) > 0.5)[0]:
        clean[t + y, :] = 255
    for x in np.where(reg.mean(axis=0) > 0.5)[0]:
        clean[:, l + x] = 255
    return clean


# ---------- класс и ячейка ----------
LAT = {"a": "а", "b": "б", "v": "в", "g": "г", "d": "д", "e": "е", "k": "к",
       "m": "м", "n": "н", "o": "о", "p": "п", "c": "с", "t": "т", "y": "у",
       "x": "х", "h": "н", "6": "б"}
LOOK = {"а": "а я @ 4 α", "б": "б 6 b", "в": "в v", "г": "г g", "д": "д d"}
RE_CLASS = re.compile(r"^\d{1,2}[а-яё]$")
RE_T = re.compile(r"[А-ЯЁA-Z][а-яёa-z]{2,}\s+[А-ЯЁA-Z]\s*[.,]")
RE_R = re.compile(r"[А-ЯЁA-Z][а-яёa-z]{2,}\s+\d{3}")


def norm(s):
    s = s.strip().lower().replace(" ", "").replace("-", "").replace(".", "")
    return
