import os
import re
import requests
import pymupdf
from io import BytesIO

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])
PDF_URL = "https://kirovskschool5.gosuslugi.ru/"
PDF_URL += "netcat_files/userfiles/raspisanie2026.pdf"
MY_CLASS = os.environ.get("MY_CLASS", "11а")
PICK = os.environ.get("PICK", "last")

LAT = {"a": "а", "b": "б", "v": "в",
       "g": "г", "d": "д", "e": "е",
       "k": "к", "m": "м", "n": "н",
       "o": "о", "p": "п", "c": "с",
       "t": "т", "y": "у", "x": "х"}

CLS = re.compile(r"^(\d{1,2})([а-яё])$")
TEACH = re.compile(r"[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.")
ROOM = re.compile(r"\b\d{3}[а-яё]?\b")


def norm(s):
    s = s.strip().lower()
    s = s.replace(" ", "")
    s = s.replace("-", "")
    out = ""
    for ch in s:
        out += LAT.get(ch, ch)
    return out


def group_rows(toks):
    rows = []
    for t in sorted(toks, key=lambda z: z[1]):
        done = False
        for row in rows:
            if abs(row[0][1] - t[1]) < 6:
                row.append(t)
                done = True
                break
        if not done:
            rows.append([t])
    for row in rows:
        row.sort(key=lambda z: z[0])
    rows.sort(key=lambda z: z[0][1])
    return rows


def lines_of(words):
    lines = []
    for w in sorted(words, key=lambda z: z[1]):
        done = False
        for ln in lines:
            if abs(ln[0][1] - w[1]) < 4:
                ln.append(w)
                done = True
                break
        if not done:
            lines.append([w])
    res = []
    for ln in lines:
        ln.sort(key=lambda z: z[0])
        res.append(" ".join(z[4] for z in ln))
    return res


def split_cell(cell):
    subj = []
    teach = []
    mode = "s"
    for ln in lines_of(cell):
        if TEACH.search(ln) or ROOM.search(ln):
            mode = "t"
        if mode == "s":
            subj.append(ln)
        else:
            teach.append(ln)
    return subj, teach


def send_message(text):
    base = "https://api.telegram.org/bot"
    url = base + BOT_TOKEN + "/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    r = requests.post(url, json=data)
    print("Send status:", r.status_code)
    print(r.text)
    if r.status_code != 200:
        raise SystemExit("Message not sent!")


def send_photo(png, caption):
    base = "https://api.telegram.org/bot"
    url = base + BOT_TOKEN + "/sendPhoto"
    data = {"chat_id": CHAT_ID, "caption": caption}
    files = {"photo": ("page.png", png)}
    r = requests.post(url, data=data, files=files)
    print("Photo status:", r.status_code)


def parse_schedule(pdf_url, target_class):
    target = norm(target_class)
    resp = requests.get(pdf_url, timeout=30)
    resp.raise_for_status()
    pdf = pymupdf.open(stream=BytesIO(resp.content),
                       filetype="pdf")
    blocks = []
    found = []
    dbg = []

    for page in pdf:
        words = page.get_text("words")
        if not words:
            dbg.append("p" + str(page.number + 1) + ":scan")
            continue
        toks = [w for w in words
                if CLS.match(norm(w[4]))]
        for t in toks:
            found.append(norm(t[4]))
        rows = group_rows(toks)
        for i, row in enumerate(rows):
            names = [norm(t[4]) for t in row]
            ks = [idx for idx, n in enumerate(names)
                  if n == target]
            if not ks:
                continue
            dbg.append("p" + str(page.number + 1))
            for k in ks:
                tok = row[k]
                left = tok[0] - 40
                if k > 0:
                    left = (row[k - 1][2] + tok[0]) / 2
                right = tok[2] + 40
                if k + 1 < len(row):
                    right = (tok[2] + row[k + 1][0]) / 2
                top = tok[3] + 2
                if i + 1 < len(rows):
                    bot = rows[i + 1][0][1] - 2
                else:
                    bot = page.rect.height
                colw = []
                nums = []
                x_first = row[0][0] - 2
                for w in words:
                    y = w[1]
                    if not (top < y < bot):
                        continue
                    cx = (w[0] + w[2]) / 2
                    t = w[4].strip()
                    if t.isdigit() and 1 <= int(t) <= 10:
                        if cx < x
