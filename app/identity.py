# Три пользователя с разными ролями
USERS = {
    "alice": {"user_id": "alice", "role": "Employee", "department": "Engineering"},
    "bob":   {"user_id": "bob",   "role": "Manager",  "department": "Engineering"},
    "admin": {"user_id": "admin", "role": "Admin",    "department": "IT"},
}


def get_user(username: str):
    """Возвращает профиль пользователя или None, если его нет."""
    return USERS.get(username)
