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


# ── Права на ДЕЙСТВИЯ (кто какое действие может выполнять) ──
# Это зачаток tool registry: правила действий лежат данными в одном месте,
# а не размазаны if-ами по main.py.
ACTION_PERMISSIONS = {
    "create_task": ["Employee", "Manager", "Admin"],  # черновик может предложить любой
    "approve":     ["Manager", "Admin"],              # подтверждать — только старше
}


def role_can_do_action(user_role: str, action_name: str) -> bool:
    """
    Проверяет, разрешено ли роли выполнять действие.
    deny-by-default: если действия нет в карте — запрещено.
    """
    allowed_roles = ACTION_PERMISSIONS.get(action_name, [])
    return user_role in allowed_roles