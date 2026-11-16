"""Бот расписания: последний лист PDF -> OCR -> расписание класса -> Telegram."""
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


# ---------- геометрия таблицы ----------
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
    """Убираем линейки таблицы: с ними tesseract теряет половину текста."""
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
RE_CLASS = re.compile(r"^\d{1,2}[а-яё]$")
RE_T = re.compile(r"[А-ЯЁA-Z][а-яёa-z]{2,}\s+[А-ЯЁA-Z]\s*[.,]")
RE_R = re.compile(r"[А-ЯЁA-Z][а-яёa-z]{2,}\s+\d{3}")


def norm(s):
    s = s.strip().lower().replace(" ", "").replace("-", "").replace(".", "")
    return "".join(LAT.get(c, c) for c in s)


def is_class(s):
    return bool(RE_CLASS.match(norm(s)))


def split_cell(text):
    text = " ".join(text.split())
    st = [m.start() for m in (RE_T.search(text), RE_R.search(text)) if m]
    if not st:
        return text, ""
    i = min(st)
    return text[:i].strip(" ,"), text[i:].strip()


# ---------- главный разбор ----------
def parse_last_page(pdf):
    page = pdf[-1]
    pix = page.get_pixmap(dpi=DPI)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    a = np.array(Image.fromarray(a).convert("L"))
    ink = a < 160
    box = bbox(ink)

    words = ocr_words(strip_lines(a, ink, box))
    log("OCR слов:", len(words))
    cands = [w for w in words if is_class(w[4])]
    log("классы:", [w[4] for w in cands])
    hits = [w for w in cands if norm(w[4]) == norm(CLASS)]
    if not hits:
        raise LookupError("класс " + CLASS + " не найден; видно: "
                          + ", ".join(sorted({w[4] for w in cands})))
    x0, y0, x1, y1, _ = hits[-1]
    cx = (x0 + x1) / 2

    t, b, l, r = box
    hl = groups(np.where(ink[:, l:r + 1].mean(axis=1) > 0.45)[0])
    head = min(g for g in hl if g[0] > y1 - 4)          # линия под шапкой
    marks = [w[1] for w in words if w[4].strip("№NоOo ") == "" and w[1] > y1 + 10]
    stop = min(marks) if marks else b + 1               # следующая шапка
    band = [g for g in hl if head[0] <= g[0] < stop - 5]
    if len(band) < 2:
        raise LookupError("нет границ строк")
    top, bot = head[1], band[-1][1]

    vl = groups(np.where(ink[top:bot, :].mean(axis=0) > 0.6)[0])
    left = max(v[1] for v in vl if v[1] < cx)
    right = min(v[0] for v in vl if v[0] > cx)
    nl, nr = vl[0][1], vl[1][0]                         # колонка номеров уроков
    log(f"колонка {CLASS}: x {left}-{right}, y {top}-{bot}")

    lessons = []
    for i, (a1, a2) in enumerate(zip(band[:-1], band[1:]), 1):
        cell = a[a1[1] + 3:a2[0] - 2, left + 3:right - 2]
        if cell.size == 0 or (cell < 160).mean() < 0.004:
            continue                                    # пустой урок
        subj, teach = split_cell(ocr(cell))
        if not subj and not teach:
            continue
        num = "".join(c for c in ocr(a[a1[1] + 3:a2[0] - 2, nl + 2:nr - 2],
                                     psm="7", whitelist="0123456789", scale=3)
                      if c.isdigit())
        lessons.append((int(num) if num else i, subj, teach))
    return lessons


def find_date(pdf):
    for page in reversed(list(pdf)):
        clip = pymupdf.Rect(0, 0, page.rect.width, page.rect.height * 0.13)
        pix = page.get_pixmap(dpi=250, clip=clip)
        a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
        a = np.array(Image.fromarray(a).convert("L"))
        for line in ocr(a, scale=1).splitlines():
            if "асписание" in line:
                return " ".join(line.split())
    return ""


def page_jpeg(pdf):
    im = pdf[-1].get_images(full=True)
    if im:
        info = pdf.extract_image(im[0][0])
        return info["image"], info["ext"]
    return pdf[-1].get_pixmap(dpi=200).tobytes("png"), "png"


def build_message(ls, date):
    d = date.replace("Расписание на", "").strip()
    head = f"📚 {CLASS} — {d}" if d else f"📚 Расписание {CLASS} (последний лист)"
    out = [head, ""]
    for n, s, t in sorted(ls):
        out.append(f"{n}. {s}" + (f"\n   👤 {t}" if t else ""))
    out += ["", "⚠️ Распознано со скана — сверяйся с оригиналом."]
    return "\n".join(out)


def main():
    log(f"::add-mask::{TOKEN}")
    pdf = pymupdf.open(stream=io.BytesIO(fetch_pdf()), filetype="pdf")
    date = find_date(pdf)
    log("дата:", date or "не найдена")
    try:
        ls = parse_last_page(pdf)
        if not ls:
            raise LookupError("пустая колонка")
        text = build_message(ls, date)
        log(text)
        tg("sendMessage", {"chat_id": CHAT, "text": text})
    except Exception as e:
        log("Разбор не удался:", type(e).__name__, str(e).replace(TOKEN, "***"))
        img, ext = page_jpeg(pdf)
        tg("sendDocument",
           {"chat_id": CHAT,
            "caption": f"⚠️ Не смог разобрать ({type(e).__name__}). "
                       f"Последний лист целиком. {date}"},
           {"document": (f"raspisanie.{ext}", img)})
    finally:
        pdf.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        m = "❌ Ошибка: " + str(e).replace(TOKEN, "***")
        log(m)
        try:
            tg("sendMessage", {"chat_id": CHAT, "text": m})
        except Exception as e2:
            log("не отправилось:", str(e2).replace(TOKEN, "***"))
        raise SystemExit(1)
