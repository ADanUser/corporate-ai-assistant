"""
Tool registry — реестр инструментов ассистента.

Инструмент (tool) — это одно контролируемое действие: создать задачу,
пересказать документ. Не «доступ к системе», а конкретная операция
с описанными правилами.

Зачем реестр: что бы у инструмента была одна карточка со всеми полями. Добавление нового
инструмента — заполнение анкеты, а не археология по коду.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolCard:
    """
    Паспорт инструмента. frozen=True — карточку нельзя изменить после
    создания: правила безопасности не должны меняться на лету из кода.

    Поля намеренно все обязательные (нет значений по умолчанию). Автор
    нового инструмента ФИЗИЧЕСКИ не может забыть указать риск или роли —
    Python не даст создать карточку, упадёт на старте приложения.
    Это лучше, чем тихая дыра в проде.
    """
    name: str              # техническое имя: create_task
    title: str             # человеческое имя для текстов: «создание задач»
    description: str       # что делает — пойдёт в карточку approval
    allowed_roles: list    # кто может вызывать
    risk_level: str        # low | medium | high | critical
    effects: str           # что произойдёт после выполнения
    is_write: bool         # меняет ли что-то во внешнем мире


# ── Порог approval ──
# Действия с риском из этого набора не выполняются без человека.
# Порог лежит данными рядом с карточками: правило видно, а не спрятано
# в условии где-то в узле графа.
APPROVAL_REQUIRED_LEVELS = {"high", "critical"}


TOOL_REGISTRY = {
    "create_task": ToolCard(
        name="create_task",
        title="создание задач",
        description="Создаёт задачу в трекере по описанию сотрудника.",
        allowed_roles=["Employee", "Manager", "Admin"],
        risk_level="high",          # пишет во внешнюю систему → нужен человек
        effects="Будет создана задача в трекере. Отмена — вручную.",
        is_write=True,
    ),
    "check_vacation_balance": ToolCard(
        name="check_vacation_balance",
        title="проверка остатка отпуска",
        description="Показывает, сколько дней отпуска осталось у сотрудника.",
        allowed_roles=["Employee", "Manager", "Admin"],
        risk_level="low",           # только чтение своих данных → без approval
        effects="Ничего не меняется, возвращается число дней.",
        is_write=False,
    ),
}


def get_tool(name: str):
    """
    Возвращает карточку инструмента или None, если такого нет.
    """
    return TOOL_REGISTRY.get(name)


def tool_allows_role(tool: ToolCard, role: str) -> bool:
    """Разрешён ли инструмент этой роли."""
    return role in tool.allowed_roles


def tool_needs_approval(tool: ToolCard) -> bool:
    """
    Нужен ли человек перед выполнением.

    Решение выводится ИЗ УРОВНЯ РИСКА, а не пишется руками для каждого
    инструмента. Поэтому нельзя случайно завести опасный инструмент
    без approval: достаточно честно указать риск.
    """
    return tool.risk_level in APPROVAL_REQUIRED_LEVELS


def describe_tools_for_prompt() -> str:
    """
    Собирает список инструментов для промпта маршрутизатора.

    Источник один — реестр. Добавили карточку в TOOL_REGISTRY — модель
    сразу узнала о новом инструменте. Если бы список жил в промпте
    строкой, он бы неизбежно разошёлся с реальностью.
    """
    lines = []
    for tool in TOOL_REGISTRY.values():
        lines.append(f"- {tool.name}: {tool.description}")
    return "\n".join(lines)


# ── Реализации инструментов (моки) 
def execute_check_vacation_balance(user: dict) -> str:
    """Мок: остаток отпуска. В проде — запрос к HR-системе."""
    return (
        f"Остаток отпуска сотрудника {user['user_id']}: 12 дней из 28.\n"
        "Данные предоставлены HR-системой (демо-режим)."
    )