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


def header_rows(page):
    toks = []
    for w in page.get_text("words"):
        if CLS.match(norm(w[4])):
            toks.append(w)
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
    out = []
    for row in rows:
        row.sort(key=lambda z: z[0])
        if len(row) >= 2:
            out.append(row)
    out.sort(key=lambda z: z[0][1])
    return out


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


def parse_schedule(pdf_url, target_class):
    target = norm(target_class)
    resp = requests.get(pdf_url, timeout=30)
    resp.raise_for_status()
    pdf = pymupdf.open(stream=BytesIO(resp.content),
                       filetype="pdf")
    lessons = []
    found = []

    for page in pdf:
        rows = header_rows(page)
        for r in rows:
            for t in r:
                found.append(norm(t[4]))
        for i, row in enumerate(rows):
            names = [norm(t[4]) for t in row]
            if target not in names:
                continue
            k = names.index(target)
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
            for w in page.get_text("words"):
                y = w[1]
                if not (top < y < bot):
                    continue
                cx = (w[0] + w[2]) / 2
                t = w[4].strip()
                if t.isdigit() and 1 <= int(t) <= 10:
                    if cx < x_first:
                        nums.append(w)
                        continue
                if left <= cx <= right:
                    colw.append(w)
            block = []
            if not nums and colw:
                colw.sort(key=lambda z: z[1])
                cells = []
                cur = [colw[0]]
                for w in colw[1:]:
                    if w[1] - cur[-1][3] > 8:
                        cells.append(cur)
                        cur = [w]
                    else:
                        cur.append(w)
                cells.append(cur)
                for n, c in enumerate(cells, 1):
                    s, t2 = split_cell(c)
                    block.append((n, s, t2))
            nums.sort(key=lambda z: z[1])
            for j, nm in enumerate(nums):
                y0 = nm[1] - 4
                if j + 1 < len(nums):
                    y1 = nums[j + 1][1] - 4
                else:
                    y1 = bot
                cell = [w for w in colw
                        if y0 <= w[1] < y1]
                if not cell:
                    continue
                s, t2 = split_cell(cell)
                block.append((int(nm[4]), s, t2))
            lessons = block

    if not lessons:
        uniq = sorted(set(found))
        msg = "❌ Class " + target_class
        msg += " not found or has no lessons."
        msg += "\nClasses seen in PDF: "
        msg += ", ".join(uniq)
        return msg

    lessons.sort(key=lambda z: z[0])
    out = []
    out.append("📚 Schedule for " + target + ":")
    out.append("")
    for num, subj, teach in lessons:
        out.append(str(num) + ". " + " ".join(subj))
        if teach:
            out.append("👤 " + " ".join(teach))
        out.append("")
    return "\n".join(out)


def send_message(text):
    base = "https://api.telegram.org/bot"
    url = base + BOT_TOKEN + "/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    r = requests.post(url, json=data)
    print("Send status:", r.status_code)
    print(r.text)
    if r.status_code != 200:
        raise SystemExit("Message not sent!")


if __name__ == "__main__":
    try:
        text = parse_schedule(PDF_URL, MY_CLASS)
    except Exception as e:
        text = "❌ Error: " + str(e)
    print(text)
    send_message(text)
