from langgraph.graph import StateGraph, START, END

from app.graph_state import AssistantState
from app.nodes import (
    identity_node,
    permission_node,
    search_node,
    answer_node,
    no_answer_node,          
    route_after_search,      # функция-развилка
)

builder = StateGraph(AssistantState)

# Узлы
builder.add_node("identity_step", identity_node)
builder.add_node("permission_step", permission_node)
builder.add_node("search_step", search_node)
builder.add_node("answer_step", answer_node)
builder.add_node("no_answer_step", no_answer_node)   

# Рёбра
builder.add_edge(START, "identity_step")
builder.add_edge("identity_step", "permission_step")
builder.add_edge("permission_step", "search_step")

# РАЗВИЛКА:
builder.add_conditional_edges(
    "search_step",
    route_after_search,
    {
        "answer_step": "answer_step",
        "no_answer_step": "no_answer_step",
    },
)

# Обе ветки развилки ведут в конец графа
builder.add_edge("answer_step", END)
builder.add_edge("no_answer_step", END)

graph = builder.compile()


# ── Временный пробный запуск ──
if __name__ == "__main__":
    # Вопрос, на который ОТВЕТ ЕСТЬ
    r1 = graph.invoke({
        "username": "alice",
        "question": "как оформить командировку?",
    })
    print("СЦЕНАРИЙ 1 (ответ есть):")
    print("  ОТВЕТ:", r1["answer"][:60], "...")
    print("  ИСТОЧНИКИ:", r1["sources"])

    # Вопрос, на который ответа НЕТ (проверяем ветку отказа)
    r2 = graph.invoke({
        "username": "alice",
        "question": "какая зарплата у senior разработчика?",
    })
    print("СЦЕНАРИЙ 2 (ответа нет):")
    print("  ОТВЕТ:", r2["answer"])
    print("  ИСТОЧНИКИ:", r2["sources"])

    # ── Нарисовать граф в виде схемы (Mermaid) ──
    print("\n--- СХЕМА ГРАФА (Mermaid) ---")
    print(graph.get_graph().draw_mermaid())