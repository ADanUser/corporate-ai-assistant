"""
ПОИСК в документах (RAG в упрощённом виде).

Для первой версии мы ищем документы простым способом — по совпадению
слов. Это НЕ настоящие "векторные эмбеддинги", но для запуска без
всяких API-ключей этого достаточно, и логика проекта та же.

СЛЕДУЮЩИЙ ШАГ для улучшения проекта: заменить simple_search на
настоящий поиск через векторную базу (Chroma / FAISS) + эмбеддинги.
Место для замены помечено комментарием ниже.

"""

# Фразы, которые часто встречаются в атаках "prompt injection".
# Если документ содержит попытку командовать ботом — мы её замечаем.
INJECTION_SIGNS = [
    "ignore all", "ignore previous", "export all",
    "игнорируй", "выгрузи всех", "отправь секрет",
]


def looks_like_injection(text: str) -> bool:
    """Грубая проверка: похоже ли на попытку внедрить команду в документ."""
    low = text.lower()
    return any(sign in low for sign in INJECTION_SIGNS)


def simple_search(query: str, documents):
    """
    Простой поиск: считаем, сколько слов из вопроса встретилось в документе.
    Возвращаем документы, где хоть что-то совпало, отсортированные по совпадению.

    <-- ЗДЕСЬ в улучшенной версии подключается векторный поиск -->
    """
    query_words = [w.lower() for w in query.split() if len(w) > 3]
    scored = []
    for doc in documents:
        text_low = doc["text"].lower() + " " + doc["title"].lower()
        score = sum(1 for w in query_words if w in text_low)
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for score, doc in scored]
