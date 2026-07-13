# app/graph_state.py
from typing import TypedDict


class AssistantState(TypedDict):
    """
    Рюкзак данных, который путешествует по всему графу.
    Каждый узел достаёт нужные поля и кладёт свои результаты.
    """
    # ── Пришло в запросе (есть с самого начала) ──
    username: str          # кто спрашивает: alice / bob / admin
    question: str          # сам вопрос пользователя

    # ── Рождается по ходу графа (узлы кладут сюда) ──
    user: dict             # профиль из identity (id, role, department)
    allowed_docs: list     # документы, разрешённые роли (из permission)
    found: list            # найденные по смыслу документы (из search)
    security_flag: bool    # похоже ли на prompt injection (из search)

    # ── Финальный результат ──
    answer: str            # текст ответа
    sources: list          # источники ответа