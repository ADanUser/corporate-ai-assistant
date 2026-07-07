"""
ГЛАВНЫЙ ФАЙЛ. Здесь собирается весь конвейер и запускается веб-сервис.

Запуск (из папки corporate-assistant):
    uvicorn app.main:app --reload

После запуска открой в браузере:  http://localhost:8000/docs
Там будет удобная страница, где можно потыкать все запросы мышкой.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.identity import get_user
from app.data.documents import DOCUMENTS
from app.permissions import filter_documents_by_role, action_needs_approval
from app.retrieval import simple_search, looks_like_injection
from app.audit import log_event, AUDIT_EVENTS

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
    task_id: str
    decision: str          # "approve" или "reject"


# ================== ЭНДПОИНТ 1: ВОПРОС ПО ДОКУМЕНТАМ ==================

@app.post("/ask")
def ask(req: AskRequest):
    """
    Пользователь задаёт вопрос. Бот ищет ответ ТОЛЬКО в тех документах,
    которые разрешены его роли, и указывает источник.
    """
    # Шаг 1: кто это?
    user = get_user(req.username)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    log_event("question_received", user["user_id"], {"question": req.question})

    # Шаг 3: фильтруем документы по роли ДО поиска.
    # Employee тут физически не получит зарплатный документ.
    allowed_docs = filter_documents_by_role(DOCUMENTS, user["role"])

    # Шаг 4: ищем среди разрешённых документов
    found = simple_search(req.question, allowed_docs)

    # Защита: проверяем, нет ли в найденных документах "команд для бота"
    security_flag = any(looks_like_injection(d["text"]) for d in found)
    if security_flag:
        log_event("security_flag", user["user_id"],
                  {"reason": "possible_prompt_injection"})

    # Если ничего не нашли — честно говорим "не найдено", а не выдумываем
    if not found:
        log_event("no_source_answer", user["user_id"], {})
        return {
            "answer": "В доступных мне документах нет ответа на этот вопрос.",
            "sources": [],
            "security_flag": security_flag,
        }

    # Формируем ответ. В реальном проекте здесь текст пишет нейросеть
    # на основе найденных кусков. Для демо мы отдаём текст документа
    # и — главное — источник.
    best = found[0]
    log_event("answer_given", user["user_id"], {"source": best["source"]})
    return {
        "answer": best["text"],
        "sources": [best["source"]],
        "security_flag": security_flag,
    }


# ================== ЭНДПОИНТ 2: СОЗДАТЬ ЗАДАЧУ (черновик) ==================

@app.post("/create-task")
def create_task(req: CreateTaskRequest):
    """
    Пользователь просит создать задачу. Бот НЕ создаёт её сразу.
    Он готовит черновик и ждёт подтверждения (human-in-the-loop).
    """
    user = get_user(req.username)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Это рискованное действие — значит, нужно подтверждение
    needs_approval = action_needs_approval("create_task")

    task_id = f"task_{len(PENDING_TASKS) + 1}"
    PENDING_TASKS[task_id] = {
        "task_id": task_id,
        "title": req.title,
        "requested_by": user["user_id"],
        "status": "pending_approval",
    }

    log_event("task_draft_created", user["user_id"],
              {"task_id": task_id, "title": req.title})

    return {
        "message": "Черновик задачи готов. Требуется подтверждение.",
        "task_id": task_id,
        "preview": PENDING_TASKS[task_id],
        "needs_approval": needs_approval,
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
