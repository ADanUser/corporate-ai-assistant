"""
Единая точка доступа к языковой модели.

Раньше клиент Gemini жил внутри search.py, и nodes.py импортировал его
оттуда: генерация ответов зависела от модуля поиска без всякой причины.
Теперь узлы вызывают generate_text() и не знают, какой провайдер за ней.
Смена модели — правка одного этого файла.
"""

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

_api_key = os.getenv("GEMINI_API_KEY")
if not _api_key:
    raise RuntimeError(
        "Не найден GEMINI_API_KEY. Создай файл .env и впиши в него строку:\n"
        "GEMINI_API_KEY=твой_ключ"
    )

_client = genai.Client(api_key=_api_key)
_MODEL = "gemini-3.1-flash-lite"


def generate_text(prompt: str) -> str:
    """
    Отправляет промпт модели и возвращает текст ответа.
    thinking_budget=0 — ни классификатору, ни короткому ответу по абзацу
    "размышления" не нужны: так быстрее, дешевле и без warning про thoughts.
    Исключения НЕ ловим здесь: как реагировать на сбой, решает узел
    (intent откатывается в "question", answer — в сырой текст документа).
    """
    response = _client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return (response.text or "").strip()