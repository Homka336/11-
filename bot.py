import os
import re
import requests
import pymupdf
from io import BytesIO

TOKEN = os.environ["BOT_TOKEN"]
CHAT = int(os.environ["CHAT_ID"])
URL = "https://"
URL += "kirovskschool5.gosuslugi.ru/"
URL += "netcat_files/"
URL += "userfiles/raspisanie2026.pdf"
MC = os.environ.get("MY_CLASS", "11а")
PICK = os.environ.get("PICK", "last")

LAT = {"a": "а", "b": "б", "v": "в",
       "g": "г", "d": "д", "e": "е",
       "k": "к", "m": "м", "n": "н",
       "o": "о", "p": "п", "c": "с",
       "t": "т", "y": "у", "x": "х"}

RE1 = re.compile(r"^(\d{1,2})([а-яё])$")
RE2 = re.compile(r"[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.")
RE3 = re.compile(r"\b\d{3}[а-яё]?\b")


def nrm(s):
    s = s.strip().lower()
    s = s.replace(" ", "")
    s = s.replace("-", "")
    o = ""
    for c in s:
        o += LAT.get(c, c)
    return o


def rows(toks):
    r = []
    for t in sorted(toks, key=lambda z: z[1]):
        d = False
        for w in r:
            if abs(w[0][1] - t[1]) < 6:
                w.append(t)
                d = True
                break
        if not d:
            r.append([t])
    for w in r:
        w.sort(key=lambda z: z[0])
    r.sort(key=lambda z: z[0][1])
    return r


def lns(ws):
    r = []
    for w in sorted(ws, key=lambda z: z[1]):
        d = False
        for x in r:
            if abs(x[0][1] - w[1]) < 4:
                x.append(w)
                d = True
                break
        if not d:
            r.append([w])
    o = []
    for x in r:
        x.sort(key=lambda z: z[0])
        o.append(" ".join(z[4] for z in x))
    return o


def split(cell):
    s = []
    t = []
    m = "s"
    for x in lns(cell):
        if RE2.search(x) or RE3.search(x):
            m = "t"
        if m == "s":
            s.append(x)
        else:
            t.append(x)
    return s, t


def send(text):
    u = "https://"
    u += "api.telegram.org/bot"
    u += TOKEN + "/sendMessage"
    d = {"chat_id": CHAT, "text": text}
    r = requests.post(u, json=d)
    sc = r.status_code
    print("Send:", sc)
    print(r.text)
    if sc != 200:
        raise SystemExit("not sent")


def photo(png, cap):
    u = "https://"
    u += "api.telegram.org/bot"
    u += TOKEN + "/sendPhoto"
    d = {"chat_id": CHAT, "caption": cap}
    f = {"photo": ("p.png", png)}
    r = requests.post(u, data=d, files=f)
    print("Photo:", r.status_code)


def cols(pg, ws, row, k, i, rr):
    tok = row[k]
    lf = tok[0] - 40
    if k > 0:
        lf = (row[k - 1][2] + tok[0]) / 2
    rt = tok[2] + 40
    if k + 1 < len(row):
        rt = (tok[2] + row[k + 1][0]) / 2
    tp = tok[3] + 2
    if i + 1 < len(rr):
        bt = rr[i + 1][0][1] - 2
    else:
        bt = pg.rect.height
    cw = []
    nm = []
    xf = row[0][0] - 2
    for w in ws:
        y = w[1]
        if not (tp < y < bt):
            continue
        cx = (w[0] + w[2]) / 2
        t = w[4].strip()
        if t.isdigit():
            if 1 <= int(t) <= 10 and cx < xf:
                nm.append(w)
                continue
        if lf <= cx <= rt:
            cw.append(w)
    return cw, nm, bt


def block(cw, nm, bt):
    b = []
    if not nm and cw:
        cw.sort(key=lambda z: z[1])
        cs = []
        cur = [cw[0]]
        for w in cw[1:]:
            if w[1] - cur[-1][3] > 8:
                cs.append(cur)
                cur = [w]
            else:
                cur.append(w)
        cs.append(cur)
        for n, c in enumerate(cs, 1):
            s, t = split(c)
            b.append((n, s, t))
    nm.sort(key=lambda z: z[1])
    for j, n in enumerate(nm):
        y0 = n[1] - 4
        if j + 1 < len(nm):
            y1 = nm[j + 1][1] - 4
        else:
            y1 = bt
        cell = [w for w in cw if y0 <= w[1] < y1]
        if not cell:
            continue
        s, t = split(cell)
        b.append((int(n[4]), s, t))
    return b


def parse():
    tg = nrm(MC)
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    pdf = pymupdf.open(stream=BytesIO(r.content),
                       filetype="pdf")
    bs = []
    fd = []
    dg = []
    for pg in pdf:
        ws = pg.get_text("words")
        if not ws:
            dg.append("p%d:scan" % (pg.number + 1))
            continue
        tk = [w for w in ws if RE1.match(nrm(w[4]))]
        for t in tk:
            fd.append(nrm(t[4]))
        rr = rows(tk)
        for i, row in enumerate(rr):
            ns = [nrm(t[4]) for t in row]
            ks = [j for j, n in enumerate(ns)
                  if n == tg]
            if not ks:
                continue
            dg.append("p%d" % (pg.number + 1))
            for k in ks:
                cw, nm, bt = cols(pg, ws, row, k, i, rr)
                bs.append(block(cw, nm, bt))
    print("DEBUG:", " ".join(dg))
    print("DEBUG blocks:", len(bs))
    if not bs:
        last = pdf[-1]
        lw = last.get_text("words")
        if not lw:
            px = last.get_pixmap()
            photo(px.tobytes("png"), "Last sheet")
            return "📷 Sent last sheet as photo."
        u = sorted(set(fd))
        m = "❌ Class " + MC
        m += " not found."
        m += "\nSeen: "
        m += ", ".join(u)
        return m
    if PICK == "first":
        ls = bs[0]
    else:
        ls = bs[-1]
    if not ls:
        return "📭 No lessons for " + tg
    ls.sort(key=lambda z: z[0])
    o = ["📚 Schedule for " + tg + ":", ""]
    for n, s, t in ls:
        o.append(str(n) + ". " + " ".join(s))
        if t:
            o.append("👤 " + " ".join(t))
        o.append("")
    return "\n".join(o)


if __name__ == "__main__":
    try:
        tx = parse()
    except Exception as e:
        tx = "❌ Error: " + str(e)
    print(tx)
    send(tx)
