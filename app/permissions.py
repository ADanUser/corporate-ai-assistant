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


# ── Право на подтверждение чужих действий ──
# Approve — не инструмент, а решение о чужом инструменте, поэтому живёт
# здесь, а не в реестре tools.py.
ACTION_PERMISSIONS = {
    "approve": ["Manager", "Admin"],
}


def role_can_do_action(user_role: str, action_name: str) -> bool:
    """
    Проверяет, разрешено ли роли выполнять действие.
    deny-by-default: если действия нет в карте — запрещено.
    """
    allowed_roles = ACTION_PERMISSIONS.get(action_name, [])
    return user_role in allowed_roles

# ── Аварийный выключатель инструментов (kill switch) ──
# Инцидент: инструмент сломался или используется во вред. Админ выключает
# его здесь — код менять не нужно, остальные инструменты работают дальше.
# Это НЕ права доступа: выключенный инструмент недоступен всем, даже Admin.
DISABLED_ACTIONS = set()


def action_is_disabled(action_name: str) -> bool:
    """Проверяет, не отключён ли инструмент аварийно."""
    return action_name in DISABLED_ACTIONS


def disable_action(action_name: str):
    """Аварийно выключает инструмент."""
    DISABLED_ACTIONS.add(action_name)


def enable_action(action_name: str):
    """Возвращает инструмент в строй."""
    DISABLED_ACTIONS.discard(action_name)