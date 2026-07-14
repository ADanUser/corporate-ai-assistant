from langgraph.graph import StateGraph, START, END

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

graph = builder.compile()


# ── Временный пробный запуск ──
if __name__ == "__main__":
    rq = graph.invoke({
        "username": "alice",
        "question": "как оформить командировку?",
    })
    print("ВОПРОС →", rq["intent"], "|", rq["answer"][:50])

    # Запрос-ДЕЙСТВИЕ → должен пойти в ветку действий (заглушка)
    ra = graph.invoke({
        "username": "bob",
        "question": "создай задачу добавить логирование",
    })
    print("ДЕЙСТВИЕ →", ra["intent"], "|", ra["answer"])

    # ── Нарисовать граф в виде схемы (Mermaid) ──
    print("\n--- СХЕМА ГРАФА (Mermaid) ---")
    print(graph.get_graph().draw_mermaid())