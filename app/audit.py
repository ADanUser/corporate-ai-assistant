"""
Логирование действий (audit log).

Каждое важное событие мы записываем: кто, что, когда, какой результат.
В реальном проекте это идёт в базу данных. Для демо — в список в памяти
и в файл.
"""

import json
from datetime import datetime

# Храним события в памяти, чтобы показать их через отдельный эндпоинт
AUDIT_EVENTS = []


def log_event(event_type: str, user_id: str, details: dict, thread_id: str = None):
    """Записывает одно событие в журнал."""
    event = {
        "event_type": event_type,
        "user_id": user_id,
        "details": details,
        "thread_id": thread_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    AUDIT_EVENTS.append(event)

    # Дополнительно пишем в файл, чтобы журнал не пропал после перезапуска
    with open("audit_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    return event
