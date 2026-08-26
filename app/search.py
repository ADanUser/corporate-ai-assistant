"""
Умный поиск по смыслу (эмбеддинги Gemini + векторная база Chroma).

Эмбеддинги (превращение текста в "координаты смысла") считает модель
Google Gemini по API. Она хорошо понимает русский язык. Chroma хранит
эти векторы и быстро находит ближайшие по смыслу.
"""

import os

import chromadb
from google import genai
from google.genai import types
from dotenv import load_dotenv

from app.data.documents import DOCUMENTS

# Загружаем переменные из файла .env (там лежит ключ GEMINI_API_KEY)
load_dotenv()

_api_key = os.getenv("GEMINI_API_KEY")
if not _api_key:
    raise RuntimeError(
        "Не найден GEMINI_API_KEY. Создай файл .env и впиши в него строку:\n"
        "GEMINI_API_KEY=твой_ключ"
    )

# Клиент Gemini только для эмбеддингов. Наружу не экспортируется:
# генерация ответов живёт в app/llm.py.
_client_embed = genai.Client(api_key=_api_key)
_EMBED_MODEL = "gemini-embedding-001"

# Векторная база в памяти. cosine — расстояние по смыслу:
# около 0 = одинаковый смысл, около 1 = совсем разный.
_client_chroma = chromadb.Client()
_collection = _client_chroma.create_collection(
    "company_docs",
    metadata={"hnsw:space": "cosine"},
)

# Порог релевантности: если ближайший документ всё равно слишком далёк
# по смыслу (расстояние больше порога) — считаем "не найдено".
# Меньше число — строже, больше — мягче. Настраивается по реальным цифрам.
RELEVANCE_THRESHOLD = 0.40


def _embed(text: str, is_query: bool):
    """
    Превращает один текст в эмбеддинг через Gemini.
    is_query=True  -> это вопрос пользователя (task_type RETRIEVAL_QUERY)
    is_query=False -> это документ базы знаний (task_type RETRIEVAL_DOCUMENT)
    Разные task_type улучшают качество поиска — так советует Google.
    """
    task = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"
    result = _client_embed.models.embed_content(
        model=_EMBED_MODEL,
        contents=text,
        config=types.EmbedContentConfig(task_type=task),
    )
    return result.embeddings[0].values


def _build_index():
    """
    Считает эмбеддинг каждого документа и складывает векторы в Chroma.
    Вызывается один раз, из _ensure_index().
    """
    ids, embeddings, metadatas, texts = [], [], [], []
    for doc in DOCUMENTS:
        full_text = doc["title"] + ". " + doc["text"]
        ids.append(doc["id"])
        embeddings.append(_embed(full_text, is_query=False))
        metadatas.append({"doc_id": doc["id"]})
        texts.append(full_text)

    _collection.add(
        ids=ids,
        embeddings=embeddings,
        metadatas=metadatas,
        documents=texts,
    )


def semantic_search(query: str, allowed_docs):
    """
    Ищет документы по смыслу, но ТОЛЬКО среди разрешённых пользователю.
    allowed_docs уже отфильтрован по роли в permissions.py ДО этого вызова.
    """
    _ensure_index()
    allowed_ids = [doc["id"] for doc in allowed_docs]
    if not allowed_ids:
        return []

    # Эмбеддинг вопроса (как query) и поиск только среди разрешённых id
    query_embedding = _embed(query, is_query=True)
    results = _collection.query(
        query_embeddings=[query_embedding],
        n_results=len(allowed_ids),
        where={"doc_id": {"$in": allowed_ids}},
    )

    found_ids = results["ids"][0] if results["ids"] else []
    distances = results["distances"][0] if results["distances"] else []

    # Оставляем только достаточно близкие по смыслу (ближе порога)
    id_to_doc = {doc["id"]: doc for doc in DOCUMENTS}
    relevant = []
    for fid, dist in zip(found_ids, distances):
        if dist <= RELEVANCE_THRESHOLD:
            relevant.append(id_to_doc[fid])
    return relevant


# Индекс строится ЛЕНИВО, при первом поиске, а не при импорте модуля.
# Импорт не должен зависеть от доступности внешнего API: иначе сбой
# провайдера роняет всё приложение, включая ветки, не связанные с поиском.
_index_ready = False


def _ensure_index():
    """Строит индекс при первой необходимости. Повторные вызовы — no-op."""
    global _index_ready
    if not _index_ready:
        _build_index()
        _index_ready = True