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

# Ветка действий тоже проходит через выходной guard
builder.add_edge("action_step", "output_guard")

checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)
