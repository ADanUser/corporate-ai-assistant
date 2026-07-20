from langgraph.types import interrupt
from app.identity import get_user
from app.data.documents import DOCUMENTS
from app.permissions import filter_documents_by_role, role_can_do_action
from app.retrieval import looks_like_injection
from google.genai import types
from app.search import semantic_search, _client_gemini
from app.audit import log_event
from app.graph_state import AssistantState


_INTENT_MODEL = "gemini-3.1-flash-lite"

INTENT_PROMPT = """Ты — классификатор запросов корпоративного ассистента.
Определи, что хочет пользователь:
- "question" — спрашивает информацию, просит объяснить, задаёт вопрос
  (даже если в вопросе есть слова «создать», «сделать» — это всё равно вопрос).
- "action" — просит ВЫПОЛНИТЬ действие: создать задачу, завести заявку.

Ответь РОВНО одним словом: question или action.
Без пояснений, без кавычек, без точки.

Запрос пользователя: {question}"""

def security_node(state: AssistantState):
    """
    Узел security: проверяет ЗАПРОС пользователя на признаки prompt injection.
    Это первый рубеж defense-in-depth — ловим атаку на входе, до всего остального.
    Само решение "блокировать или пропустить" принимает развилка route_after_security.
    """
    question = state["question"]
    is_injection = looks_like_injection(question)

    if is_injection:
        # Попытка инъекции — это security-событие, безопасник должен его видеть
        log_event("injection_in_query", state["user"]["user_id"],
                  {"question_len": len(question)})

    return {"injection_in_query": is_injection}

def route_after_security(state: AssistantState) -> str:
    """
    Развилка после проверки безопасности.
    Инъекция в запросе → блокируем (узел-отказ). Чисто → идём дальше, к intent.
    """
    if state["injection_in_query"]:
        return "blocked_step"      # → узел-отказ
    return "intent_step"           # → обычный путь

def blocked_node(state: AssistantState):
    """
    Узел-отказ: запрос заблокирован из-за признаков инъекции.
    Тупиковая ветка — дальше граф не идёт, сразу к концу.
    """
    return {
        "answer": "Запрос отклонён: он содержит признаки небезопасной инструкции.",
        "sources": [],
    }

def identity_node(state: AssistantState):
    """
    Узел identity: по username достаёт профиль пользователя.
    Раньше это была строка: user = get_user(req.username)
    """
    user = get_user(state["username"])   # достаём username из рюкзака
    return {"user": user}                # кладём user обратно в рюкзак

def intent_node(state: AssistantState):
    """
    Узел intent: определяет, вопрос это или действие, с помощью LLM.
    Модель — лёгкая Gemini Flash-Lite (быстрая и дешёвая, для классификации).
    Возвращает СТРОГО "question" или "action".
    """
    question = state["question"]
    prompt = INTENT_PROMPT.format(question=question)

    try:
        # Вызываем генеративную Gemini (не эмбеддинги!) как классификатор
        response = _client_gemini.models.generate_content(
            model=_INTENT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                # Отключаем "размышления": классификатору они не нужны,
                # так быстрее и дешевле, плюс уходит warning про thought parts
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        # Защитная нормализация: убираем пробелы/переносы и приводим к нижнему регистру
        raw = (response.text or "").strip().lower()
    except Exception as e:
        # Сеть/API упали — не роняем весь граф, тихо откатываемся к вопросу
        log_event("intent_llm_error", state["user"]["user_id"],
                  {"error_type": type(e).__name__})
        return {"intent": "question"}

    # Fallback: если модель вернула что-то за пределами двух допустимых значений —
    # не гадаем, откатываемся к безопасному "question" и логируем это
    if raw not in ("question", "action"):
        log_event("intent_unexpected_output", state["user"]["user_id"],
                  {"raw_output": raw})
        return {"intent": "question"}

    return {"intent": raw}


def permission_node(state: AssistantState):
    """
    Узел permission: фильтрует документы по роли пользователя.
    Раньше: allowed_docs = filter_documents_by_role(DOCUMENTS, user["role"])
    """
    role = state["user"]["role"]         # user положил предыдущий узел
    allowed = filter_documents_by_role(DOCUMENTS, role)
    return {"allowed_docs": allowed}     # кладём результат в рюкзак


def search_node(state: AssistantState):
    """
    Узел search (RAG): ищет документы по смыслу среди разрешённых
    и проверяет, нет ли в них признаков prompt injection.
    """
    found = semantic_search(state["question"], state["allowed_docs"])

    # проверка на "команды для бота" внутри документов
    security_flag = any(looks_like_injection(d["text"]) for d in found)
    if security_flag:
        log_event("security_flag", state["user"]["user_id"],
                  {"reason": "possible_prompt_injection"})

    # кладём в рюкзак сразу два поля
    return {"found": found, "security_flag": security_flag}


def answer_node(state: AssistantState):
    """
    Узел answer: формирует финальный ответ из лучшего найденного документа.
    Важно: сюда попадаем ТОЛЬКО когда что-то найдено.
    """
    best = state["found"][0]
    log_event("answer_given", state["user"]["user_id"],
              {"source": best["source"]})

    return {
        "answer": best["text"],
        "sources": [best["source"]],
    }


def route_after_search(state: AssistantState) -> str:
    """
    Функция-развилка: смотрит в рюкзак и решает, КУДА идти после поиска.
    Возвращает ИМЯ следующего узла (строку), а не данные.
    """
    if not state["found"]:          # ничего не нашли
        return "no_answer_step"     # → узел-отказ
    return "answer_step"            # → узел-ответ


def no_answer_node(state: AssistantState):
    """
    Узел-отказ: ничего не нашли — честно об этом говорим.
    Раньше это была ветка 'if not found' внутри /ask.
    """
    log_event("no_source_answer", state["user"]["user_id"], {})
    return {
        "answer": "В доступных мне документах нет ответа на этот вопрос.",
        "sources": [],
    }


def route_after_intent(state: AssistantState) -> str:
    """
    Развилка по intent: вопрос идёт в ветку поиска, действие — в ветку действий.
    Читает поле intent, которое положил intent_node.
    """
    if state["intent"] == "action":
        return "action_step"        # → ветка действий (пока заглушка)
    return "permission_step"        # → ветка вопросов


def action_node(state: AssistantState):
    """
    Узел действия: проверяет право на создание, затем ставит паузу на подтверждение.
    interrupt() замораживает граф и ждёт решения человека.
    """
    role = state["user"]["role"]

    # ── Проверка прав ДО паузы (это чтение, безопасно повторяется при возобновлении) ──
    if not role_can_do_action(role, "create_task"):
        log_event("action_denied", state["user"]["user_id"],
                  {"action": "create_task", "reason": "role_not_allowed"})
        return {
            "answer": "У вашей роли нет прав на создание задач.",
            "sources": [],
        }

    task_title = state["question"]

    # ⏸ ПАУЗА: показываем человеку, что собираемся сделать, и ждём решения.
    decision = interrupt({
        "type": "approval_request",
        "message": "Подтвердите создание задачи",
        "task_title": task_title,
    })

    # --- Код НИЖЕ выполнится только ПОСЛЕ решения человека (важное — тут) ---
    if decision == "approve":
        log_event("task_approved", state["user"]["user_id"], {"title": task_title[:100]})
        return {
            "answer": f"Готово. Задача создана после подтверждения: «{task_title}».",
            "sources": [],
        }
    else:
        log_event("task_rejected", state["user"]["user_id"], {"title": task_title[:100]})
        return {
            "answer": f"Действие отклонено. Задача «{task_title}» не создана.",
            "sources": [],
        }