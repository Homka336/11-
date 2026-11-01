import os
import re
import requests
import pandas as pd
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


def normalize_class(name):
    name = name.strip().lower()
    name = name.replace(" ", "")
    name = name.replace("-", "")
    out = ""
    for ch in name:
        out += LAT.get(ch, ch)
    return out


CLASS_RE = re.compile(r"^(\d{1,2})([а-яa-z])$")


def parse_schedule(pdf_url, target_class):
    target = normalize_class(target_class)
    resp = requests.get(pdf_url, timeout=30)
    resp.raise_for_status()
    pdf = pymupdf.open(stream=BytesIO(resp.content),
                       filetype="pdf")
    lessons = []
    found_class = False

    for page in pdf:
        tables = page.find_tables().tables
        for table in tables:
            df = table.to_pandas()
            col_class = {}
            for col in df.columns:
                c = str(col).strip()
                if CLASS_RE.match(c):
                    col_class[col] = normalize_class(c)
            target_col = None
            for c, v in col_class.items():
                if v == target:
                    target_col = c
            if target_col is not None:
                found_class = True

            for _, row in df.iterrows():
                vals = []
                for v in row.values:
                    s = str(v).strip()
                    if pd.notna(v) and s not in ("", "nan"):
                        vals.append(s)
                if not vals:
                    continue
                if "№" in vals:
                    for col in df.columns:
                        c = str(row[col]).strip()
                        ok = pd.notna(row[col])
                        if ok and CLASS_RE.match(c):
                            col_class[col] = normalize_class(c)
                    target_col = None
                    for c, v in col_class.items():
                        if v == target:
                            target_col = c
                    if target_col is not None:
                        found_class = True
                    continue
                if target_col is None:
                    continue
                cell = str(row[target_col]).strip()
                if not cell or cell == "nan":
                    continue
                num = None
                for v in vals:
                    if v.isdigit() and 1 <= int(v) <= 10:
                        num = int(v)
                        break
                if num is not None:
                    lessons.append((num, cell))

    if not found_class:
        return "❌ Class " + target_class + " not found."
    if not lessons:
        return "📭 Class " + target + " has no lessons."

    lines = []
    head = "📚 Schedule for class " + target + ":"
    lines.append(head)
    lines.append("")
    lessons.sort(key=lambda x: x[0])
    for num, cell in lessons:
        parts = []
        for p in cell.split("\n"):
            p = p.strip()
            if p:
                parts.append(p)
        subject = parts[0]
        teacher = ""
        if len(parts) > 1:
            teacher = ", ".join(parts[1:])
        lines.append(str(num) + ". " + subject)
        if teacher:
            lines.append("👤 " + teacher)
        lines.append("")
    return "\n".join(lines)


def send_message(text):
    base = "https://api.telegram.org/bot"
    url = base + BOT_TOKEN + "/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    r = requests.post(url, json=data)
    print("Send status:", r.status_code)


if __name__ == "__main__":
    try:
        text = parse_schedule(PDF_URL, MY_CLASS)
    except Exception as e:
        text = "❌ Error: " + str(e)
    print(text)
    send_message(text)
