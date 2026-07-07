# Какие действия считаем рискованными и требующими подтверждения человека
RISKY_ACTIONS = {"create_task"}


def filter_documents_by_role(documents, user_role):
    """
    Оставляет только те документы, которые разрешены роли пользователя.
    Employee не увидит зарплатные вилки, потому что их здесь просто
    не окажется в списке.
    """
    allowed = []
    for doc in documents:
        if user_role in doc["allowed_roles"]:
            allowed.append(doc)
    return allowed


def action_needs_approval(action_name: str) -> bool:
    """Проверяет, требует ли действие подтверждения человека."""
    return action_name in RISKY_ACTIONS
