import os
import re
import requests
import pandas as pd
import pymupdf
from io import BytesIO

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])
PDF_URL = "https://kirovskschool5.gosuslugi.ru/netcat_files/userfiles/raspisanie2026.pdf"
MY_CLASS = os.environ.get("MY_CLASS", "11а")

LAT_TO_CYR = {"a": "а", "b": "б", "v": "в", "g": "г", "d": "д",
              "e": "е", "k": "к", "m": "м", "n": "н", "o": "о",
              "p": "п", "c": "с", "t": "т", "y": "у", "x": "х"}

def normalize_class(name: str) -> str:
    """Приводит '11A' / '11 а' / '11-а' к виду '11а'"""
    name = name.strip().lower().replace(" ", "").replace("-", "")
    return "".join(LAT_TO_CYR.get(ch, ch) for ch in name)

CLASS_RE = re.compile(r"^(\d{1,2})([а-яa-z])$", re.IGNORECASE)

def parse_schedule(pdf_url: str, target_class: str):
    target = normalize_class(target_class)
    response = requests.get(pdf_url, timeout=30)
    response.raise_for_status()
    pdf = pymupdf.open(stream=BytesIO(response.content), filetype="pdf")

    lessons = []
    found_class = False

    for page in pdf:
        for table in page.find_tables().tables:
            df = table.to_pandas()
            # соответствие колонка -> класс
            col_class = {}
            for col in df.columns:
                if CLASS_RE.match(str(col).strip()):
                    col_class[col] = normalize_class(str(col).strip())
            target_col = next((c for c, v in col_class.items() if v == target), None)
            if target_col is not None:
                found_class = True

            for _, row in df.iterrows():
                vals = [str(v).strip() for v in row.values
                        if pd.notna(v) and str(v).strip() not in ("", "nan")]
                if not vals:
                    continue
                if "№" in vals:
                    # новая группа классов — обновляем соответствие
                    for col in df.columns:
                        c = str(row[col]).strip() if pd.notna(row[col]) else ""
                        if CLASS_RE.match(c):
                            col_class[col] = normalize_class(c)
                    target_col = next((c for c, v in col_class.items() if v == target), None)
                    if target_col is not None:
                        found_class = True
                    continue
                if target_col is not None:
                    cell = str(row[target_col]).strip() if pd.notna(row[target_col]) else ""
                    if cell and cell != "nan":
                        num = next((int(v) for v in vals if v.isdigit() and 1 <= int(v) <= 10), None)
                        if num:
                            lessons.append((num, cell))

    if not found_class:
        return (f"❌ Класс '{target_class}' не найден.\n"
                f"Проверьте секрет MY_CLASS (пример: 11а).")
    if not lessons:
        return f"📋 У класса {target} уроков нет (выходной или каникулы)."

    lines = [f"📚 Расписание для класса
