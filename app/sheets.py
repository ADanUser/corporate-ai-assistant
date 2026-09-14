"""
Интеграция с Google Sheets — реальный трекер задач вместо мока.

Клиент собирается лениво, при первом вызове, а не при импорте модуля:
app.tools импортируется тестами (tests/test_security.py), а тесты не
поднимают ключи внешних интеграций. Раннее падение здесь сломало бы
быстрые тесты, которые к Sheets вообще не обращаются.
"""

import json
import os
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_WORKSHEET_NAME = "Tasks"
_HEADER = ["Создано (UTC)", "Автор", "Роль", "Задача"]

_client = None


def _get_worksheet():
    global _client
    if _client is None:
        creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        if not creds_json or not sheet_id:
            raise RuntimeError(
                "Не настроена интеграция с Google Sheets. Нужны переменные "
                "окружения:\n"
                "GOOGLE_SERVICE_ACCOUNT_JSON — содержимое JSON-ключа "
                "сервисного аккаунта одной строкой\n"
                "GOOGLE_SHEET_ID — ID таблицы из её URL"
            )
        creds = Credentials.from_service_account_info(
            json.loads(creds_json), scopes=_SCOPES
        )
        _client = gspread.authorize(creds)

    spreadsheet = _client.open_by_key(os.environ["GOOGLE_SHEET_ID"])
    try:
        return spreadsheet.worksheet(_WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(_WORKSHEET_NAME, rows=100, cols=4)
        worksheet.append_row(_HEADER)
        return worksheet


def append_task(title: str, user: dict) -> None:
    """Дописывает строку с задачей в лист Tasks. Побочный эффект — только здесь."""
    worksheet = _get_worksheet()
    worksheet.append_row([
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        user["user_id"],
        user["role"],
        title,
    ])
