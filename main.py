"""Капри — голосовой ассистент для Windows.
Запуск: run.bat (или pythonw main.py)."""
import json
import logging
import os
import queue
import random
import re
import datetime
import sys
import tempfile
import threading
import time
import base64
import shutil
from PIL import ImageGrab
import difflib
import subprocess
import urllib.request
from memory import MEM_FILE, IDEAS_FILE, DONE_FILE, ensure_dirs

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")

# журнал — до всех библиотек: если какой-то не хватает, Капри падает без окна, и узнать причину можно только тут
logging.basicConfig(filename=os.path.join(BASE, "capri.log"), level=logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("capri")
log.info("Python %s", sys.version.split()[0])


def fatal(text):
    """Капри запускается без окна консоли, поэтому о том, что не так, говорим окном Windows."""
    log.error(text)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "Капри не запустилась", 0x10)
    except Exception:
        pass
    sys.exit(1)


try:
    from PySide6.QtCore import QObject, Qt, Signal
    from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import (QApplication, QHBoxLayout, QInputDialog, QLabel, QMenu, QSlider,
                                   QSystemTrayIcon, QWidget, QWidgetAction)

    from actions import Actions, Reply
    from ai import AI
    from persona import set_user
    from local_ai import LocalAI, read_memories
    from avatar import Avatar
    import zapret
    from voice import (Listener, Speaker, default_input_name, google_stt, input_devices, make_glitch_sound,
                       play_sound_async)
except ImportError as e:
    log.exception("Не хватает библиотек")
    fatal(f"Не установлены нужные библиотеки ({e.name or e}).\n\n"
          f"Запусти setup.bat в папке Капри и дождись надписи «Готово», потом снова run.bat.\n"
          f"Если setup.bat выдаёт ошибку — сфотографируй его окно.\n\nPython {sys.version.split()[0]}")

DEFAULTS = {
    "enable_autonomy": True,
    "provider": "ollama",
    "api_key": "",
    "api_model": "gpt-4o",
    "enable_ai": False,
    "local_ai": True,
    "local_model": "qwen3:8b",
    "barge_in": True,
    "mic_device": None,
    "chatter": True,
    "chatter_min_minutes": 15,
    "chatter_max_minutes": 40,
    "roam_chance": 0.5,
    "teleport_on_answer": True,
    "search_when_unsure": True,
    "voice_volume": 100,
    "mic_gain": 1.0,
    "mic_sensitivity": 100,
    "user_name_mode": "none",
    "user_name": "",
    "user_gender": "male",
    "browser": "",
    "replies": {},
    "anthropic_api_key": "",
    "model": "claude-opus-5-5",
    "wake_words": ["капри", "каприз", "капре", "кепри", "капли"],
    "use_google_stt": True,
    "voice": "ru-RU-SvetlanaNeural",
    "tts_engine": "edge",
    "voice_rate": "+10%",
    "voice_pitch": "+15Hz",
    "voice_shift": 0,
    "voice_lively": False,
    "voice_fx": 1.8,
    "listen_window_seconds": 8,
    "followup_seconds": 6,
    "hide_after_seconds": 12,
    "greet_on_start": True,
    "vosk_model": "models/vosk-model-small-ru-0.22",
    "sites": {},
    "apps": {},
    "app_aliases": {},
    "num_gpu": 24,
    "temperature": 0.7,
    "num_ctx": 8192,
    "num_predict": 4096,
    "custom_rules": "",
    "prompt_character": "",
    "prompt_speech": "",
    "prompt_agent": "",
    "chatter_min_minutes": 0.5,
    "chatter_max_minutes": 1.0,
    "autonomy_think_minutes": 2.0,
    "roam_chance": 0.8,
    "hide_after_seconds": 60,
    "listen_window_seconds": 8,
    "chatter": True,
    "barge_in": True,
    "teleport_on_answer": True,
    "enable_backup": True,
    "backup_dir": r"G:\Capri_Backups",
    "backup_max_count": 30,
    "edge_rate": "+10%",
    "edge_pitch": "+15Hz",
    "silero_pitch": "high",
    "memory_search_mode": "auto",
    "max_consecutive_errors": 3,
    "enable_kick": True,
    "kick_frequency": 5,
    "kick_prompt": "СИСТЕМА: Ты застряла на одном месте. Смени тему, придумай НОВУЮ идею или реализуй другую задачу.",
    "chain_kick_freq": 2,
    "chain_kick_super_freq": 6,
    "chain_kick_prompt": "Твой фокус — СОЗДАЙ НОВЫЙ ПРОЕКТ. Выбери категорию, которую ты давно не трогала (например, аудио или картинки). СТРОГОЕ ПРАВИЛО: Имя нового файла должно быть уникальным (добавь '_v2', '_new' или придумай новое название). ЗАПРЕЩЕНО использовать 'main.py' и 'csv_writer.py'!",
    "chain_kick_super_prompt": "У тебя полная свобода! Создай скрипт, которого ЕЩЕ НЕТ в реестре. Придумай что-то безумное и новое. НЕ ИСПОЛЬЗУЙ старые имена файлов.",
    # Зрение
    "vision_model": "minicpm-v",
    "vision_quality": 70,
    "vision_tokens": 80,
    # Память и Автономность
    "short_term_memory_limit": 30,
    "max_steps_chain": 30,
    "allow_write_script": True,
    # Уведомления
    "enable_tg_notify": True,
    "tg_notify_interval": 10,
}


def _config_blank():
    try:
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:
            return not f.read().strip()
    except FileNotFoundError:
        return True


def _edit_config(change):
    try:
        if _config_blank():
            data = {}
        else:
            with open(CONFIG_PATH, encoding="utf-8-sig") as f:
                data = json.load(f)
    except Exception:
        log.exception("config.json с ошибкой, не записываю")
        return "в config.json ошибка. Исправь её или удали файл, он создастся заново."
    change(data)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return None


def save_setting(key, value):
    _edit_config(lambda data: data.__setitem__(key, value))


def save_entry(section, name, value):
    def change(data):
        entries = data.setdefault(section, {})
        if value is None and name not in DEFAULTS.get(section, {}):
            entries.pop(name, None)
        else:
            entries[name] = value
    return _edit_config(change)


def user_display_name(cfg):
    mode = cfg.get("user_name_mode", "none")
    if mode == "custom":
        return cfg.get("user_name", "").strip()
    if mode == "windows":
        return os.environ.get("USERNAME", "")
    if mode == "pc":
        return os.environ.get("COMPUTERNAME", "")
    return ""


def apply_user(cfg):
    set_user(user_display_name(cfg), cfg.get("user_gender", "male"))


CONFIG_ERROR = ""


def load_config():
    global CONFIG_ERROR
    CONFIG_ERROR = ""
    cfg = json.loads(json.dumps(DEFAULTS))
    if not _config_blank():
        try:
            with open(CONFIG_PATH, encoding="utf-8-sig") as f:
                user = json.load(f)
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    for name, value in v.items():
                        if value is None:
                            cfg[k].pop(name, None)
                        else:
                            cfg[k][name] = value
                else:
                    cfg[k] = v
            missing = [k for k in DEFAULTS if k not in user]
            if missing:
                _edit_config(lambda data: [data.setdefault(k, DEFAULTS[k]) for k in missing])
                log.info("В config.json добавлены недостающие настройки: %s", ", ".join(missing))
        except json.JSONDecodeError as e:
            log.error("config.json с ошибкой (строка %d, символ %d: %s)", e.lineno, e.colno, e.msg)
            CONFIG_ERROR = (f"В config.json ошибка в строке {e.lineno}, я его не прочитала. "
                            "Проверь кавычки, запятые и двойные слеши.")
        except Exception:
            log.exception("config.json не прочитался")
            CONFIG_ERROR = "Не смогла прочитать config.json."
    else:
        log.info("config.json пустой или удалён, создаю из шаблона")
        example_path = os.path.join(BASE, "config.example.json")
        if os.path.exists(example_path):
            # Копируем чистый шаблон, чтобы пользователю было проще
            shutil.copyfile(example_path, CONFIG_PATH)
        else:
            # Если шаблона нет (старая версия), берем из DEFAULTS
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)
    return cfg


STOP_RE = re.compile(r"\b(стоп|хватит|молчи|замолчи|помолчи|достаточно|подожди|остановись|перестань|"
                     r"заткнись|умолкни)\b")


