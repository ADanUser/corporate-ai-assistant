from typing import TypedDict


class AssistantState(TypedDict):
    """
    Рюкзак данных, который путешествует по всему графу.
    Каждый узел достаёт нужные поля и кладёт свои результаты.
    """
    # ── Пришло в запросе (есть с самого начала) ──
    username: str          # кто спрашивает: alice / bob / admin
    question: str          # сам вопрос пользователя
    thread_id: str         # идентификатор диалога (для логов и поиска истории)

    # ── Рождается по ходу графа (узлы кладут сюда) ──
    user: dict             # профиль из identity (id, role, department)
    allowed_docs: list     # документы, разрешённые роли (из permission)
    found: list            # найденные по смыслу документы (из search)
    security_flag: bool    # похоже ли на prompt injection (из search)
    injection_in_query: bool   # инъекция в ЗАПРОСЕ пользователя (из security)
    intent: str            # "question" или "action" (кладёт intent_node)
    selected_tool: str     # имя инструмента, предложенное моделью (tool_router)

    # ── Финальный результат ──
    answer: str            # текст ответа
    sources: list          # источники ответа
    answer_type: str       # тип ответа (см. app/responses.py) — для логов и evals