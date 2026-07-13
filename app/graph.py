# app/graph.py
from langgraph.graph import StateGraph, START, END

from app.graph_state import AssistantState
from app.nodes import (
    identity_node,
    permission_node,
    search_node,
    answer_node,
)

# 1. Создаём граф и говорим, какой у него "рюкзак" (state)
builder = StateGraph(AssistantState)

# 2. Добавляем узлы
builder.add_node("identity_step", identity_node)
builder.add_node("permission_step", permission_node)
builder.add_node("search_step", search_node)
builder.add_node("answer_step", answer_node)

# 3. Соединяем рёбрами 
builder.add_edge(START, "identity_step")
builder.add_edge("identity_step", "permission_step")
builder.add_edge("permission_step", "search_step")
builder.add_edge("search_step", "answer_step")
builder.add_edge("answer_step", END)        # последний узел → выход графа

# 4. Компилируем — превращаем чертёж в готовый к запуску граф
graph = builder.compile()

if __name__ == "__main__":
    result = graph.invoke({
        "username": "alice",
        "question": "как оформить командировку?",
    })
    print("ОТВЕТ:", result["answer"])
    print("ИСТОЧНИКИ:", result["sources"])