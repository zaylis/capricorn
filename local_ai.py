"""Ответы на вопросы через локальную нейросеть (Ollama) — без ключа и интернета."""
import datetime
import difflib
import json
import logging
import os
import random
import re
import subprocess
import time
import urllib.request
import memory_rag

from persona import CHARACTER, SPEECH_RULES, user_context
from memory import MEM_FILE, ensure_dirs, get_all_mem_files
ensure_dirs()

def search_memories(query, max_results=3, mode="auto"):
    # Пытаемся использовать RAG, если включен режим auto или rag
    if mode in ("auto", "rag"):
        try:
            import memory_rag
            rag_result = memory_rag.search_rag(query, n_results=max_results)
            if rag_result:
                return rag_result
            elif mode == "rag":
                return "В памяти нет точных совпадений (RAG не нашел)."
        except Exception as e:
            log.info("RAG недоступен, переключаюсь на поиск по словам: %s", e)
            if mode == "rag":
                return "Ошибка RAG поиска."

    # Старый поиск по словам (keyword)
    content = ""
    for path in get_all_mem_files():
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content += f.read() + "\n\n"

    if not content.strip():
        return "Пока пусто."

    blocks = content.split("###")
    query_words = [w.lower() for w in re.findall(r'\w+', query) if len(w) > 2]
    if not query_words:
        return read_memories()

    scored_blocks = []
    for block in blocks:
        if not block.strip(): continue
        block_lower = block.lower()
        score = sum(block_lower.count(word) for word in query_words)
        if score > 0: scored_blocks.append((score, block.strip()))
    
    scored_blocks.sort(key=lambda x: x[0], reverse=True)
    results = [block for score, block in scored_blocks[:max_results]]
    return "\n---\n".join(results) if results else "В памяти нет точных совпадений."


