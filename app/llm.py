"""
Единая точка доступа к языковой модели.
"""

import os
import time                      # ← нужен для пауз между повторами

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

# Сколько раз пробуем повторить запрос при ВРЕМЕННОМ сбое провайдера.
# Лежит рядом с моделью: это настройка доступа к LLM, а не логика узла.
_MAX_RETRIES = 4


def generate_text(prompt: str) -> str:
    """
    Отправляет промпт модели и возвращает текст ответа.
    thinking_budget=0 — ни классификатору, ни короткому ответу по абзацу
    "размышления" не нужны: так быстрее, дешевле и без warning про thoughts.

    Ретраи с экспоненциальной паузой: провайдер отвечает 429 при
    превышении квоты, и это временная ошибка — через несколько секунд
    запрос пройдёт. Без ретраев серия запросов подряд (прогон eval-
    датасета) выбивает квоту и валит всё, что идёт после.

    Исключение пробрасывается только после исчерпания попыток: как
    реагировать на окончательный сбой, решает узел графа
    (intent откатывается в "question", answer — в сырой текст документа).
    """
    delay = 2
    for attempt in range(_MAX_RETRIES):
        try:
            response = _client.models.generate_content(
                model=_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            return (response.text or "").strip()
        except Exception as e:
            # Повторяем только ВРЕМЕННЫЕ ошибки. Неверный ключ или битый
            # промпт от повтора не починятся — падаем сразу, без задержек.
            transient = any(s in str(e).lower()
                            for s in ("429", "resource_exhausted", "503",
                                      "unavailable", "timeout", "deadline"))
            if not transient or attempt == _MAX_RETRIES - 1:
                raise
            time.sleep(delay)
            delay *= 2          # паузы: 2 → 4 → 8 секунд