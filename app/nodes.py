# app/nodes.py
from app.identity import get_user
from app.data.documents import DOCUMENTS
from app.permissions import filter_documents_by_role
from app.retrieval import looks_like_injection
from app.search import semantic_search
from app.audit import log_event
from app.graph_state import AssistantState


def identity_node(state: AssistantState):
    """
    Узел identity: по username достаёт профиль пользователя.
    Раньше это была строка: user = get_user(req.username)
    """
    user = get_user(state["username"])   # достаём username из рюкзака
    return {"user": user}                # кладём user обратно в рюкзак


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