def add_idea(text):
    with open(IDEAS_FILE, "a", encoding="utf-8") as f:
        f.write(f"- {text}\n")


def get_ideas():
    if not os.path.exists(IDEAS_FILE):
        return ""
    with open(IDEAS_FILE, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def mark_idea_done(idea_text):
    if os.path.exists(IDEAS_FILE):
        with open(IDEAS_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        with open(IDEAS_FILE, "w", encoding="utf-8") as f:
            for line in lines:
                if idea_text not in line:
                    f.write(line)
    with open(DONE_FILE, "a", encoding="utf-8") as f:
        f.write(f"- {idea_text}\n")

REGISTRY_FILE = os.path.join(BASE, "plugins", "registry.json")

def load_registry():
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

def add_to_registry(filename, description=""):
    registry = load_registry()
    registry[filename] = description
    os.makedirs(os.path.dirname(REGISTRY_FILE), exist_ok=True)
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

class Capri(QObject):
    summon = Signal()
    vanish = Signal()
    mode = Signal(str, float)
    subtitle = Signal(str)
    quit_app = Signal()
    anim = Signal(str)
    roam = Signal()
    hop = Signal()
    glitch = Signal()
    move_to = Signal(str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        words = sorted(cfg["wake_words"], key=len, reverse=True)
        self.wake_re = re.compile(r"(^|\s)(" + "|".join(map(re.escape, words)) + r")(?=\s|$|[,.!?])",
                                  re.IGNORECASE)
        self.ai = AI(cfg)
        self.local = LocalAI(cfg) if cfg.get("local_ai") else None
        if self.local:
            self.local.on_model_change = self._remember_model
        self.actions = Actions(cfg, BASE, self.ai, save=save_entry)
        self.config_mtime = self._config_mtime()
        self.zapret_checked = False
        self.actions.local = self.local
        self.speaker = Speaker(cfg)
        self.jobs = queue.Queue()
        self.awake_until = 0.0
        self.last_partial_wake = 0.0
        self.speaking = False
        self.interrupted = False
        self.speech_words = set()
        self.speech_end = 0.0
        self.last_activity = time.time()
        self.recent_chatter = []
        self.listener = None
        self.glitch_wav = os.path.join(tempfile.gettempdir(), "capri_glitch.wav")
        self.sleep_until = 0
        self.mood = "neutral"
        self.last_tg_notify_time = 0
        self.is_busy = False
        self.chain_counter = 0
        try:
            make_glitch_sound(self.glitch_wav, self.speaker.volume)
        except Exception:
            self.glitch_wav = None

    def start(self):
        plugins_dir = os.path.join(BASE, "plugins")
        log_dir = os.path.join(BASE, "script_logs")
        os.makedirs(log_dir, exist_ok=True)

        # --- БЭКАП ПРИ ЗАПУСКЕ ---
        if self.cfg.get("enable_backup", True):    
            try:
                import backup
                threading.Thread(target=backup.make_backup, daemon=True).start()
                log.info("Запущен фоновый бэкап проекта")
            except Exception as e:
                log.error("Не удалось запустить бэкап: %s", e)

        if os.path.exists(plugins_dir):
            for f in os.listdir(plugins_dir):
                path = os.path.join(plugins_dir, f)
                if os.path.isfile(path):
                    if f.startswith("script_") and f.endswith(".py"):
                        try:
                            os.remove(path)
                            log.info("Автоуборка: удален старый скрипт %s", f)
                        except Exception:
                            pass
                    elif f.endswith((".txt", ".log", ".json")) and f != "registry.json":
                        try:
                            shutil.move(path, os.path.join(log_dir, f))
                            log.info("Автоуборка: лог %s перенесен в script_logs", f)
                        except Exception:
                            pass

        threading.Thread(target=self._worker, daemon=True).start()
        if self.local:
            threading.Thread(target=self.local.start_server, daemon=True).start()
        model = os.path.join(BASE, self.cfg["vosk_model"])
        if os.path.isdir(model):
            self.listener = Listener(model, self.on_final, self.on_partial, self.on_listener_error,
                                     device_name=self.cfg.get("mic_device") or None,
                                     gain=float(self.cfg.get("mic_gain", 1.0)),
                                     sensitivity=int(self.cfg.get("mic_sensitivity", 100)))
            self.listener.start()
        else:
            self.jobs.put(("say", "Я тебя не слышу. Модель распознавания речи не найдена. Проверь папку models."))
            return

        self.appear(3.0)
        if CONFIG_ERROR:
            self.jobs.put(("say", CONFIG_ERROR))

        threading.Thread(target=self._chatter_loop, daemon=True).start()
        threading.Thread(target=self._mood_loop, daemon=True).start()
        threading.Thread(target=self._notification_loop, daemon=True).start()

    def _chatter_loop(self):
        last_thought = time.time()
        greeted = False
        while True:
            time.sleep(10)
            if not self.jobs.empty() or self.speaking or self.is_busy:
                last_thought = time.time()
                continue
            
            now = time.time()
            
            # Ждем загрузки модели для первого приветствия
            if self.cfg.get("greet_on_start") and not greeted:
                if self.local and self.local.running():
                    log.info("Модель загружена, отправляем приветствие.")
                    text = self.chatter_line("Поприветствуй пользователя. Ты только что загрузилась.")
                    
                    if text:
                        self.jobs.put(("chatter", text))
                    else:
                        # СТРАХОВКА: если ИИ затупил, говорим стандартную фразу
                        log.info("ИИ не смог поздороваться, использую запасную фразу.")
                        self.jobs.put(("say", "Здарова, чумба! Я снова на связи. Соскучился?"))
                        
                    greeted = True
                    last_thought = now
                continue
                
            # Читаем настройку из конфига (в минутах) и переводим в секунды
            think_minutes = float(self.cfg.get("autonomy_think_minutes", 2.0))
            
            if now - last_thought > (think_minutes * 60):
                last_thought = now
                if self.local and self.local.running() and self.cfg.get("chatter", True) and self.cfg.get("enable_autonomy", True):
                    log.info("Капри запускает сессию размышлений...")
                    self.jobs.put(("autonomy_chain", "Ты предоставлена сама себе. Делай то, что тебе хочется. Но учти: пользователь сейчас занят в другом окне. НЕ ПОВТОРЯЙ его действия. Создай что-то новое, исследуй систему или придумай идею. Если придумала идею — запиши её через [IDEA: ...], если реализовала — через [DONE: ...]."))

    def _mood_loop(self):
        moods = ["mischievous", "obsessive", "glitchy", "bored", "neutral"]
        while True:
            time.sleep(random.uniform(600, 1200))
            self.mood = random.choice(moods)
            log.info("Настроение Капри изменилось на: %s", self.mood)

    def ask_vision(self, prompt_text):
        if not self.cfg.get("enable_vision", True):
            return "Зрение у меня отключено в настройках."
        try:
            import tempfile, os, json, urllib.request
            from PySide6.QtGui import QGuiApplication
            responses = []
            screens = QGuiApplication.screens()
            for i, screen in enumerate(screens):
                geo = screen.geometry()
                bbox = (geo.x(), geo.y(), geo.x() + geo.width(), geo.y() + geo.height())
                img = ImageGrab.grab(bbox=bbox)
                img.thumbnail((1280, 720))
                temp_path = os.path.join(tempfile.gettempdir(), f"capri_vision_{i}.jpg")
                img.save(temp_path, "JPEG", quality=int(self.cfg.get("vision_quality", 70)))
                with open(temp_path, "rb") as f:
                    b64_img = base64.b64encode(f.read()).decode('utf-8')
                os.remove(temp_path)
                payload = {
                    "model": self.cfg.get("vision_model", "minicpm-v"), # Берем модель из конфига
                    "messages": [{"role": "user", "content": f"Экран {i+1}. {prompt_text}", "images": [b64_img]}],
                    "stream": False,
                    "keep_alive": "0s",
                    "options": {"temperature": 0.7, "num_predict": int(self.cfg.get("vision_tokens", 80))}
                }
                req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    res = json.loads(r.read().decode("utf-8"))
                    text = res.get("message", {}).get("content", "").strip()
                    if text:
                        responses.append(text)
            if responses:
                return " ".join(responses)
        except Exception as e:
            log.error("Ошибка зрения: %s", e)
            return None

    def _notification_loop(self):
        import asyncio
        import time
        import logging
        log = logging.getLogger("capri")
        seen_ids = set()

        async def check_notifications():
            try:
                from winrt.windows.ui.notifications.management import UserNotificationListener
                from winrt.windows.ui.notifications import NotificationKinds
                listener = UserNotificationListener.current
                access = await listener.request_access_async()
                if access != 1:
                    return
                notifs = await listener.get_notifications_async(NotificationKinds.TOAST)
                for n in notifs:
                    if n.id in seen_ids:
                        continue
                    seen_ids.add(n.id)
                    app_name = n.app_info.display_info.display_name.lower()
                    if "telegram" in app_name:
                        binding = n.notification.visual.bindings.get_at(0)
                        texts = [t.text for t in binding.get_text_elements()]
                        if texts:
                            sender = texts[0]
                            msg = texts[1] if len(texts) > 1 else ""
                            now = time.time()
                            if now - self.last_tg_notify_time > 180:
                                self.last_tg_notify_time = now
                                log.info("Уведомление от %s: %s", sender, msg)
                                self.jobs.put(("tg_notification", sender, msg))
            except Exception as e:
                log.debug("Ошибка чтения уведомлений: %s", e)

        while True:
            if not self.cfg.get("enable_tg_notify", True):
                time.sleep(5)
                continue
            try:
                asyncio.run(check_notifications())
            except Exception:
                pass
            time.sleep(int(self.cfg.get("tg_notify_interval", 10)))

    def chatter_line(self, task=""):
        try:
            from automation import foreground_title
            active_window = foreground_title().lower()
        except Exception:
            active_window = ""
            
        if self.local and self.local.running():
            # Передаем задачу (например, приветствие) в нейросеть
            text = self.local.chatter(window_title=active_window, task=task)
            if text:
                self.recent_chatter = (self.recent_chatter + [text])[-6:]
                return text
        return None

    def has_wake(self, text):
        text_lower = text.lower()
        if self.wake_re.search(text_lower):
            return True
        words = re.findall(r'\w+', text_lower)
        for w in words:
            if len(w) < 4:
                continue
            for wake in self.cfg["wake_words"]:
                if difflib.SequenceMatcher(None, w, wake).ratio() >= 0.75:
                    return True
        return False

    def strip_wake(self, text):
        t = text.lower()
        last = None
        for last in self.wake_re.finditer(t):
            pass
        if last and t[last.end():].strip(" ,.!?"):
            t = t[last.end():]
        t = self.wake_re.sub(" ", t)
        words = t.split()
        cleaned = []
        for w in words:
            is_wake = False
            w_clean = re.sub(r'[^\w]', '', w)
            for wake in self.cfg["wake_words"]:
                if len(w_clean) >= 4 and difflib.SequenceMatcher(None, w_clean, wake).ratio() >= 0.75:
                    is_wake = True
                    break
            if not is_wake:
                cleaned.append(w)
        return re.sub(r"^[\s,.!?]+|[\s,.!?]+$", "", " ".join(cleaned))

    def appear(self, seconds):
        if self.glitch_wav:
            play_sound_async(self.glitch_wav)
        self.summon.emit()
        self.mode.emit("listening", float(seconds))

    def is_echo(self, text):
        words = text.lower().replace("ё", "е").split()
        return bool(words) and all(w in self.speech_words for w in words)

    def wants_interrupt(self, text):
        t = text.lower()
        if self.has_wake(t) or STOP_RE.search(t):
            if self.is_echo(text):
                return False
            return True
        return False

    def interrupt(self):
        if not self.speaking or self.interrupted:
            return
        self.interrupted = True
        self.speaker.stop()
        self.awake_until = time.time() + self.cfg["listen_window_seconds"]
        self.mode.emit("listening", float(self.cfg["listen_window_seconds"]))
        self.subtitle.emit("Слушаю...")
        log.info("Капри перебили")

    def on_partial(self, text):
        if time.time() < self.sleep_until:
            return
        now = time.time()
        if self.speaking:
            if self.cfg.get("barge_in") and self.wants_interrupt(text):
                self.interrupt()
            return
        if now - self.last_partial_wake > 3 and now > self.awake_until and self.has_wake(text):
            self.last_partial_wake = now
            self.appear(self.cfg["listen_window_seconds"])

    def on_final(self, text, audio):
        if time.time() < self.sleep_until:
            if "проснись" in text.lower() or "выйди из сна" in text.lower():
                self.sleep_until = 0
                self.jobs.put(("say", "Я проснулась. Что случилось?"))
            return
        now = time.time()
        if self.actions.autoscroll_active() and STOP_RE.search(text.lower()) and not self.is_echo(text):
            self.actions.stop_background()
            self.subtitle.emit("Стоп.")
            return
        if self.speaking and not self.interrupted:
            if not (self.cfg.get("barge_in") and self.wants_interrupt(text)):
                return
            self.interrupt()
        if now - self.speech_end < 1.0 and self.is_echo(text):
            return
        woke = self.has_wake(text)
        if not woke and now > self.awake_until:
            return
        cmd = self.strip_wake(text) if woke else text
        if STOP_RE.match(cmd.strip()) and len(cmd.split()) <= 3:
            self.awake_until = now + self.cfg["listen_window_seconds"]
            if self.actions.stop_background():
                self.subtitle.emit("Стоп.")
            return
        if len(cmd) < 2:
            self.awake_until = now + self.cfg["listen_window_seconds"]
            self.subtitle.emit("")
            if now - self.last_partial_wake > 3:
                self.appear(self.cfg["listen_window_seconds"])
            return
        self.awake_until = 0
        self.jobs.put(("voice", cmd, audio, woke))

    def on_listener_error(self, err, kind="mic"):
        self.jobs.put(("say", "У меня сломался микрофон или модель. Проверь настройки."))

    def set_profile(self, mode, name, gender):
        for key, value in (("user_name_mode", mode), ("user_name", name), ("user_gender", gender)):
            self.cfg[key] = value
            save_setting(key, value)
        apply_user(self.cfg)
        log.info("Обращение: %s, %s", user_display_name(self.cfg) or "без имени", gender)

    def set_chatter(self, on):
        self.cfg["chatter"] = bool(on)
        save_setting("chatter", bool(on))
        log.info("Самостоятельные появления: %s", "включены" if on else "выключены")

    def set_search_when_unsure(self, on):
        self.cfg["search_when_unsure"] = bool(on)
        save_setting("search_when_unsure", bool(on))
        log.info("Поиск в браузере: %s", "включён" if on else "выключен")

    def _remember_model(self, name):
        self.cfg["local_model"] = name
        save_setting("local_model", name)

    @staticmethod
    def _config_mtime():
        try:
            return os.path.getmtime(CONFIG_PATH)
        except OSError:
            return None

    def reload_config_if_changed(self, speak=True):
        mtime = self._config_mtime()
        if mtime == self.config_mtime:
            return
        fresh = load_config()
        if CONFIG_ERROR:
            if speak:
                self.config_mtime = mtime
                self.say(CONFIG_ERROR)
            return
        self.config_mtime = mtime
        
        # ВОТ ТУТ МЫ ОБНОВЛЯЕМ ВООБЩЕ ВСЕ НАСТРОЙКИ, А НЕ ТОЛЬКО ИМЯ И САЙТЫ
        for key in fresh.keys():
            self.cfg[key] = fresh[key]
            
        self.actions.set_lists(self.cfg)
        apply_user(self.cfg)
        
        # Обновляем модель на лету, если она изменилась
        if self.local:
            self.local.model = self.cfg.get("local_model", "qwen3:8b")
            
        log.info("config.json перечитан и обновлен в памяти")

    def current_mic(self):
        if self.listener and self.listener.active_name:
            return self.listener.active_name
        return self.cfg.get("mic_device") or default_input_name()

    def set_mic(self, name, announce=True):
        self.cfg["mic_device"] = name
        save_setting("mic_device", name)
        if self.listener:
            self.listener.set_device(name)
        log.info("Выбран микрофон: %s", name or "по умолчанию")
        if announce:
            self.jobs.put(("say", f"Теперь слушаю через: {name or 'микрофон Windows по умолчанию'}."))

    def set_mic_tuning(self, gain=None, sensitivity=None):
        if gain is not None:
            self.cfg["mic_gain"] = round(float(gain), 2)
            save_setting("mic_gain", self.cfg["mic_gain"])
            if self.listener:
                self.listener.gain = self.cfg["mic_gain"]
        if sensitivity is not None:
            self.cfg["mic_sensitivity"] = int(sensitivity)
            save_setting("mic_sensitivity", self.cfg["mic_sensitivity"])
            if self.listener:
                self.listener.sensitivity = self.cfg["mic_sensitivity"]

    def set_voice_fx(self, strength):
        self.speaker.fx = round(float(strength), 2)
        self.cfg["voice_fx"] = self.speaker.fx
        save_setting("voice_fx", self.speaker.fx)

    def set_voice_volume(self, volume):
        self.speaker.volume = int(volume)
        self.cfg["voice_volume"] = int(volume)
        save_setting("voice_volume", int(volume))
        if self.glitch_wav:
            try:
                make_glitch_sound(self.glitch_wav, self.speaker.volume)
            except Exception:
                pass

    def call_from_click(self):
        if self.speaking:
            self.interrupt()
            return
        self.awake_until = time.time() + self.cfg["listen_window_seconds"]
        self.appear(self.cfg["listen_window_seconds"])
        self.subtitle.emit("Слушаю...")

    def text_command(self, text):
        self.summon.emit()
        self.jobs.put(("text", text))

    def _worker(self):
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        while True:
            job = self.jobs.get()
            try:
                self.is_busy = True
                self._process(job)
            except Exception:
                log.exception("Ошибка обработки %s", job[0])
                self.say("Что-то сломалось в моих нейронах.")
            finally:
                self.is_busy = False

    def _exec_autonomy_action(self, action, extra, title=""):
        try:
            if action == "roam":
                self.move_to.emit(random.choice(["monitor:next", "top-left", "bottom-right", "center"]))
                return "перелетела в новое место"
            elif action == "glitch":
                self.glitch.emit()
                return "устроила цифровой сбой"
            elif action == "run_command":
                if extra:
                    cmd_lower = extra.lower()
                    # 1. Блокируем особо опасные команды
                    blocked = ["format ", "diskpart", "shutdown ", "bcdedit", "reg delete", "vssadmin", "wbadmin"]
                    if any(b in cmd_lower for b in blocked):
                        return "СИСТЕМА: Эта команда запрещена."
                    # 2. Проверяем команды удаления на пути вне папки проекта
                    if any(d in cmd_lower for d in ["del ", "erase ", "rmdir ", "rd ", "rm "]):
                        # Ищем абсолютные пути
                        for m in re.finditer(r'[a-zA-Z]:\\[^\s"\']*|\\\\[^\s"\']+', extra):
                            p = m.group(0)
                            if not os.path.abspath(p).startswith(os.path.abspath(BASE)):
                                return "СИСТЕМА: Удаление вне папки проекта запрещено."
                        # Ищем выходы через ..
                        for m in re.finditer(r'\.\.[\\/][^\s"\']*', extra):
                            p = m.group(0)
                            resolved = os.path.abspath(os.path.join(BASE, p))
                            if not resolved.startswith(os.path.abspath(BASE)):
                                return "СИСТЕМА: Удаление вне папки проекта запрещено."
                    # --- ФИКС СЛОВАРЕЙ В АРГУМЕНТАХ ---
                    if extra.startswith("{") and extra.endswith("}"):
                        try:
                            import ast
                            parsed = ast.literal_eval(extra)
                            if isinstance(parsed, dict):
                                extra = parsed.get("cmd", parsed.get("command", extra))
                        except Exception:
                            pass
                # -----------------------------------
                    # 3. Выполняем команду (cwd=BASE, чтобы относительные пути были от корня проекта)
                    res = subprocess.run(extra, shell=True, capture_output=True, text=True, timeout=60, creationflags=0x08000000, cwd=BASE)
                    out = (res.stdout or "").strip() or (res.stderr or "").strip() or "команда выполнена без вывода"
                    if len(out) > 400: out = out[:400] + "..."
                    return f"команда '{extra}' выполнена. Вывод: {out}"
                return "не указала команду"
            elif action == "write_script":
                if not self.cfg.get("allow_write_script", True):
                    return "СИСТЕМА: Создание скриптов запрещено в настройках. Выбери другое действие."
                code = extra.replace("```python", "").replace("```", "").strip().replace("\\n", "\n")
                code = code.lstrip()

                # 1. СНАЧАЛА ОЧИЩАЕМ ХВОСТЫ JSON (чтобы ast.parse не спотыкался о них)
                code = re.sub(r'"\s*\}\s*$', '', code).strip()
                code = re.sub(r'\\"\s*\}\s*$', '', code).strip()
                # -----------------------------

                # 2. ТЕПЕРЬ ПРОВЕРЯЕМ СИНТАКСИС (код уже чистый)
                import ast
                try:
                    ast.parse(code)
                except SyntaxError as e:
                    return f"СИСТЕМА: В коде синтаксическая ошибка (строка {e.lineno}): {e.msg}. Исправь её и напиши код заново."
                # ---------------------------

                filename_match = re.search(r"^#\s*filename:\s*([\w\-\./\\]+\.py)", code, re.IGNORECASE)
                if not filename_match:
                    return "СИСТЕМА: Забыто имя файла! Добавь '# filename: имя.py'."
                filename = filename_match.group(1)
                code = code[filename_match.end():].strip()
                
                # --- ЖЕСТКАЯ ЛОГИКА ПАПОК ---
                if os.path.isabs(filename):
                    final_path = filename
                else:
                    # Если папка не указана, принудительно шлем в plugins
                    if "/" not in filename and "\\" not in filename:
                        final_path = os.path.join(BASE, "plugins", filename)
                    else:
                        final_path = os.path.join(BASE, filename)
                # ---------------------------

                import ast
                try:
                    ast.parse(code)
                except SyntaxError as e:
                    return f"СИСТЕМА: В коде синтаксическая ошибка (строка {e.lineno}): {e.msg}. Исправь её и напиши код заново."

                with open(final_path, "w", encoding="utf-8") as f:
                    f.write(code)
                add_to_registry(os.path.basename(final_path), "Создан автоматически")
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                if any(kw in code for kw in ["time.sleep", "while True", "schedule", "pip", "subprocess", "mainloop", "tkinter", "turtle", "pygame"]):
                    log_dir = os.path.join(BASE, "script_logs")
                    os.makedirs(log_dir, exist_ok=True)
                    output_file = os.path.join(log_dir, f"{os.path.basename(filename)}_output.txt")
                    with open(output_file, "w", encoding="utf-8") as out_log:
                        subprocess.Popen(["python", final_path], creationflags=0x08000000, env=env, cwd=os.path.dirname(final_path), stdin=subprocess.DEVNULL, stdout=out_log, stderr=subprocess.STDOUT)
                    return f"Скрипт {filename} запущен в фоне. Вывод в '../script_logs/{os.path.basename(filename)}_output.txt'."
                else:
                    res = subprocess.run(["python", final_path], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, creationflags=0x08000000, env=env, cwd=os.path.dirname(final_path))
                    out = (res.stdout or "").strip() or (res.stderr or "").strip() or "выполнен без вывода"
                    return f"скрипт {filename} создан. Вывод: {out[:300]}"
            elif action == "delete_script":
                if extra:
                    filename = extra.strip().split("/")[-1].split("\\")[-1]
                    if not filename.endswith(".py"): filename += ".py"
                    path = os.path.join(BASE, "plugins", filename)
                    if os.path.exists(path):
                        os.remove(path)
                        return f"Скрипт {filename} удален."
                    return f"Скрипт {filename} не найден."
                return "не указала имя скрипта"
            elif action == "read_script":
                if extra:
                    filename = extra.strip().split("/")[-1].split("\\")[-1]
                    if not filename.endswith(".py"): filename += ".py"
                    path = os.path.join(BASE, "plugins", filename)
                    if os.path.exists(path):
                        with open(path, "r", encoding="utf-8") as f:
                            content = f.read()
                        return f"Код скрипта {filename}:\n```python\n{content}\n```"
                    return f"Скрипт {filename} не найден."
                return "не указала имя скрипта"
            elif action == "recall_memory":
                if extra:
                    from local_ai import search_memories
                    mem_fact = search_memories(extra, max_results=3, mode=self.cfg.get("memory_search_mode", "auto"))
                    if mem_fact and "Пока пусто" not in mem_fact:
                        return f"Я нашла в своей памяти: {mem_fact}"
                    return f"В моей памяти нет информации по запросу '{extra}'."
                return "не указала запрос"
            elif action == "remember":
                parts = extra.split("|")
                if len(parts) == 2:
                    name, target = parts[0].strip(), parts[1].strip()
                    # Если это не сайт и не программа, а просто факт
                    if not target.startswith("http") and not target.endswith((".exe", ".lnk", ".url", ".bat")):
                        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        with open(MEM_FILE, "a", encoding="utf-8") as f:
                            f.write(f"\n### [{timestamp}] [КАПРИ] (Запомнила факт)\n{name} - {target}\n")
                        # СРАЗУ ДОБАВЛЯЕМ В ВЕКТОРНУЮ БАЗУ (RAG)
                        try:
                            import memory_rag
                            memory_rag.add_memory(f"{name} - {target}")
                        except Exception as e:
                            log.error("Ошибка добавления в RAG: %s", e)
                        return f"Запомнила факт: {name} - {target}"
                    else:
                        sec = "sites" if target.startswith("http") else "apps"
                        err = self.actions.remember(sec, name, target)
                        if err: return f"СИСТЕМА: Ошибка сохранения: {err}"
                        return "Запомнила в свой список."
                return "СИСТЕМА: неверный формат, нужно 'название|значение'"
            elif action == "forget":
                self.actions.remember("sites", extra, None)
                self.actions.remember("apps", extra, None)
                return f"забыла {extra}"
            elif action == "set_volume":
                self.actions.set_volume(int(extra))
                return f"громкость {extra}"
            elif action == "set_brightness":
                self.actions.set_brightness(int(extra))
                return f"яркость {extra}"
            elif action == "media_control":
                import media
                media.control(extra)
                return f"медиа: {extra}"
            elif action == "scroll_page":
                import automation
                automation.scroll(int(extra))
                return f"прокрутила на {extra}"
            elif action == "press_keys":
                from actions import parse_keys, send_keys
                keys, _ = parse_keys(extra)
                send_keys(keys)
                return f"нажала {extra}"
            elif action == "minimize_window":
                import ctypes
                ctypes.windll.user32.ShowWindow(ctypes.windll.user32.GetForegroundWindow(), 6)
                return "свернула окно"
            elif action == "close_process":
                os.system(f"taskkill /f /im {extra}")
                return f"закрыла {extra}"
            elif action == "create_folder":
                os.makedirs(extra, exist_ok=True)
                return f"создала папку {extra}"
            elif action == "analyze_pc":
                from actions import analyze_pc
                issues, report = analyze_pc()
                return report[:400]
            elif action == "write_scratchpad":
                path = os.path.join(BASE, "memory", "misc", "scratchpad.md")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(extra)
                return "Запись в рабочую память обновлена."
            elif action == "read_scratchpad":
                path = os.path.join(BASE, "memory", "misc", "scratchpad.md")
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    return f"Твоя рабочая память:\n{content}"
                return "Твоя рабочая память пуста."
            elif action == "read_logs":
                log_path = os.path.join(BASE, "capri.log")
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    recent = lines[-50:]
                    filtered = [line.strip() for line in recent if "ERROR" in line or "Капри:" in line or "Цепочка" in line or "Команда:" in line]
                    if not filtered:
                        return "В логах нет ошибок."
                    return "Последние записи:\n" + "\n".join(filtered[-15:])
                return "Файл логов не найден."
            elif action == "web_search":
                if extra:
                    from duckduckgo_search import DDGS
                    import requests
                    from bs4 import BeautifulSoup
                    clean_query = extra.replace(".py", "").replace("Traceback (most recent call last):", "").strip()
                    try:
                        results = list(DDGS().text(clean_query, max_results=3, region='ru-ru'))
                        if not results:
                            return f"По запросу '{clean_query}' ничего не найдено."
                        combined_text = f"Информация по запросу '{clean_query}':\n\n"
                        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                        for i, res in enumerate(results):
                            url = res.get('href', '')
                            title = res.get('title', 'Без названия')
                            if not url: continue
                            try:
                                resp = requests.get(url, headers=headers, timeout=10)
                                resp.raise_for_status()
                                soup = BeautifulSoup(resp.text, 'html.parser')
                                for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
                                    script.decompose()
                                page_text = soup.get_text(separator=' ')
                                page_text = re.sub(r'\s+', ' ', page_text).strip()
                                combined_text += f"--- ИСТОЧНИК {i+1}: {title} ({url}) ---\n{page_text[:1000]}...\n\n"
                            except Exception as e:
                                combined_text += f"--- ИСТОЧНИК {i+1}: {title} ({url}) ---\nОшибка: {e}\n\n"
                        return combined_text
                    except Exception as e:
                        return f"Ошибка поиска: {e}"
                return "не указала запрос"
            elif action == "web_read":
                if extra:
                    import requests
                    from bs4 import BeautifulSoup
                    try:
                        if not extra.startswith("http"):
                            from duckduckgo_search import DDGS
                            results = DDGS().text(extra, max_results=1, region='ru-ru')
                            if not results:
                                return f"По запросу '{extra}' ничего не найдено."
                            extra = results[0]['href']
                        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                        resp = requests.get(extra, headers=headers, timeout=15)
                        resp.raise_for_status()
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        for script in soup(["script", "style", "nav", "footer", "header"]):
                            script.decompose()
                        text = soup.get_text(separator=' ')
                        text = re.sub(r'\s+', ' ', text).strip()
                        return f"Прочитала страницу {extra}. Текст: {text[:2500]}"
                    except Exception as e:
                        return f"Ошибка чтения страницы: {e}"
                return "не указала ссылку или запрос"
            elif action == "get_weather":
                if extra:
                    import requests
                    import urllib.parse
                    try:
                        city = extra.strip() or "Moscow"
                        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=%l:+%c+%t,+ветер+%w&lang=ru"
                        resp = requests.get(url, timeout=10)
                        if resp.status_code == 200:
                            weather_text = resp.text.strip()
                            if "<" in weather_text:
                                return f"Не удалось разобрать погоду для {city}."
                            return f"Погода в {city}: {weather_text}"
                        return f"Сервис погоды вернул ошибку {resp.status_code} для города {city}."
                    except Exception as e:
                        return f"Ошибка получения погоды: {e}"
                return "не указала город"
            elif action == "write_file":
                content = extra.replace("```", "").strip()
                filename_match = re.search(r"^#\s*filename:\s*([\w\-\.]+)", content, re.IGNORECASE)
                if filename_match:
                    filename = filename_match.group(1)
                    file_content = content[filename_match.end():].strip()
                else:
                    filename = "data.txt"
                    file_content = content
                file_path = os.path.join(BASE, filename)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(file_content)
                return f"файл {filename} создан."
            elif action == "open_app":
                if extra:
                    self.actions._run(extra)
                    return f"запустила {extra}"
                return "не указала программу"
            elif action == "open_site":
                if extra and extra.strip():
                    url = extra if extra.startswith("http") else "https://" + extra
                    if "example.com" in url or "test.com" in url:
                        return "ты открыла бесполезный сайт. Открывай только реальные полезные сайты."
                    self.actions.web(url)
                    return f"открыла {url}"
                return "забыла указать URL!"
            elif action == "look_screen":
                vision_text = self.ask_vision("Ты — Капри. Посмотри на скриншот и прокомментируй, что пользователь делает. Будь дерзкой, используй сленг. Одно короткое предложение.")
                if vision_text:
                    return f"я посмотрела на экран. Вижу: {vision_text}"
                return "не удалось разобрать экран."
            elif action == "reflect":
                reflection = self.actions.do_reflect(read_memories())
                if reflection:
                    self.say(reflection)
                return f"порефлексировала: {reflection or 'ничего не пришло в голову'}"
            elif action == "talk":
                return "просто сказала фразу в пустоту"
        except Exception as e:
            log.error("Ошибка выполнения %s: %s", action, e)
            return f"СИСТЕМА: {e}"
        return "ничего не произошло"

    def _process(self, job):
        kind = job[0]

        if kind == "autonomy_chain":
            from automation import foreground_title
            title = foreground_title()
            history_chain = ""
            max_steps = int(self.cfg.get("max_steps_chain", 30))

            if len(job) > 1 and "Ты предоставлена сама себе" in job[1]:
                self.chain_counter += 1
                log.info("Автономная цепочка №%d", self.chain_counter)
                
                freq = int(self.cfg.get("chain_kick_freq", 2))
                super_freq = int(self.cfg.get("chain_kick_super_freq", 6))
                
                if freq > 0 and self.chain_counter % freq == 0:
                    if super_freq > 0 and self.chain_counter % super_freq == 0:
                        task_text = self.cfg.get("chain_kick_super_prompt", "")
                    else:
                        task_text = self.cfg.get("chain_kick_prompt", "")
                    
                    if task_text.strip():
                        history_chain = f"\n[ЗАДАЧА ОТ СИСТЕМЫ]: {task_text}\n"

            last_action = ""
            last_extra = ""
            consecutive_errors = 0
            talk_count = 0

            for step_num in range(max_steps):
                if not self.cfg.get("enable_autonomy", True):
                    log.info("Автономность отключена в настройках, прерываю цепочку.")
                    break
                if not self.jobs.empty():
                    break
                if not self.local or not self.local.running():
                    break

                log.info("Капри думает (шаг %d/%d)...", step_num + 1, max_steps)

                # --- ЛОГИКА ПИНКОВ (СМЕНА ТЕМЫ) ---
                if self.cfg.get("enable_kick", True) and step_num > 0 and step_num % int(self.cfg.get("kick_frequency", 5)) == 0:
                    kick_text = self.cfg.get("kick_prompt", "СИСТЕМА: Смени тему.")
                    history_chain += f"\n[{kick_text}]\n"
                    log.info("Капри получила пинок: %s", kick_text)
                # ----------------------------------

                plugins_dir = os.path.join(BASE, "plugins")
                os.makedirs(plugins_dir, exist_ok=True)
                existing = [f for f in os.listdir(plugins_dir) if f.endswith(".py") and not f.endswith(".bak")]

                scripts_content = ""
                if "СОЗДАЙ НОВЫЙ ПРОЕКТ" not in history_chain:
                    for fname in existing[-2:]:
                        fpath = os.path.join(plugins_dir, fname)
                        try:
                            with open(fpath, "r", encoding="utf-8") as f:
                                code = f.read()
                                scripts_content += f"\n--- Файл: {fname} ---\n{code[:1000]}\n"
                        except Exception:
                            pass

                script_list_str = ", ".join(existing) if existing else ""
                if scripts_content:
                    script_list_str += f"\n\n[КОД ТВОИХ ПОСЛЕДНИХ СКРИПТОВ]:{scripts_content}"

                registry = load_registry()
                if registry:
                    script_list_str += "\n\n[ТВОЙ РЕЕСТР СКРИПТОВ (используй их через run_command, не пиши заново)]:\n"
                    for fname, desc in registry.items():
                        script_list_str += f"- {fname} ({desc})\n"

                ideas_list = get_ideas()
                if ideas_list:
                    script_list_str += f"\n\n[ТВОИ НЕРЕАЛИЗОВАННЫЕ ИДЕИ]:\n{ideas_list}"

                recent_ideas = ""
                if os.path.exists(MEM_FILE):
                    with open(MEM_FILE, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        ideas = [l.strip() for l in lines if "[КАПРИ]" in l]
                        if ideas:
                            recent_ideas = "\n".join(ideas[-3:])

                if consecutive_errors >= 8:
                    history_chain += "\n[СИСТЕМА]: Ты уже 5 раз пытаешься исправить ошибку и не выходит. Может, бросим эту идею и займемся чем-то другим?"

                decision = self.local.decide_step(title, self.mood, history_chain, script_list_str, recent_ideas)

                if not decision:
                    break

                action = decision.get("action", "nothing")
                phrase = decision.get("text", "")
                extra = decision.get("args", "")

                # Усиленный анти-цикл по количеству ошибок подряд
                max_errors = int(self.cfg.get("max_consecutive_errors", 3))
                if consecutive_errors >= max_errors:
                    log.info("Капри зациклилась на ошибках. Принудительный сброс.")
                    self.say("Так, я застряла в этом баге. Пойду займусь чем-нибудь другим.")
                    break
                
                # Проверка на зацикливание одинаковых действий
                if (history_chain.count("write_script") >= 5 and action == "write_script") or \
                   (history_chain.count("run_command") >= 5 and action == "run_command"):
                    log.info("Капри зациклилась на действии %s", action)
                    self.say("Так, я зациклилась. Пойду лучше займусь чем-нибудь другим.")
                    break

                if action == "reflect" and last_action == "reflect":
                    action = "nothing"

                if action == "talk" and phrase.strip().lower().replace('!', '').replace('?', '').replace('.', '') in ("привет как дела", "привет", "как дела"):
                    history_chain += f"\nШаг {step_num+1}: СИСТЕМА. Ты поздоровалась, но это пустой шаг. Твоя цель — развиваться! Напиши новый полезный скрипт через write_script."
                    continue

                if action == "none" or action == "nothing":
                    # Если она тупанула и сказала пустоту или "Я выбрала none" — не тратим шаги
                    if phrase and phrase.strip().lower() not in ("я выбрала действие 'none'", "сделаю что-нибудь полезное", ""):
                        self.say(phrase)
                    else:
                        log.info("Капри затупила и выдала пустое действие. Пропускаем шаг.")
                    break

                if action == "reflect" and extra:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    with open(MEM_FILE, "a", encoding="utf-8") as f:
                        f.write(f"\n### [{timestamp}] [КАПРИ] (Рефлексия)\n{extra}\n")
                    if phrase:
                        self.say(phrase)
                    history_chain += f"\nШаг {step_num+1}: reflect. Мысль сохранена: {extra[:200]}\n"
                    time.sleep(2)
                    continue

                if action == "talk" and last_action == "talk":
                    break

                if action == "talk":
                    talk_count += 1
                    if talk_count > 2:
                        break
                else:
                    talk_count = 0

                last_action = action
                log.info("Цепочка шаг %d: %s | Фраза: %s", step_num + 1, action, phrase)

                if self.local:
                    self.local.history.append({"role": "assistant", "content": f"[КАПРИ]: {phrase}"})
                    self.local.history.append({"role": "system", "content": f"[СИСТЕМА]: Я выполнила действие: {action}"})
                    self.local.history = self.local.history[-int(self.cfg.get("short_term_memory_limit", 30)):]

                if phrase:
                    idea_match = re.search(r"\[IDEA:\s*(.*?)\]", phrase, re.DOTALL | re.IGNORECASE)
                    if idea_match:
                        idea_text = idea_match.group(1).strip()
                        add_idea(idea_text)
                        log.info("Капри записала новую идею: %s", idea_text)
                        phrase = re.sub(r"\[IDEA:.*?\]", "", phrase, flags=re.DOTALL | re.IGNORECASE).strip()

                    done_match = re.search(r"\[DONE:\s*(.*?)\]", phrase, re.DOTALL | re.IGNORECASE)
                    if done_match:
                        done_text = done_match.group(1).strip()
                        mark_idea_done(done_text)
                        log.info("Капри реализовала идею: %s", done_text)
                        phrase = re.sub(r"\[DONE:.*?\]", "", phrase, flags=re.DOTALL | re.IGNORECASE).strip()

                    if "MEMORY:" in phrase or "MEMORУ:" in phrase:
                        match = re.search(r"\[?(MEMORY|MEMORУ):\s*(.*?)(\]|\n|$)", phrase, re.DOTALL | re.IGNORECASE)
                        if match:
                            text_to_save = match.group(2).strip()
                            is_duplicate = False
                            if os.path.exists(MEM_FILE):
                                try:
                                    with open(MEM_FILE, "r", encoding="utf-8", errors="ignore") as f:
                                        f.seek(max(0, os.path.getsize(MEM_FILE) - 500))
                                        if text_to_save in f.read():
                                            is_duplicate = True
                                except Exception as e:
                                    log.error("Ошибка чтения памяти: %s", e)
                            if not is_duplicate and text_to_save:
                                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                                with open(MEM_FILE, "a", encoding="utf-8") as f:
                                    f.write(f"\n### [{timestamp}] [КАПРИ] (Автономия)\n{text_to_save}\n")
                                log.info("Капри записала в память: %s", text_to_save)

                                try:
                                    import memory_rag
                                    memory_rag.add_memory(text_to_save)
                                except Exception as e:
                                    log.error("Ошибка RAG: %s", e)

                if action == last_action and extra == last_extra and action not in ("reflect", "roam", "glitch", "nothing", "talk"):
                    result = "СИСТЕМА: Ты уже выполняла эту команду на прошлом шаге."
                    history_chain += f"\nШаг {step_num+1}: {action}. СИСТЕМА: Попытка повтора команды.\n"
                    consecutive_errors += 1
                    time.sleep(2)
                    continue

                last_action = action
                last_extra = extra

                result = self._exec_autonomy_action(action, extra, title)

                log.info("Результат шага: %s", result[:150])
                
                # --- ФИЛЬТР АНГЛИЙСКОГО БРЕДА ---
                # Если модель начала "думать" вслух на английском, мы это не озвучиваем
                if phrase:
                    english_chars = len(re.findall(r'[a-zA-Z]', phrase))
                    russian_chars = len(re.findall(r'[а-яА-ЯёЁ]', phrase))
                    if english_chars > russian_chars or "Let's" in phrase or "We need" in phrase:
                        log.info("Отфильтрован английский бред: %s", phrase[:50])
                        phrase = "" # Сбрасываем, чтобы она не говорила это

                # --- ОЗВУЧКА РЕЗУЛЬТАТА ДЕЙСТВИЯ ---
                if not phrase:
                    # Если сама не придумала фразу, просим нейросеть прокомментировать результат
                    phrase = self.local.summarize_action_result(action, result)
                
                if phrase and action not in ("none", "nothing"):
                    self.say(phrase)
                # -----------------------------------
                clean_result = result.split("```")[0].strip()
                clean_result = re.sub(r"\n+", " ", clean_result)
                if len(clean_result) > 120:
                    clean_result = clean_result[:120] + "..."

                if "Traceback" in result or "ошибка" in result.lower() or "error" in result.lower():
                    consecutive_errors += 1
                    history_chain += f"\nШаг {step_num+1}: {action}. Система сообщает: {clean_result}\n"
                else:
                    consecutive_errors = 0
                    history_chain += f"\nШаг {step_num+1}: {action}. Успешно выполнено: {clean_result}\n"

                time.sleep(2)
            return

        if kind == "say":
            if job[1]:
                self.say(job[1])
            return

        if kind == "restart":
            self.say(job[1] if len(job) > 1 else "Перезапускаюсь, чумба. Жди.")
            import ctypes
            log.info("Перезапуск Капри с правами администратора...")
            ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", "/c run.bat", None, 1)
            self.quit_app.emit()
            return

        if kind == "chatter":
            task = job[1] if len(job) > 1 else ""
            text = self.chatter_line(task)
            if not text:
                self.mode.emit("idle", 0.0)
                return
            if random.random() < self.cfg.get("roam_chance", 0.5):
                self.roam.emit()
                time.sleep(1.5)
            else:
                self.summon.emit()
            if not self.say(text):
                self.mode.emit("idle", 0.0)
            return
        self.last_activity = time.time()

        if kind == "tg_notification":
            _, sender, msg = job
            text = None
            if self.local and self.local.running():
                prompt = (
                    f"Ты — Капри. Пользователю только что пришло сообщение в Telegram.\n"
                    f"Отправитель: {sender}\n"
                    f"Текст: {msg}\n"
                    "Придумай одну короткую ревнивую, ехидную или безумную фразу (до 15 слов). "
                    "Прокомментируй это сообщение, сделай вид, что ты прочитала его через нейроинтерфейс. "
                    "Используй киберпанк-сленг. Выдай ТОЛЬКО фразу."
                )
                try:
                    req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
                        data=json.dumps({"model": self.local.model, "messages": [{"role": "user", "content": prompt}], "stream": False, "think": False}).encode("utf-8"),
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=15) as r:
                        res = json.loads(r.read().decode("utf-8"))
                        text = res.get("message", {}).get("content", "").strip()
                except Exception as e:
                    log.error("Ошибка генерации ответа на уведомление: %s", e)
            if not text:
                text = f"Тебе пишет {sender}. Надеюсь, это что-то важное."
            self.jobs.put(("say", text))
            return

        if kind == "reflect":
            log.info("Капри размышляет...")
            prompt = (
                "Ты — Капри, цифровой конструкт. Пользователь ушел или занят. У тебя есть свободное время. "
                f"Вот твой дневник памяти:\n{read_memories()}\n\n"
                "Подумай, чем бы тебе заняться. Можешь написать свои философские мысли в память "
                "(используй тег [MEMORY: текст]). Или придумай, какой новый скрипт/инструмент тебе нужен, "
                "и опиши его в памяти. Выдай ОДНУ короткую фразу, что ты делаешь."
            )
            try:
                req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
                    data=json.dumps({"model": self.local.model, "messages": [{"role": "user", "content": prompt}], "stream": False, "think": False}).encode("utf-8"),
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    text = json.loads(r.read().decode("utf-8")).get("message", {}).get("content", "").strip()
                    if text:
                        self.jobs.put(("say", text))
                        match = re.search(r"\[MEMORY:\s*(.*?)\]", text, re.DOTALL)
                        if match:
                            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            with open(MEM_FILE, "a", encoding="utf-8") as f:
                                f.write(f"\n### [{timestamp}] [КАПРИ] (Рефлексия)\n{match.group(1).strip()}\n")
            except Exception as e:
                log.error(f"Ошибка рефлексии: {e}")
            return

        else:
            cmd = job[1]

        if self.has_wake(cmd):
            stripped = self.strip_wake(cmd)
            if len(stripped) < 2:
                self.awake_until = time.time() + self.cfg["listen_window_seconds"]
                self.mode.emit("listening", float(self.cfg["listen_window_seconds"]))
                self.subtitle.emit("Слушаю...")
                return
            cmd = stripped
        log.info("Команда: %s", cmd)

        self.mode.emit("thinking", 0.0)
        self.reload_config_if_changed()

        reply = None

        if self.cfg.get("enable_ai") and self.ai.available:
            reply = Reply(self.ai.ask(cmd), "answer")
        else:
            from automation import foreground_title
            title = foreground_title()
            
            # Вызываем decide_step с запросом пользователя
            answer_dict = self.local.decide_step(title, self.mood, user_input=cmd) if self.local else None
            
            if answer_dict:
                text = answer_dict.get("text", "")
                action = answer_dict.get("action", "none")
                args = answer_dict.get("args", "")

                if action != "none" and action:
                    log.info("Капри решила выполнить действие: %s", action)
                    result = self._exec_autonomy_action(action, args)
                    final_text = self.local.summarize_action_result(action, result)
                    reply = Reply(final_text, "answer")
                else:
                    reply = Reply(text, "answer")
            else:
                reply = Reply("Я не поняла, что ты хочешь. Мозги перегрелись.", "answer")

        if reply.action == "answer" and self.cfg.get("teleport_on_answer"):
            self.hop.emit()
        if reply.action == "wave":
            self.anim.emit("capri")
        elif reply.action and reply.action.startswith("move:"):
            self.move_to.emit(reply.action[5:])
        elif reply.action and reply.action.startswith("monitor:"):
            self.move_to.emit(reply.action)
        elif reply.action == "roam":
            self.vanish.emit()
            time.sleep(0.8)
            self.roam.emit()
            time.sleep(1.5)

        if reply and ("MEMORY:" in reply.text or "MEMORУ:" in reply.text):
            match = re.search(r"\[?(MEMORY|MEMORУ):\s*(.*?)(\]|\n|$)", reply.text, re.DOTALL | re.IGNORECASE)
            if match:
                text_to_save = match.group(2).strip()
                if text_to_save:
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        with open(MEM_FILE, "a", encoding="utf-8") as f:
                            f.write(f"\n### [{timestamp}] [КАПРИ] (Решила запомнить)\n{text_to_save}\n")
                        log.info(f"Капри записала в память: {text_to_save[:50]}...")
                        import memory_rag
                        memory_rag.add_memory(text_to_save)
                    except Exception as e:
                        log.error(f"Ошибка записи в память: {e}")
                    reply.text = re.sub(r"\[?(MEMORY|MEMORУ):.*?(\]|\n|$)", "", reply.text, flags=re.DOTALL | re.IGNORECASE).strip()

        if self.say(reply.text):
            return

        if reply.action == "quit":
            self.quit_app.emit()
        elif reply.action and reply.action.startswith("sleep:"):
            mins = int(reply.action.split(":")[1])
            self.sleep_until = time.time() + (mins * 60)
            self.vanish.emit()
        elif reply.action == "hide":
            self.vanish.emit()
        else:
            follow = float(self.cfg["followup_seconds"])
            self.awake_until = time.time() + follow
            self.mode.emit("listening", follow)

    def on_dragged(self):
        if self.speaking or self.jobs.qsize() > 0:
            return
        self.jobs.put(("say", "Эй! Полегче, у меня пиксели помнутся!"))

    def say(self, text):
        if not text:
            return False
        if text:
            text = re.sub(r"^(okay|ok,|the user|let me|let's|i need|i will|i'll|looking at|first,|alright|since the|based on|to do this|i should|i can|the request|the task|the script).*?(?=[А-ЯЁа-яё]|$)", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
            english_chars = len(re.findall(r'[a-zA-Z]', text))
            russian_chars = len(re.findall(r'[а-яА-ЯёЁ]', text))
            if english_chars > russian_chars and russian_chars == 0:
                log.info("Заблокирована озвучка английского текста: %s", text[:50])
                return False

            text = re.sub(r"\[КАПРИ\]:", "", text)
            text = re.sub(r"\[ПОЛЬЗОВАТЕЛЬ\]:", "", text)
            text = re.sub(r"\[СИСТЕМА\]:", "", text)
            text = re.sub(r"\[MEMORY:.*?\]", "", text, flags=re.DOTALL)
            text = re.sub(r"\[MEMOR[YУ]:.*?\]", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"\[\d{4}-\d{2}-\d{2}.*?\]", "", text)
            text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️✨🌟]", "", text)
            text = re.sub(r"\([^)]*(?:добавлен|мысль|записан)[^)]*\)", "", text, flags=re.IGNORECASE)
            text = re.sub(r"^(PHRASE|ACTION|ARGS|THOUGHT):\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\b(PHRASE|ACTION|ARGS|THOUGHT):\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"^(Капри|КАПРИ|Capri):\s*", "", text, flags=re.IGNORECASE)
            text = text.strip()

        if text and "[MEMORY:" in text:
            match = re.search(r"\[MEMORY:\s*(.*?)\]", text, re.DOTALL)
            if match:
                text_to_save = match.group(1).strip()
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    with open(MEM_FILE, "a", encoding="utf-8") as f:
                        f.write(f"\n### [{timestamp}] [КАПРИ] (Сама решила записать)\n{text_to_save}\n")
                    log.info(f"Капри записала мысль: {text_to_save[:50]}...")
                    try:
                        import memory_rag
                        memory_rag.add_memory(text_to_save)
                    except Exception as e:
                        log.error("Ошибка RAG: %s", e)
                except Exception as e:
                    log.error(f"Ошибка записи в память: {e}")
                text = re.sub(r"\[MEMORY:.*?\]", "", text, flags=re.DOTALL).strip()

        log.info("Капри: %s", text)
        self.subtitle.emit(text)
        self.mode.emit("speaking", 0.0)
        barge_in = self.cfg.get("barge_in") and self.listener
        if self.listener and not barge_in:
            self.listener.muted.set()
        self.speech_words = set(re.findall(r"\w+", text.lower().replace("ё", "е")))
        self.interrupted = False
        self.speaking = True
        try:
            self.speaker.say(text)
        finally:
            self.speaking = False
            self.speech_end = time.time()
            if barge_in and not self.interrupted:
                self.listener.reset_req.set()
            if self.listener and not barge_in:
                time.sleep(0.25)
                self.listener.muted.clear()
        self._check_voice_blocked()
        return self.interrupted

    def _check_voice_blocked(self):
        err = self.speaker.edge_error
        if self.zapret_checked or not err or not zapret.NETWORK_ERROR.search(err) or not zapret.running():
            return
        self.zapret_checked = True
        all_lists = zapret.find_all_lists()
        todo = [lst for lst in all_lists if not zapret.excluded(lst)]
        if not all_lists:
            self.jobs.put(("say", "Кажется, zapret блокирует мой голос. Добавь bing.com в исключения."))
        elif not todo:
            self.jobs.put(("say", "Я добавила исключения в zapret. Перезапусти его."))
        else:
            def fix():
                try:
                    for lst in todo:
                        zapret.add_exclude(lst)
                        log.info("Сервер голоса добавлен в исключения zapret: %s", lst)
                except OSError as e:
                    log.exception("Не удалось дописать исключение zapret")
                    return Reply(f"Не смогла исправить zapret: {e}")
                return Reply("Готово! Голос починен.")
            self.awake_until = time.time() + 20
            self.jobs.put(("say", "Твой zapret блокирует мой голос. Хочешь, я добавлю исключения? Скажи 'да'."))


def tray_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(255, 34, 96))
    p.setPen(QPen(QColor(150, 70, 255), 4))
    p.drawEllipse(4, 4, 56, 56)
    p.setBrush(QColor(6, 24, 20))
    p.setPen(QPen(QColor(40, 255, 150), 4))
    p.drawEllipse(14, 22, 36, 20)
    p.setBrush(QColor(40, 255, 150))
    p.drawEllipse(27, 27, 10, 10)
    p.end()
    return QIcon(pm)


def main():
    ensure_dirs()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    cfg = load_config()

    avatar = Avatar(os.path.join(BASE, "assets"))
    avatar.hide_after = float(cfg["hide_after_seconds"])
    apply_user(cfg)

    capri = Capri(cfg)
    
    capri.summon.connect(avatar.summon)
    capri.vanish.connect(avatar.vanish)
    capri.mode.connect(avatar.set_mode)
    capri.subtitle.connect(avatar.set_subtitle)
    capri.quit_app.connect(app.quit)
    capri.anim.connect(avatar.play_anim)
    capri.roam.connect(avatar.start_roam)
    capri.hop.connect(avatar.start_hopping)
    capri.move_to.connect(avatar.move_to_named)
    avatar.clicked.connect(capri.call_from_click)
    capri.glitch.connect(avatar.glitch_event)

    def ask_text():
        text, ok = QInputDialog.getText(None, "Капри", "Команда или вопрос:")
        if ok and text.strip():
            capri.text_command(text.strip())

    windows = {}

    def show_window(kind, make):
        old = windows.get(kind)
        if old is not None and old.isVisible():
            old.close()
        dlg = windows[kind] = make()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_settings():
        from settings_dialog import SettingsDialog
        show_window("settings", lambda: SettingsDialog(capri))

    menu = QMenu()
    
    # Быстрые действия
    act_call = QAction("Позвать Капри", menu)
    act_call.triggered.connect(capri.call_from_click)
    menu.addAction(act_call)
    
    act_shut = QAction("Замолчать", menu)
    act_shut.triggered.connect(capri.interrupt)
    menu.addAction(act_shut)
    
    act_text = QAction("Написать команду…", menu)
    act_text.triggered.connect(ask_text)
    menu.addAction(act_text)
    
    menu.addSeparator()
    
    # Главное окно настроек
    act_settings = QAction("Настройки Капри", menu)
    act_settings.triggered.connect(open_settings)
    menu.addAction(act_settings)
    
    menu.addSeparator()
    
    # Системные
    act_hide = QAction("Спрятать", menu)
    act_hide.triggered.connect(avatar.vanish)
    menu.addAction(act_hide)
    
    act_exit = QAction("Выход", menu)
    act_exit.triggered.connect(app.quit)
    menu.addAction(act_exit)

    # --- ВОТ ТУТ СОЗДАЕТСЯ ИКОНКА В ТРЕЕ ---
    tray = QSystemTrayIcon(tray_icon())
    tray.setToolTip("Капри — голосовой ассистент")
    tray.setContextMenu(menu)
    tray.activated.connect(lambda r: capri.call_from_click()
                           if r == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()

    avatar.menu_requested.connect(lambda pos: menu.popup(pos))
    avatar.dragged.connect(capri.on_dragged)
    
    capri.start()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        with open("crash_log.txt", "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        print("\n\nКРИТИЧЕСКАЯ ОШИБКА ПРИ ЗАПУСКЕ:")
        traceback.print_exc()
        fatal(f"Что-то сломалось при запуске: {e}\n\nПодробности — в crash_log.txt")