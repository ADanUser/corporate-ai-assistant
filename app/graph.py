from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from app.graph_state import AssistantState
from app.nodes import (
    identity_node,
    permission_node,
    search_node,
    answer_node,
    no_answer_node,          
    route_after_search,      # функция-развилка
    intent_node,  
    action_node,          
    route_after_intent,
)

builder = StateGraph(AssistantState)

# Узлы
builder.add_node("identity_step", identity_node)
builder.add_node("intent_step", intent_node)
builder.add_node("permission_step", permission_node)
builder.add_node("search_step", search_node)
builder.add_node("answer_step", answer_node)
builder.add_node("no_answer_step", no_answer_node)  
builder.add_node("action_step", action_node) 

# Рёбра
builder.add_edge(START, "identity_step")
builder.add_edge("identity_step", "intent_step")

# Развилка по intent: вопрос → permission, действие → action
builder.add_conditional_edges(
    "intent_step",
    route_after_intent,
    {
        "permission_step": "permission_step",
        "action_step": "action_step",
    },
)

# Ветка вопросов — БЕЗ ИЗМЕНЕНИЙ (как у тебя уже работает)
builder.add_edge("permission_step", "search_step")
builder.add_conditional_edges(
    "search_step",
    route_after_search,
    {
        "answer_step": "answer_step",
        "no_answer_step": "no_answer_step",
    },
)
builder.add_edge("answer_step", END)
builder.add_edge("no_answer_step", END)

# Ветка действий (пока заглушка) → конец
builder.add_edge("action_step", END)

checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    from langgraph.types import Command

    # thread_id — "имя сохранёнки". Один и тот же id = продолжаем тот же граф.
    config = {"configurable": {"thread_id": "demo-1"}}

    # ── ШАГ 1: запускаем действие. Граф дойдёт до interrupt и ЗАМРЁТ ──
    result = graph.invoke(
        {"username": "bob", "question": "создай задачу добавить логирование"},
        config=config,
    )
    print("ПОСЛЕ ПЕРВОГО ВЫЗОВА (граф на паузе):")

    # Информацию о паузе достаём из состояния графа
    snapshot = graph.get_state(config)
    print("  Граф ждёт на узлах:", snapshot.next)

    # Карточка approval лежит внутри задачи: tasks[0].interrupts[0].value
    card = snapshot.tasks[0].interrupts[0].value
    print("  Сообщение:", card["message"])
    print("  Задача:", card["task_title"])

    # ── ШАГ 2: человек подтверждает. Возобновляем ТОТ ЖЕ thread_id ──
    final = graph.invoke(
        Command(resume="approve"),   # передаём решение человека
        config=config,               # тот же config = то же "имя сохранёнки"
    )
    print("\nПОСЛЕ ВОЗОБНОВЛЕНИЯ (approve):")
    print("  ОТВЕТ:", final["answer"])