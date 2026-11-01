import pymupdf
import requests
from io import BytesIO
import pandas as pd
import os

# Берём настройки из секретов GitHub
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])
PDF_URL = "https://kirovskschool5.gosuslugi.ru/netcat_files/userfiles/raspisanie2026.pdf"
MY_CLASS = os.environ.get("MY_CLASS", "9б")

def parse_schedule(pdf_url: str, target_class: str) -> str | None:
    """Скачивает PDF и парсит расписание для указанного класса."""
    try:
        response = requests.get(pdf_url, timeout=30)
        if response.status_code != 200:
            return f"❌ Ошибка загрузки PDF: {response.status_code}"

        pdf_document = pymupdf.open(stream=BytesIO(response.content), filetype="pdf")

        all_data = []
        for page_num in range(pdf_document.page_count):
            page = pdf_document[page_num]
            tables = page.find_tables()
            for table in tables.tables:
                df = table.to_pandas()
                all_data.append(df)

        df_full = pd.concat(all_data, ignore_index=True)

        # Ищем нужный класс в таблице
        class_schedule = {}
        current_class = None

        for idx, row in df_full.iterrows():
            for col in df_full.columns:
                cell = str(row[col])
                if cell.strip() == target_class:
                    current_class = col
                    break
            if current_class:
                break

        if not current_class:
            return f"❌ Класс '{target_class}' не найден в расписании."

        # Собираем уроки
        lessons = []
        found_header = False

        for idx, row in df_full.iterrows():
            row_values = [str(v).strip() for v in row.values if pd.notna(v)]
            if target_class in row_values and "№" in row_values:
                found_header = True
                continue

            if found_header:
                first_col = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
                target_col_value = str(row[current_class]).strip() if pd.notna(row[current_class]) else ""

                if first_col.isdigit():
                    lesson_num = int(first_col)
                    if target_col_value and target_col_value not in ["nan", "None", ""]:
                        lessons.append((lesson_num, target_col_value))

                # Если начался новый блок классов — выходим
                if "№" in str(row.iloc[0]) if pd.notna(row.iloc[0]) else "":
                    break

        if not lessons:
            return f"📋 Расписание для {target_class} пустое."

        # Формируем сообщение
        result = f"📚 Расписание для класса *{target_class}* на завтра:\n\n"
        for num, lesson in sorted(lessons):
            parts = lesson.split("\\n")
            subject = parts[0]
            teacher = parts[1] if len(parts) >= 2 else ""
            result += f"*{num}.* {subject}"
            if teacher:
                result += f"\n👤 _{teacher}_"
            result += "\n\n"

        return result

    except Exception as e:
        return f"❌ Ошибка при парсинге: {str(e)}"


def send_message(text):
    """Отправляет сообщение в Telegram"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    r = requests.post(url, json=data)
    if r.status_code == 200:
        print("✅ Сообщение отправлено!")
    else:
        print(f"❌ Ошибка отправки: {r.text}")


if __name__ == "__main__":
    schedule_text = parse_schedule(PDF_URL, MY_CLASS)
    print("Расписание:", schedule_text)
    send_message(schedule_text)
