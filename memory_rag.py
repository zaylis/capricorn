import os
import json
import urllib.request
import chromadb
from chromadb.config import Settings

BASE = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE, "memory", "chroma_db")
OLLAMA_URL = "http://127.0.0.1:11434/api/embeddings"

# Инициализация клиента ChromaDB
client = chromadb.PersistentClient(path=DB_DIR)
collection = client.get_or_create_collection(name="capri_memories")

def get_embedding(text):
    """Получаем вектор текста через Ollama"""
    try:
        req = urllib.request.Request(OLLAMA_URL, 
            data=json.dumps({"model": "nomic-embed-text", "prompt": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))["embedding"]
    except Exception as e:
        print(f"Ошибка эмбеддинга: {e}")
        return None

def add_memory(text, metadata=None):
    """Добавляет факт в память"""
    if not text.strip():
        return
    emb = get_embedding(text)
    if not emb:
        return
    
    # Используем хэш текста как ID, чтобы не дублировать записи
    mem_id = str(hash(text))
    try:
        collection.add(
            embeddings=[emb],
            documents=[text],
            metadatas=[metadata or {"source": "auto"}],
            ids=[mem_id]
        )
    except Exception:
        pass # Игнорируем дубликаты

def search_rag(query, n_results=3):
    """Ищет в памяти по смыслу"""
    emb = get_embedding(query)
    if not emb:
        return ""
    
    try:
        results = collection.query(
            query_embeddings=[emb],
            n_results=n_results
        )
        if results['documents'] and results['documents'][0]:
            return "\n---\n".join(results['documents'][0])
    except Exception as e:
        print(f"Ошибка поиска RAG: {e}")
    return ""

def sync_memories_from_file(mem_file_path):
    """Читает memories.md и загружает новые записи в базу"""
    if not os.path.exists(mem_file_path):
        return
    with open(mem_file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    # Разбиваем по маркерам ### (как у тебя в memories.md)
    blocks = content.split("###")
    for block in blocks:
        block = block.strip()
        if len(block) > 10: # Игнорируем слишком короткие огрызки
            add_memory(block, {"source": "memories.md"})