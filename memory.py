"""Единая папка памяти Капри: дневник, идеи, знания, прочее."""
import os

BASE = os.path.dirname(os.path.abspath(__file__))
MEM_DIR = os.path.join(BASE, "memory")
MEM_FILE = os.path.join(MEM_DIR, "memories.md")
IDEAS_FILE = os.path.join(MEM_DIR, "ideas.md")
DONE_FILE = os.path.join(MEM_DIR, "done.md")
KNOWLEDGE_DIR = os.path.join(MEM_DIR, "knowledge")
MISC_DIR = os.path.join(MEM_DIR, "misc")


def ensure_dirs():
    """Создать папки и пустые файлы, если их нет."""
    for d in (MEM_DIR, KNOWLEDGE_DIR, MISC_DIR):
        os.makedirs(d, exist_ok=True)
    for f in (MEM_FILE, IDEAS_FILE, DONE_FILE):
        if not os.path.exists(f):
            open(f, "w", encoding="utf-8").close()


def get_all_mem_files():
    """Все .md файлы в папке памяти (дневник + база знаний + прочее)."""
    files = [MEM_FILE]
    for sub in (KNOWLEDGE_DIR, MISC_DIR):
        if os.path.exists(sub):
            for f in sorted(os.listdir(sub)):
                if f.endswith(".md"):
                    files.append(os.path.join(sub, f))
    return files

SCRATCHPAD_FILE = os.path.join(MISC_DIR, "scratchpad.md")