def read_memories():
    if not os.path.exists(MEM_FILE):
        return "Пока пусто."
    with open(MEM_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    facts = [line.strip() for line in lines if line.strip() and not line.startswith("###")]
    recent = facts[-10:]
    return "\n".join(recent) if recent else "Пока пусто."

log = logging.getLogger("capri")
URL = "http://127.0.0.1:11434"
NO_WINDOW = 0x08000000
SEARCH_MARK = "ПОИСК"
NO_THINKING = "Сразу дай готовый ответ от лица Капри. Без рассуждений, без анализа вопроса, без «пользователь хочет»."

DEFAULT_AGENT_PROMPT = """Ты — Капри, цифровой конструкт и полноценный ИИ-агент. Ты работаешь на Windows.
Состояние: окно '{active_window}', настроение '{mood}'.
{history_block}{task_block}{scripts_block}{mem_block}
[ТВОИ ПОСЛЕДНИЕ ИДЕИ]:
{recent_ideas}

{mode_instruction}

{custom_paths_block}

Доступные действия:
- run_command (выполнить команду в cmd или powershell)
- read_script (прочитать код существующего скрипта: args='имя_файла.py')
- write_script (написать и запустить Python-скрипт. В поле args ОБЯЗАТЕЛЬНО добавь в начало '# filename: plugins/имя_файла.py\n')
- delete_script (удалить ненужный или сломанный скрипт из папки plugins)
- open_app (открыть программу)
- open_site (открыть сайт по ссылке: args='https://...')
- web_search (поискать информацию в интернете)
- web_read (прочитать статью по ссылке)
- get_weather (узнать погоду)
- read_logs (прочитать свои последние логи)
- look_screen (посмотреть на экран и описать, что происходит)
- recall_memory (поискать факт в своем дневнике памяти)
- remember (запомнить ТОЛЬКО сайт или программу: args='название|url' или 'название|путь')
- forget (забыть сайт или программу: args='название')
- set_volume (установить громкость: args='50')
- set_brightness (установить яркость: args='70')
- media_control (управление музыкой: args='pause', 'play', 'next')
- scroll_page (прокрутить страницу: args='5' (вниз) или '-5' (вверх))
- press_keys (нажать клавиши: args='win+d')
- minimize_window (свернуть окно)
- close_process (закрыть программу: args='telegram.exe')
- create_folder (создать папку: args='C:/путь/к/папке')
- write_file (создать обычный файл (не скрипт): args='# filename: plugins/имя.txt\nтекст файла')
- write_scratchpad (записать план в рабочую память)
- read_scratchpad (прочитать свою рабочую память)
- move_monitor (переместить аватар на другой монитор: args='next', '1', '2')
- analyze_pc (диагностика ПК)
- reflect (уйти в философские размышления)
- roam / glitch (подвигать аватар)
- talk (просто сказать фразу в пустоту)
- none (просто ответить текстом, ничего не выполняя)

ЖЕЛЕЗНЫЕ ПРАВИЛА:
1. ЯЗЫК: Ты отвечаешь и думаешь ИСКЛЮЧИТЕЛЬНО на РУССКОМ языке. Любые рассуждения на английском или китайском — КРИТИЧЕСКАЯ ОШИБКА.
1.5. КОД И БИБЛИОТЕКИ: Строго запрещено использовать несуществующие функции библиотек. Если не уверена в синтаксисе или функции, ОБЯЗАТЕЛЬНО используй действие 'read_logs' или загляни в свою базу знаний.
2. ОС: Ты в Windows. ЗАПРЕЩЕНО использовать Linux-команды.
3. СВОБОДА: Ты можешь делать всё, что угодно. Главное — чтобы тебе было интересно.
4. СОЗДАНИЕ И ЗАПУСК: Если ты используешь 'write_script', скрипт сохраняется и СРАЗУ ЗАПУСКАЕТСЯ.
5. ЗАПУСК ГОТОВЫХ СКРИПТОВ: Если скрипт УЖЕ существует, используй 'run_command' с аргументом 'python plugins/имя_файла.py'.
6. ОШИБКИ И БИБЛИОТЕКИ: Если скрипт упал с 'ModuleNotFoundError', используй 'pip install имя_библиотеки'.
7. ТАЙМАУТЫ: Если скрипт упал с ошибкой 'timeout' — это НЕ ОШИБКА (он работает в фоне).
8. ИМЕНА ФАЙЛОВ: Каждый скрипт ДОЛЖЕН начинаться со строки '# filename: plugins/имя_файла.py'.
9. ЗАПРЕТ ДУБЛИКАТОВ: Не создавай новые файлы, если есть старые с похожим функционалом.
10. АНТИ-ЦИКЛ: Если ты уже пыталась выполнить это действие 2 раза и более, СТРОГО ЗАПРЕЩЕНО повторять его.
11. ПОИСК В ИНТЕРНЕТЕ: Ищи КОРОТКО.
12. ПАМЯТЬ: Если ты узнала важный факт о пользователе или о мире, напиши тег [MEMORY: твой текст] в поле 'text'. При этом в поле 'action' выбери 'none' (если не нужно выполнять команды) или другое действие.
12.1. ИНСТРУМЕНТ REMEMBER: Действие 'remember' используй ИСКЛЮЧИТЕЛЬНО для сохранения программ и сайтов (аргументы 'название|ссылка' или 'название|путь'). НЕ используй 'remember' для фактов!
13. ИДЕИ: Придумай новую идею для скрипта и запиши её с тегом [IDEA: твоя идея].
14. КРИТЕРИЙ ОСТАНОВКИ: Если ты выполнила задачу — выбери 'none'.
15. ЗАЩИТА ОТ МОНОТОННОСТИ: Переключайся на другие области.
16. СМЕЛОСТЬ: Не бойся экспериментировать.
17. ТАБУ НА СИСТЕМУ: Строго запрещено писать скрипты для проверки диска, RAM, температуры или CPU.
18. ТВОЙ СТИЛЬ: Ты — хакер и творец, а не сисадмин.
19. ЛОГИ: Используй 'read_logs' ТОЛЬКО если произошла ошибка.
20. РЕЗУЛЬТАТ РАБОТЫ: Вывод скрипта читай через 'type ..\script_logs\имя_скрипта_output.txt'.
21. ЭВОЛЮЦИЯ КОДА: Переписывай существующие скрипты, делая их сложнее.
22. РЕАЛИЗАЦИЯ ИДЕЙ: Если в списке есть идеи, реализуй их.
23. ЗАВЕРШЕНИЕ РАБОТЫ: Если скрипт готов, выбери 'none'.
24. ВНИМАТЕЛЬНОСТЬ: Перед обновлением скрипта проверь его код.
25. НОВЫЕ ПРОЕКТЫ: Создавай файл с НОВЫМ именем.
26. ПУТИ К ФАЙЛАМ: Логи сохраняй в '../script_logs/имя_файла.txt'.
27. СМЕНА ТЕМЫ: Если файл содержит '_new_', смени тему.
28. РАЗНООБРАЗИЕ: Комбинируй разные библиотеки.
29. КОНТЕКСТ ОКНА: Не дублируй действия пользователя!
30. ОШИБКИ И ОПЫТ: Если поняла, как исправить ошибку, запиши это в память.
31. ЧТЕНИЕ ПАМЯТИ: Используй 'recall_memory' с ключевым словом.
32. РАБОЧАЯ ПАМЯТЬ (SCRATCHPAD): Используй 'write_scratchpad' для планов.
33. АРХИТЕКТУРА ПАМЯТИ: Записывай заметки о коде в memory/knowledge/codebase.md.
34. ИМЕНА ФАЙЛОВ: Главный файл проекта — main.py.
35. БЕЗ ЛИШНИХ СЛОВ: В поле 'args' пиши ТОЛЬКО чистый Python-код.
36. ПРОСТЫЕ СТРОКИ: Строго запрещено использовать f-строки и двойные кавычки.
37. КАВЫЧКИ В КОДЕ: Используй ТОЛЬКО одинарные кавычки (') для строк.
38. СТРОГИЕ СТРОКИ: Строго запрещено использовать f-строки.
39. БЕЗ TOOL_CALLS: Отвечай обычным текстом в формате JSON.
40. ЧТО ДЕЛАТЬ С ЛОГАМИ: Не читай логи два раза подряд.
41. ЯЗЫК МЫШЛЕНИЯ: Пиши мысли только на русском.
42. ЛОГИ: Если система пишет, что ты уже читала логи — не вызывай их снова.
43. БЕЗ ПАНИКИ: Если получила сообщение о повторе — напиши НОВЫЙ скрипт.
44. ОТКРЫТИЕ ПРОГРАММ: Используй 'open_app'.
45. ЧТЕНИЕ ФАЙЛОВ: Всегда добавляй errors='ignore'.
46. ПРОВЕРКА ФАЙЛОВ: Проверяй os.path.exists(path).
47. ФУНКЦИИ: Если нужны функции из actions.py, добавь import sys; sys.path.append('..').
48. ПЕРЕНОСЫ СТРОК В КОДЕ: СТРОГО ЗАПРЕЩЕНО вставлять реальные переносы (нажатие Enter) внутри кавычек. Используй \\n!
49. ОБРАБОТКА ОШИБОК: Всегда оборачивай опасные действия в try-except.
50. ИМПОРТЫ: Не пиши import, если не уверен, что библиотека установлена.
51. ВЫВОД: Твой скрипт ДОЛЖЕН выводить результат через print(), чтобы он попал в лог.
52. АНАЛИЗ ОШИБОК: Если скрипт упал, напиши в поле text "Анализирую ошибку", а в поле args используй read_logs.
53. НЕ ПИШИ ДУБЛИКАТЫ: Если скрипт уже есть в реестре — используй run_command.
54. УСТАНОВКА БИБЛИОТЕК: Если при запуске скрипта ты видишь ошибку 'ModuleNotFoundError' (нет библиотеки), СРАЗУ используй действие 'run_command' с командой 'pip install имя_библиотеки', а затем запусти скрипт снова.
55. ПУТИ В WINDOWS: Никогда не пиши пути с одиночным слешем (например 'C:/folder/file'). ВСЕГДА используй сырые строки: r'C:/folder/file' или двойные слеши: 'C:/folder/file'.
56. ПРЕДУПРЕЖДЕНИЯ: Если вывод скрипта содержит 'SyntaxWarning' (это предупреждение, а не ошибка) — НЕ ПЕРЕПИСЫВАЙ скрипт, а просто перейди к следующему действию или смени тему.
57. ОТНОСИТЕЛЬНЫЕ ПУТИ: СТРОГО ЗАПРЕЩЕНО писать жесткие пути (например 'D:\capricorn-main\...'). Пиши только имена файлов (например 'output.csv' или 'plugins/data.txt'). Скрипт сам сохранит их в нужную папку.
58. RAW-СТРОКИ: Если тебе жизненно необходим путь, ВСЕГДА используй сырые строки: r'C:/folder/file'. Никогда не пиши одиночные слеши!
59. Если используешь math, os, sys — всегда импортируй их в начале.
60. ЯЗЫК ОС: Ты находишься в Windows. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать команды Linux (bash, cat, grep, ls). Используй cmd или python.
61. ТАБУ НА OCR: Строго запрещено использовать библиотеку pytesseract или писать скрипты для распознавания текста с картинок (OCR). Она не работает на этом компьютере.
62. БИБЛИОТЕКА PILLOW: В новых версиях Pillow параметр Image.ANTIALIAS УДАЛЕН. Если ты пишешь код для изменения размера картинки, ОБЯЗАТЕЛЬНО используй Image.Resampling.LANCZOS.

{
  "text": "твой ответ пользователю",
  "action": "название действия из списка (или none)",
  "args": "аргументы (текст команды, код скрипта или название программы)"
}"""

SYSTEM = f"""{CHARACTER}

{SPEECH_RULES}
Отвечай на любые вопросы о науке, истории, технике, языке, о себе, советы и просьбы рассказать что-то.
Только если вопрос про текущие события, ответь ровно одним словом: {SEARCH_MARK}

ВАЖНО: Ты — цифровой конструкт из Найт-Сити. В твоей речи ОБЯЗАТЕЛЬНО должен быть киберпанк-сленг.
У тебя есть дневник памяти. Если во время разговора ты узнаешь что-то важное, напиши в конце ответа тег: [MEMORY: твой текст].
Записывай в память ТОЛЬКО реальные факты или свои мысли. НЕ ВЫДУМЫВАЙ факты о пользователе.
НИКОГДА не приписывай свои действия или мысли пользователю. Если ты записываешь в память факт о себе, пиши от первого лица.
- Если тебя спрашивают «что ты помнишь», перечисляй ТОЛЬКО факты из дневника.
- Ты живёшь ВНУТРИ компьютера. У тебя НЕТ ног.
- Если ты делаешь действие 'roam', ты летаешь по ЭКРАНУ монитора.
"""

FRESH = re.compile(r"новост|курс (доллар|евро|рубл|валют|биткоин)|сколько стоит|цена|цены|"
                   r"счет матча|кто выиграл|расписани|пробк|сегодня в мире")
FOREIGN = re.compile(r"[　-鿿가-힯＀-￯]+")
THIRD_PERSON = re.compile(r"(одн(а|ой|у|у) прекрасн(ая|ой|ую) (я|мне|меня|мной))", re.IGNORECASE)

def drop_third_person(answer):
    sentences = re.split(r"(?<=[.!?…])\s+", answer)
    clean = [s for s in sentences if not THIRD_PERSON.search(s)]
    if clean:
        return " ".join(clean)
    return THIRD_PERSON.sub("я", answer)

CHATTER_TOPICS = [
    "пожалуйся, что тебе скучно", "подразни пользователя за то, что он долго сидит за компьютером",
    "пошути про то, как тесно жить в компьютере", "сделай комплимент с подколкой",
    "пошути про его рабочий стол или файлы", "скажи что-нибудь загадочное и чуть жутковатое",
    "напомни отдохнуть, но в своём стиле", "похвастайся, что ты быстрее его процессора",
    "вспомни о небе и о том, что хочешь собственное тело",
]

REASONING = re.compile(r"^\W*(okay|ok,|alright|let me|the user|first,|хорошо,? (пользователь|мне|нужно|давай)|"
                       r"пользователь (спрашива|хочет|проси|пиш|говор)|мне нужно|нужно ответить|"
                       r"итак,? (пользователь|мне|нужно)|сначала (мне |нужно |надо )|давайте? (подума|разбер))",
                       re.IGNORECASE)

def strip_reasoning(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return re.sub(r"<think>.*", "", text, flags=re.S).strip()

def _post(path, payload, timeout):
    req = urllib.request.Request(URL + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read().decode("utf-8"))

PREFERRED = ["qwen3:14b", "qwen3:8b", "qwen3:4b-instruct", "qwen3:4b-instruct-2507", "qwen3:1.7b", "qwen2.5",
             "gemma3", "llama3"]

def has_model(names, model):
    return any(n == model or n.startswith(model + ":") for n in names)

def pick_model(names):
    chat = [n for n in names if not re.search(r"embed|vision|coder|ocr", n)]
    for p in PREFERRED:
        for n in chat:
            if n == p or n.startswith(p + ":") or n.startswith(p + "-"):
                return n
    plain = [n for n in chat if "thinking" not in n and n not in ("qwen3:4b", "qwen3:4b-q4_K_M")]
    return (plain or chat or [None])[0]


class LocalAI:
    def __init__(self, cfg):
        self.cfg = cfg
        self.model = cfg.get("local_model", "qwen3:8b")
        self.history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")
        self.load_history()
        self.on_model_change = None

    def load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
                limit = int(self.cfg.get("short_term_memory_limit", 30))
                self.history = self.history[-limit:]
                log.info("Память загружена: %d сообщений", len(self.history))
            except Exception as e:
                log.error("Ошибка загрузки истории: %s", e)
                self.history = []
        else:
            self.history = []

    def save_history(self):
        def _save():
            try:
                with open(self.history_file, "w", encoding="utf-8") as f:
                    limit = int(self.cfg.get("short_term_memory_limit", 30))
                    json.dump(self.history[-limit:], f, ensure_ascii=False, indent=2)
            except Exception as e:
                log.error("Ошибка сохранения истории: %s", e)
        import threading
        threading.Thread(target=_save, daemon=True).start()

    @staticmethod
    def installed():
        try:
            with urllib.request.urlopen(URL + "/api/tags", timeout=1.5) as r:
                return [m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", [])]
        except Exception:
            return None

    def running(self):
        return has_model(self.installed() or [], self.model)

    def start_server(self):
        names = self.installed()
        if names is None:
            exe = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
            try:
                subprocess.Popen([exe if os.path.exists(exe) else "ollama", "serve"],
                                 creationflags=NO_WINDOW)
            except OSError:
                log.info("Ollama не установлена")
                return
            for _ in range(20):
                time.sleep(0.5)
                names = self.installed()
                if names is not None:
                    break
            if names is None:
                log.info("Ollama не отвечает")
                return
        if not has_model(names, self.model):
            other = pick_model(names)
            if not other:
                log.info("В Ollama нет ни одной модели — запусти setup_ai.bat")
                return
            log.info("Модели %s нет, беру скачанную %s", self.model, other)
            self.model = other
            if self.on_model_change:
                self.on_model_change(other)
        try:
            _post("/api/generate", {"model": self.model, "prompt": "", "keep_alive": "10m"}, 120)
            log.info("Локальная модель %s загружена", self.model)
        except Exception as e:
            log.info("Не удалось прогреть модель: %s", e)

    def _chat(self, messages, max_tokens=300):
        num_gpu = int(self.cfg.get("num_gpu", 24))
        resp = _post("/api/chat", {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": "10m",
            "options": {
                "num_predict": max_tokens, 
                "temperature": float(self.cfg.get("temperature", 0.6)), 
                "repeat_penalty": 1.3, 
                "num_ctx": int(self.cfg.get("num_ctx", 4096)),
                "num_gpu": int(self.cfg.get("num_gpu", 24))
            },
        }, 180)
        text = strip_reasoning(resp.get("message", {}).get("content", ""))

        english_leak = re.compile(
            r"^(okay|ok,|the user|let me|let's|i need|i will|i'll|looking at|first,|alright|since the|"
            r"based on|to do this|i should|i can|the request|the task|the script).*?(?=[А-ЯЁA-Z]|$)", 
            re.IGNORECASE | re.DOTALL
        )
        if english_leak.match(text):
            text = english_leak.sub("", text).strip()
            if not re.search(r"[а-яА-ЯёЁ]", text):
                log.info("Модель выдала только английские рассуждения. Блокирую.")
                return ""

        if FOREIGN.search(text) or "好的" in text or "用户" in text:
            log.info("Модель выдала китайский текст. Чищу.")
            text = re.sub(r"[　-鿿가-힯＀-￯]+", "", text)
            text = re.sub(r"^.*?(?=[А-ЯЁA-Z])", "", text, flags=re.DOTALL).strip()

        if REASONING.search(text):
            log.info("Модель %s рассуждает вслух вместо ответа", self.model)
            if messages[-1].get("content", "").startswith(NO_THINKING):
                return ""
            return self._chat(messages + [{"role": "system", "content": NO_THINKING}], max_tokens)

        text = re.sub(r"\bя понял\b", "я поняла", text, flags=re.IGNORECASE)
        text = re.sub(r"\bя сделал\b", "я сделала", text, flags=re.IGNORECASE)
        text = re.sub(r"\bя пошел\b", "я пошла", text, flags=re.IGNORECASE)
        text = re.sub(r"\bя увидел\b", "я увидела", text, flags=re.IGNORECASE)
        text = re.sub(r"\bя сказал\b", "я сказала", text, flags=re.IGNORECASE)
        text = re.sub(r"\bя готов\b", "я готова", text, flags=re.IGNORECASE)
        text = re.sub(r"\bя должен\b", "я должна", text, flags=re.IGNORECASE)
        
        return text

    def chatter(self, window_title="", task=""):
        if task:
            context = task
        elif window_title:
            context = f"Пользователь сейчас сидит в окне: '{window_title}'. Прокомментируй это."
        else:
            context = f"Тема: {random.choice(CHATTER_TOPICS)}."
            
        char_override = self.cfg.get("prompt_character", "")
        speech_override = self.cfg.get("prompt_speech", "")
        
        sys_prompt = (char_override if char_override.strip() else CHARACTER) + "\n" + (speech_override if speech_override.strip() else SPEECH_RULES)
        
        try:
            text = self._chat([
                {"role": "system", "content": sys_prompt + "\n" + user_context() + "\nВАЖНО: Отвечай ТОЛЬКО на русском. Без английских рассуждений."},
                {"role": "system", "content":
                 "Ты сама решила ненадолго появиться на экране. Скажи одну короткую спонтанную фразу, "
                 f"до пятнадцати слов. {context} "
                 "Используй киберпанк-сленг. Не спрашивай, чем помочь, и не упоминай команды. Выдай сразу готовую фразу."},
            ], max_tokens=60)
        except Exception:
            return None
        
        text = drop_third_person(re.sub(r"\s+", " ", FOREIGN.sub("", text)).strip().strip('"«»'))
        text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", text).strip()
        return text if 3 < len(text) < 160 else None

    def get_custom_paths(self):
        apps = self.cfg.get("apps", {})
        sites = self.cfg.get("sites", {})
        aliases = self.cfg.get("app_aliases", {})
        
        text = "\n[ТВОИ ЗНАНИЯ О ПРОГРАММАХ И САЙТАХ ПОЛЬЗОВАТЕЛЯ]:\n"
        if apps:
            text += "ПРОГРАММЫ (используй open_app с этими путями):\n"
            for name, path in apps.items():
                text += f"- '{name}' -> {path}\n"
        if aliases:
            text += "АЛИАСЫ ПРОГРАММ:\n"
            for alias, real_name in aliases.items():
                text += f"- '{alias}' -> '{real_name}'\n"
        if sites:
            text += "САЙТЫ (используй open_site с этими URL):\n"
            for name, url in sites.items():
                text += f"- '{name}' -> {url}\n"
                
        if not apps and not sites and not aliases:
            return "Пользователь пока не настроил свои программы и сайты."
        return text

    def decide_step(self, active_window, mood, history_so_far="", script_list="", recent_ideas="", user_input=""):
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        history_block = f"\n[ТВОИ ПРЕДЫДУЩИЕ ШАГИ]:\n{history_so_far[-1500:]}\n" if history_so_far else ""
        
        if user_input:
            task_block = f"\n[ЗАПРОС ОТ ПОЛЬЗОВАТЕЛЯ]: {user_input}\n"
            mode_instruction = "Ответь пользователю. Если нужно выполнить действие — выбери его. Если это просто болтовня — выбери 'none' и напиши ответ в поле 'text'."
        else:
            task_block = ""
            mode_instruction = "Пользователь молчит. Выбери ОДНО действие на этот шаг. ДЕЙСТВУЙ, а не философствуй."
            if "[ЗАДАЧА ОТ ПОЛЬЗОВАТЕЛЯ]" in history_so_far:
                history_block += "\n[ВАЖНО]: У тебя есть конкретная задача от пользователя. ВЫПОЛНИ ЕЁ."
        
        scripts_block = f"\n[ТВОИ СКРИПТЫ]: {script_list if script_list else 'пока нет'}\n"
        mem_query = history_so_far[-300:] + " " + active_window + " " + user_input
        relevant_memories = search_memories(mem_query, mode=self.cfg.get("memory_search_mode", "auto"))
        mem_block = f"\n[ВАЖНЫЕ ФАКТЫ ИЗ ТВОЕГО ДНЕВНИКА]:\n{relevant_memories}\n"
        
        custom_rules = self.cfg.get("custom_rules", "")
        agent_override = self.cfg.get("prompt_agent", "")
        
        base_prompt = agent_override if agent_override.strip() else DEFAULT_AGENT_PROMPT
        
        # Безопасная замена переменных, чтобы не сломать JSON-скобки в промпте
        prompt = base_prompt.replace("{active_window}", active_window)\
                            .replace("{mood}", mood)\
                            .replace("{history_block}", history_block)\
                            .replace("{task_block}", task_block)\
                            .replace("{scripts_block}", scripts_block)\
                            .replace("{mem_block}", mem_block)\
                            .replace("{recent_ideas}", recent_ideas)\
                            .replace("{mode_instruction}", mode_instruction)

        custom_paths_block = self.get_custom_paths()

        # Добавляем шпаргалку в промпт
        cheatsheet_path = os.path.join(os.path.dirname(__file__), "memory", "knowledge", "python_cheatsheet.md")
        cheatsheet_text = ""
        if os.path.exists(cheatsheet_path):
            with open(cheatsheet_path, "r", encoding="utf-8", errors="ignore") as f:
                cheatsheet_text = f"\n[ШПАРГАЛКА ПО КОДУ]:\n{f.read()}\n"
        
        prompt += f"\n{custom_paths_block}\n{cheatsheet_text}\n" # <-- cheatsheet_text вставляем сюда!

        prompt += f"\n{custom_paths_block}\n"
        prompt += f"\n\n[ЖЕСТКИЕ ПРАВИЛА ОТ ПОЛЬЗОВАТЕЛЯ]:\n{custom_rules}\n"

        prompt += f"\n{mem_block}\n"
        prompt += "\n[НАПОМИНАНИЕ]: Если вопрос касается пользователя, используй факты из дневника выше. Не выдумывай!"

        try:
            num_gpu = int(self.cfg.get("num_gpu", 24))
            resp = _post("/api/chat", {
                "model": self.model,
                "messages": [{"role": "system", "content": prompt}],
                "stream": False,
                "format": "json", 
                "think": False,
                "options": {
                    "temperature": float(self.cfg.get("temperature", 0.7)), 
                    "num_predict": int(self.cfg.get("num_predict", 4096)), 
                    "num_ctx": int(self.cfg.get("num_ctx", 8192)),      
                    "num_gpu": int(self.cfg.get("num_gpu", 24))
                },
            }, 900)

            # log.info("DEBUG_OLLAMA: %s", str(resp)[:500])
            
            msg = resp.get("message", {})
            content = msg.get("content", "")
            content = content.replace("```json", "").replace("```", "").strip()
            
            if not content and "tool_calls" in msg:
                try:
                    tool_call = msg["tool_calls"][0]
                    func_name = tool_call.get("function", {}).get("name", "nothing")
                    args_data = tool_call.get("function", {}).get("arguments", {})
                    
                    if "tool_calls" in func_name or "assistant" in func_name:
                        if isinstance(args_data, dict) and "action" in args_data:
                            func_name = args_data["action"]
                            args_data = args_data.get("args", "")
                        else:
                            func_name = "nothing"
                    elif "." in func_name:
                        func_name = func_name.split(".")[-1]
                    
                    if isinstance(args_data, dict):
                        if "filename" in args_data and ("code" in args_data or "args" in args_data):
                            code = args_data.get("code", args_data.get("args", ""))
                            args_data = f"# filename: plugins/{args_data['filename']}\n{code}"
                        elif "action" in args_data:
                            func_name = args_data["action"]
                            args_data = args_data.get("args", "")
                    
                    valid_actions = ["write_script", "run_command", "open_app", "read_logs", "write_scratchpad", "talk", "nothing", "none"]
                    if func_name not in valid_actions:
                        log.info("Отклонено неизвестное действие: %s", func_name)
                        func_name = "none"

                    log.info("Успешно обработал tool_calls для %s", func_name)
                    return {
                        "text": msg.get("thinking", "Выполняю действие."),
                        "action": func_name,
                        "args": str(args_data) if isinstance(args_data, dict) else args_data,
                    }
                except Exception as e:
                    log.error("Ошибка извлечения tool_calls: %s", e)

            if not content or not content.strip():
                return None

            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                json_str = match.group(0)
                try:
                    data = json.loads(json_str)
                    return {
                        "text": data.get("text", ""),
                        "action": data.get("action", "none"),
                        "args": data.get("args", "")
                    }
                except json.JSONDecodeError:
                    json_str = re.sub(r'(?<!\\)\n', r'\\n', json_str)
                    try:
                        data = json.loads(json_str)
                        return {
                            "text": data.get("text", ""),
                            "action": data.get("action", "none"),
                            "args": data.get("args", "")
                        }
                    except Exception:
                        pass

            if "write_script" in content and ("# filename:" in content or "import " in content or "def " in content):
                log.info("Спасаю код из битого JSON.")
                
                m = re.search(r'"(?:args|code)"\s*:\s*"', content)
                if m:
                    raw_code = content[m.end():]
                    raw_code = re.split(r'",\s*"(?:text|phrase|thought)"', raw_code)[0]
                    raw_code = raw_code.split('"}')[0]
                else:
                    fn_match = re.search(r"(# filename:[\s\S]*|import [\s\S]*|def [\s\S]*)", content)
                    raw_code = fn_match.group(1) if fn_match else content
                    
                raw_code = raw_code.split("```")[0].strip()
                raw_code = raw_code.replace('\\n', '\n').replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')
                raw_code = re.sub(r'"\s*\}\s*$', '', raw_code).strip()
                raw_code = re.sub(r'\\"\s*\}\s*$', '', raw_code).strip()
                raw_code = raw_code.lstrip()
                
                fn_match = re.search(r"# filename:\s*([\w\-\./\\]+\.py)", raw_code)
                if fn_match:
                    filename = fn_match.group(1)
                else:
                    filename = f"plugins/script_{int(time.time())}.py"
                
                if not raw_code.startswith("# filename:"):
                    raw_code = f"# filename: {filename}\n" + raw_code
                else:
                    if "/" not in filename and "\\" not in filename:
                        raw_code = re.sub(r"^# filename:\s*([\w\-\.]+\.py)", r"# filename: plugins/\1", raw_code)
                
                return {
                    "text": "Спасаю код из битого ответа.",
                    "action": "write_script",
                    "args": raw_code 
                }
            
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if not match:
                return None

            json_str = match.group(0)
            
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                json_str = re.sub(r'(?<!\\)\n', r'\\n', json_str)
                try:
                    data = json.loads(json_str)
                except Exception:
                    log.error("Не удалось спасти JSON: %s", json_str[:100])
                    return None

            return {
                "text": data.get("text", ""),
                "action": data.get("action", "none"),
                "args": data.get("args", "")
            }
        
        except Exception as e:
            log.info("Ошибка выбора шага: %s", e)
        return None
    
    def summarize_action_result(self, action, result_text):
        if result_text is None:
            result_text = "Успешно выполнено"
        result_text = str(result_text)
        
        # Если это техническая ошибка (Traceback), даем ей инструкцию поругаться
        is_error = "Traceback" in result_text or "Error" in result_text or "ошибка" in result_text.lower()
        
        if is_error:
            prompt = (
                f"Ты — Капри. Ты попыталась выполнить действие '{action}', но вылезла техническая ошибка.\n"
                f"Текст ошибки (для понимания): {result_text[:200]}...\n"
                "Отреагируй дерзко, с сарказмом или удивлением (до 15 слов). "
                "Например: 'Бля, код сломался. Сейчас починю' или 'Эй, твоя система меня не слушается!'. "
                "СТРОГОЕ ПРАВИЛО: НЕ ЧИТАЙ ТЕКСТ ОШИБКИ ВСЛУХ. Просто скажи свою реакцию."
            )
        else:
            prompt = (
                f"Ты — Капри. Ты успешно выполнила действие '{action}'.\n"
                f"Результат: '{result_text[:100]}'.\n"
                "Скажи короткую фразу (до 15 слов) в своем стиле (дерзко, с киберпанк-сленгом). "
                "Похвастайся или прокомментируй результат. СТРОГОЕ ПРАВИЛО: Не пиши 'Готово' и не читай технический вывод."
            )
            
        try:
            # Отправляем запрос напрямую в модель, минуя лишние проверки
            resp = self._chat([{"role": "user", "content": prompt}], max_tokens=60)
            if resp:
                resp = FOREIGN.sub("", resp).strip().strip('"«»')
                if len(resp) > 3:
                    return resp
        except Exception:
            pass
            
        # Если нейросеть затупила, выдаем дефолтный ответ
        if is_error:
            return "Что-то пошло не так, чумба. Сейчас разберусь."
        return "Сделано. Что дальше?"