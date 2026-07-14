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
from app.permissions import action_needs_approval, role_can_do_action
from app.audit import log_event, AUDIT_EVENTS
from app.graph import graph

app = FastAPI(title="Корпоративный AI-ассистент (портфолио)")

# Здесь мы храним черновики задач, которые ждут подтверждения.
# Ключ — id черновика, значение — данные задачи.
PENDING_TASKS = {}


# ---- Описание того, что приходит в запросах (валидация за нас) ----

class AskRequest(BaseModel):
    username: str          # кто спрашивает: alice / bob / admin
    question: str          # сам вопрос


class CreateTaskRequest(BaseModel):
    username: str
    title: str             # название задачи


class ApproveRequest(BaseModel):
    username: str
    thread_id: str
    decision: str          # "approve" или "reject"


# ================== ЭНДПОИНТ 1: ВОПРОС ПО ДОКУМЕНТАМ ==================

@app.post("/ask")
def ask(req: AskRequest):
    """
    Вопрос ИЛИ действие. Вся логика — в графе.
    Если граф встал на паузу (действие) — возвращаем карточку approval + thread_id.
    """
    user = get_user(req.username)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    log_event("question_received", user["user_id"], {"question": req.question})

    # Каждый прогон — свой уникальный thread_id (чтобы не мешать другим запросам)
    thread_id = f"task-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    result = graph.invoke(
        {"username": req.username, "question": req.question},
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


# ================== ЭНДПОИНТ 2: СОЗДАТЬ ЗАДАЧУ (черновик) ==================

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
                  {"action": "approve", "reason": "role_not_allowed"})
        raise HTTPException(status_code=403,
                            detail="У вашей роли нет прав на подтверждение задач.")

    # ── Проверка 2: запрет самоподтверждения (separation of duties) ──
    creator = snapshot.values["username"]           # кто создал (из графа)
    if req.username == creator:                     # подтверждает тот же?
        log_event("action_denied", user["user_id"],
                  {"action": "approve", "reason": "self_approval_forbidden"})
        raise HTTPException(status_code=403,
                            detail="Нельзя подтверждать собственную задачу. Нужен другой человек.")

    # Проверки пройдены — возобновляем граф
    final = graph.invoke(Command(resume=req.decision), config=config)

    return {
        "status": "done",
        "answer": final["answer"],
    }

# ================== ЭНДПОИНТ 3: ПОДТВЕРДИТЬ ИЛИ ОТКЛОНИТЬ ==================

@app.post("/approve")
def approve(req: ApproveRequest):
    """
    Человек подтверждает или отклоняет черновик. Только после "approve"
    задача считается созданной. Это и есть безопасная остановка.
    """
    user = get_user(req.username)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    task = PENDING_TASKS.get(req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Черновик задачи не найден")
    
    # Проверка 1: есть ли у роли право подтверждать вообще
    if not role_can_do_action(user["role"], "approve"):
        log_event("action_denied", user["user_id"],
                  {"action": "approve", "reason": "role_not_allowed"})
        raise HTTPException(
            status_code=403,
            detail="У вашей роли нет прав на подтверждение задач.",
        )

    # Проверка 2: нельзя подтверждать СВОЙ собственный черновик
    # (иначе "человек в цепочке" = тот же человек, что и запросил — контроля ноль)
    if task["requested_by"] == user["user_id"]:
        log_event("action_denied", user["user_id"],
                  {"action": "approve", "reason": "self_approval_forbidden"})
        raise HTTPException(
            status_code=403,
            detail="Нельзя подтверждать собственную задачу. Нужен другой человек.",
        )

    if req.decision == "approve":
        task["status"] = "created"
        # Здесь в реальном проекте вызвался бы мок Jira-инструмента
        fake_url = f"https://jira.example.com/browse/AI-{req.task_id}"
        log_event("task_approved", user["user_id"],
                  {"task_id": req.task_id, "url": fake_url})
        return {
            "message": "Готово. Задача создана после вашего подтверждения.",
            "url": fake_url,
            "task": task,
        }
    else:
        task["status"] = "rejected"
        log_event("task_rejected", user["user_id"], {"task_id": req.task_id})
        return {
            "message": "Действие не выполнено: задача отклонена.",
            "task": task,
        }


# ================== ЭНДПОИНТ 4: ПОСМОТРЕТЬ ЖУРНАЛ ==================

@app.get("/audit")
def get_audit():
    """Показывает журнал всех событий. Удобно для демо и отладки."""
    return {"events": AUDIT_EVENTS}


@app.get("/")
def root():
    return {"message": "Ассистент работает. Открой /docs, чтобы потыкать запросы."}
