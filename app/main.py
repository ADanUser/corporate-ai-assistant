"""
ГЛАВНЫЙ ФАЙЛ. Здесь собирается весь конвейер и запускается веб-сервис.

Запуск (из папки corporate-assistant):
    uvicorn app.main:app --reload

После запуска открой в браузере:  http://localhost:8000/docs
Там будет удобная страница, где можно потыкать все запросы мышкой.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import uuid                              # для генерации уникального thread_id
from langgraph.types import Command      # для возобновления графа
from app.identity import get_user
from app.permissions import (
    role_can_do_action,
    disable_action,
    enable_action,
    DISABLED_ACTIONS,
)
from app.audit import log_event, AUDIT_EVENTS
from app.graph import graph
from typing import Literal

app = FastAPI(title="Корпоративный AI-ассистент (портфолио)")


# ---- Описание того, что приходит в запросах (валидация за нас) ----

class AskRequest(BaseModel):
    username: str          # кто спрашивает: alice / bob / admin
    question: str          # сам вопрос


class ApproveRequest(BaseModel):
    username: str
    thread_id: str                           # номерок, полученный из /ask
    decision: Literal["approve", "reject"]   # мусор отсекает Pydantic (422)


# ================== ЭНДПОИНТ 1: ВОПРОС ИЛИ ДЕЙСТВИЕ ==================

@app.post("/ask")
def ask(req: AskRequest):
    user = get_user(req.username)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Сначала создаём thread_id — он нужен уже первому событию
    thread_id = f"task-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    # Теперь логируем — thread_id уже существует
    log_event("question_received", user["user_id"],
              {"question_len": len(req.question)}, thread_id)

    result = graph.invoke(
        {
            "username": req.username,
            "question": req.question,
            "thread_id": thread_id,
        },
        config=config,
    )

    # Признак: если answer нет — граф встал на паузу (это было действие)
    if "answer" not in result:
        snapshot = graph.get_state(config)
        card = snapshot.tasks[0].interrupts[0].value
        return {
            "status": "pending_approval",
            "thread_id": thread_id,          # ← пользователь вернёт его в /approve
            "approval_card": card,
        }

    # Иначе граф дошёл до конца — обычный ответ
    return {
        "status": "done",
        "answer": result["answer"],
        "sources": result["sources"],
        "security_flag": result.get("security_flag", False),
    }


# ================== ЭНДПОИНТ 2: ПОДТВЕРДИТЬ ИЛИ ОТКЛОНИТЬ ==================

@app.post("/approve")
def approve(req: ApproveRequest):
    """
    Возобновляет замороженный граф по thread_id и передаёт решение человека.
    С проверками безопасности: право на approve + запрет самоподтверждения.
    """
    user = get_user(req.username)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    config = {"configurable": {"thread_id": req.thread_id}}

    # Достаём замороженное состояние графа
    snapshot = graph.get_state(config)

    # Если задачи нет или она уже не на паузе — нечего подтверждать
    if not snapshot.next:
        raise HTTPException(status_code=404,
                            detail="Нет задачи, ожидающей подтверждения")

    # ── Проверка 1: есть ли у роли право подтверждать ──
    if not role_can_do_action(user["role"], "approve"):
        log_event("action_denied", user["user_id"],
                  {"action": "approve", "reason": "role_not_allowed"}, req.thread_id)
        raise HTTPException(status_code=403,
                            detail="У вашей роли нет прав на подтверждение задач.")

    # ── Проверка 2: запрет самоподтверждения (separation of duties) ──
    creator = snapshot.values["username"]           # кто создал (из графа)
    if req.username == creator:                     # подтверждает тот же?
        log_event("action_denied", user["user_id"],
                  {"action": "approve", "reason": "self_approval_forbidden"}, req.thread_id)
        raise HTTPException(status_code=403,
                            detail="Нельзя подтверждать собственную задачу. Нужен другой человек.")

    # Передаём не только решение, но и КТО его принял.
    # user["user_id"] — из хранилища, а не из тела запроса.
    final = graph.invoke(
        Command(resume={"decision": req.decision, "approver": user["user_id"]}),
        config=config,
    )

    return {
        "status": "done",
        "answer": final["answer"],
    }


# ================== ЭНДПОИНТ 3: АВАРИЙНОЕ УПРАВЛЕНИЕ ==================

class KillSwitchRequest(BaseModel):
    username: str
    action_name: str       # какой инструмент, например "create_task"
    enabled: bool          # False = выключить, True = включить обратно


@app.post("/admin/tools")
def toggle_tool(req: KillSwitchRequest):
    """
    Аварийный выключатель инструмента. Только для Admin.
    Позволяет отключить сломанный инструмент без правки кода и деплоя.
    """
    user = get_user(req.username)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Управлять выключателем может только Admin — это операция безопасности
    if user["role"] != "Admin":
        log_event("action_denied", user["user_id"],
                  {"action": "toggle_tool", "reason": "role_not_allowed"}, None)
        raise HTTPException(status_code=403,
                            detail="Управление инструментами доступно только Admin.")

    if req.enabled:
        enable_action(req.action_name)
        event = "tool_enabled"
    else:
        disable_action(req.action_name)
        event = "tool_disabled"

    # Включение и выключение инструмента — событие безопасности, логируем оба
    log_event(event, user["user_id"], {"action": req.action_name}, None)

    return {"status": "ok", "disabled_actions": sorted(DISABLED_ACTIONS)}


# ================== ЭНДПОИНТ 4: ПОСМОТРЕТЬ ЖУРНАЛ ==================

@app.get("/audit")
def get_audit():
    """Показывает журнал всех событий. Удобно для демо и отладки."""
    return {"events": AUDIT_EVENTS}


@app.get("/")
def root():
    return {"message": "Ассистент работает. Открой /docs, чтобы потыкать запросы."}