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
    security_node,           
    route_after_security,    
    blocked_node,            
    output_guard,            # выходной guard
    tool_router_node,        # выбор инструмента моделью
)

builder = StateGraph(AssistantState)

# Узлы
builder.add_node("identity_step", identity_node)
builder.add_node("security_step", security_node)
builder.add_node("blocked_step", blocked_node)
builder.add_node("output_guard", output_guard)
builder.add_node("intent_step", intent_node)
builder.add_node("permission_step", permission_node)
builder.add_node("search_step", search_node)
builder.add_node("answer_step", answer_node)
builder.add_node("no_answer_step", no_answer_node)  
builder.add_node("action_step", action_node) 
builder.add_node("tool_router_step", tool_router_node)

# Рёбра
builder.add_edge(START, "identity_step")
builder.add_edge("identity_step", "security_step")

# Развилка: инъекция → blocked, чисто → intent
builder.add_conditional_edges(
    "security_step",
    route_after_security,
    {
        "blocked_step": "blocked_step",
        "intent_step": "intent_step",
    },
)

builder.add_edge("blocked_step", "output_guard")

# Развилка по intent: вопрос → permission, действие → выбор инструмента
builder.add_conditional_edges(
    "intent_step",
    route_after_intent,
    {
        "permission_step": "permission_step",
        "tool_router_step": "tool_router_step",
    },
)

# Маршрутизатор выбрал инструмент → узел исполнения
builder.add_edge("tool_router_step", "action_step")

# Ветка вопросов
builder.add_edge("permission_step", "search_step")
builder.add_conditional_edges(
    "search_step",
    route_after_search,
    {
        "answer_step": "answer_step",
        "no_answer_step": "no_answer_step",
    },
)
builder.add_edge("answer_step", "output_guard")
builder.add_edge("no_answer_step", "output_guard")
builder.add_edge("output_guard", END)

# Ветка действий → конец
builder.add_edge("action_step", END)

checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    from langgraph.types import Command

    # thread_id — "имя сохранёнки". Один и тот же id = продолжаем тот же граф.
    config = {"configurable": {"thread_id": "demo-1"}}

    # ── ШАГ 1: запускаем действие. Граф дойдёт до interrupt и ЗАМРЁТ ──
    result = graph.invoke(
        {"username": "bob", "question": "создай задачу добавить логирование",
         "thread_id": "demo-1"},
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
        Command(resume={"decision": "approve", "approver": "admin"}),
        config=config,               # тот же config = то же "имя сохранёнки"
    )
    print("\nПОСЛЕ ВОЗОБНОВЛЕНИЯ (approve):")
    print("  ОТВЕТ:", final["answer"])