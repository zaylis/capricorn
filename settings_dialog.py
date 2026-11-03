"""Окно настроек Капри: максимальная кастомизация."""
import json
import os
import main
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel, 
                               QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox, QSlider, QTextEdit, 
                               QComboBox, QCheckBox, QRadioButton, QButtonGroup, QScrollArea, 
                               QFormLayout, QMessageBox, QGroupBox)
import shutil
from entries_dialog import STYLE
from persona import CHARACTER, SPEECH_RULES 
from local_ai import DEFAULT_AGENT_PROMPT
import logging
from voice import Speaker

log = logging.getLogger("capri")

PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")
os.makedirs(PROFILES_DIR, exist_ok=True)

class SettingsDialog(QDialog):
    def __init__(self, capri):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint)
        self.capri = capri
        self.setWindowTitle("Капри — Настройки")
        self.setStyleSheet(STYLE)
        self.resize(800, 700)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        self.tab_profiles = QWidget()
        self.setup_profiles_tab()
        self.tabs.insertTab(0, self.tab_profiles, "Профили")

        self.tab_ai = QWidget()
        self.setup_ai_tab()
        self.tabs.addTab(self.tab_ai, "Нейросеть")

        self.tab_behavior = QWidget()
        self.setup_behavior_tab()
        self.tabs.addTab(self.tab_behavior, "Поведение")

        self.tab_kicks = QWidget()
        self.setup_kicks_tab()
        self.tabs.addTab(self.tab_kicks, "Пинки и Лимиты")

        self.tab_sound = QWidget()
        self.setup_sound_tab()
        self.tabs.addTab(self.tab_sound, "Звук")

        self.tab_pers = QWidget()
        self.setup_pers_tab()
        self.tabs.addTab(self.tab_pers, "Персонализация")

        self.tab_prompts = QWidget()
        self.setup_prompts_tab()
        self.tabs.addTab(self.tab_prompts, "Промпты")

        self.tab_paths = QWidget()
        self.setup_paths_tab()
        self.tabs.addTab(self.tab_paths, "Программы и Сайты")

        self.tab_vision = QWidget()
        self.setup_vision_tab()
        self.tabs.addTab(self.tab_vision, "Зрение")

        self.tab_system = QWidget()
        self.setup_system_tab()
        self.tabs.addTab(self.tab_system, "Система")

        self.tab_backup = QWidget()
        self.setup_backup_tab()
        self.tabs.addTab(self.tab_backup, "Бэкапы")

        layout.addWidget(self.tabs)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        btn_save = QPushButton("Сохранить всё")
        btn_save.clicked.connect(self.save_settings)
        bottom_layout.addWidget(btn_save)
        
        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.close)
        bottom_layout.addWidget(btn_close)
        
        layout.addLayout(bottom_layout)

    # ---------------- ВКЛАДКА 0: ПРОФИЛИ ----------------
    def setup_profiles_tab(self):
        layout = QVBoxLayout(self.tab_profiles)
        
        layout.addWidget(QLabel("<b>Управление профилями настроек</b>"))
        info = QLabel("Ты можешь сохранять текущие настройки как отдельный профиль (например, 'Работа', 'Игры', 'Хакер')\n"
                      "и мгновенно переключаться между ними.")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(10)

        # Блок загрузки
        layout.addWidget(QLabel("<b>Загрузить профиль:</b>"))
        row_load = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.refresh_profiles() # Заполняем список при открытии
        row_load.addWidget(self.profile_combo)
        
        btn_load = QPushButton("Загрузить")
        btn_load.clicked.connect(self.load_profile)
        row_load.addWidget(btn_load)
        
        btn_delete = QPushButton("Удалить")
        btn_delete.clicked.connect(self.delete_profile)
        row_load.addWidget(btn_delete)
        layout.addLayout(row_load)

        layout.addSpacing(20)

        # Блок сохранения
        layout.addWidget(QLabel("<b>Сохранить текущие настройки как новый профиль:</b>"))
        row_save = QHBoxLayout()
        self.new_profile_input = QLineEdit()
        self.new_profile_input.setPlaceholderText("Введи название (например: Работа)")
        row_save.addWidget(self.new_profile_input)
        
        btn_save_as = QPushButton("Сохранить как профиль")
        btn_save_as.clicked.connect(self.save_as_profile)
        row_save.addWidget(btn_save_as)
        layout.addLayout(row_save)

        layout.addStretch()

    def refresh_profiles(self):
        """Сканирует папку profiles и обновляет выпадающий список"""
        self.profile_combo.clear()
        if os.path.exists(PROFILES_DIR):
            for f in os.listdir(PROFILES_DIR):
                if f.endswith(".json"):
                    self.profile_combo.addItem(f[:-5]) # Убираем .json

    def load_profile(self):
        name = self.profile_combo.currentText()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Выбери профиль из списка!")
            return
            
        profile_path = os.path.join(PROFILES_DIR, f"{name}.json")
        config_path = os.path.join(os.path.dirname(PROFILES_DIR), "config.json")
        
        if os.path.exists(profile_path):
            try:
                # Копируем файл профиля поверх основного конфига
                shutil.copyfile(profile_path, config_path)
                
                # Применяем на лету
                self.capri.reload_config_if_changed(speak=False)
                
                QMessageBox.information(self, "Успех", f"Профиль '{name}' загружен и применён!\n\n"
                                                       f"Окно настроек сейчас закроется. Открой его снова, чтобы увидеть новые значения ползунков.")
                self.close() # Закрываем окно, чтобы пользователь открыл его заново со свежими данными
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить профиль: {e}")

    def save_as_profile(self):
        name = self.new_profile_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Напиши название профиля!")
            return
            
        try:
            # 1. Сначала пробуем сохранить настройки. Если упадет - мы поймаем ошибку.
            self.save_settings(close_window=False)
            
            # 2. Вычисляем пути (через BASE, чтобы наверняка)
            config_path = os.path.join(main.BASE, "config.json")
            profile_path = os.path.join(PROFILES_DIR, f"{name}.json")
            
            # 3. Проверяем, что config.json реально создался
            if not os.path.exists(config_path):
                raise FileNotFoundError(f"Файл config.json не найден по пути: {config_path}")
            
            # 4. Копируем
            import time
            time.sleep(0.2)
            shutil.copyfile(config_path, profile_path)
            
            # 5. Обновляем интерфейс
            self.refresh_profiles()
            self.new_profile_input.clear()
            self.profile_combo.setCurrentText(name) # Выделяем созданный профиль
            
            QMessageBox.information(self, "Успех", f"Профиль '{name}' сохранён в папку profiles!")
            
        except Exception as e:
            # Показываем РЕАЛЬНУЮ ошибку на экран
            import traceback
            error_details = traceback.format_exc()
            log.error(f"Ошибка сохранения профиля: {e}\n{error_details}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить профиль:\n{e}\n\nПодробности в логе.")

    def delete_profile(self):
        name = self.profile_combo.currentText()
        if not name:
            return
            
        profile_path = os.path.join(PROFILES_DIR, f"{name}.json")
        box = QMessageBox(QMessageBox.Icon.Question, "Удаление", f"Точно удалить профиль '{name}'?", parent=self)
        yes = box.addButton("Удалить", QMessageBox.ButtonRole.YesRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.NoRole)
        box.exec()
        
        if box.clickedButton() is yes:
            try:
                if os.path.exists(profile_path):
                    os.remove(profile_path)
                self.refresh_profiles()
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось удалить: {e}")

    # ---------------- ВКЛАДКА 1: НЕЙРОСЕТЬ ----------------
    def setup_ai_tab(self):
        layout = QVBoxLayout(self.tab_ai)
        
        # --- Выбор провайдера ---
        prov_layout = QHBoxLayout()
        prov_layout.addWidget(QLabel("<b>Провайдер (Мозги):</b>"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["Ollama (Локально)", "Claude API (Anthropic)", "OpenAI (ChatGPT)", "DeepSeek"])
        
        # Загружаем текущий
        current_prov = self.capri.cfg.get("provider", "ollama")
        if current_prov == "claude": self.provider_combo.setCurrentText("Claude API (Anthropic)")
        elif current_prov == "openai": self.provider_combo.setCurrentText("OpenAI (ChatGPT)")
        elif current_prov == "deepseek": self.provider_combo.setCurrentText("DeepSeek")
        else: self.provider_combo.setCurrentText("Ollama (Локально)")
        
        self.provider_combo.currentIndexChanged.connect(self.toggle_provider)
        prov_layout.addWidget(self.provider_combo)
        layout.addLayout(prov_layout)

        # --- Группа Ollama ---
        self.group_ollama = QGroupBox("Настройки Ollama")
        form_ollama = QFormLayout()
        self.model_input = QLineEdit(self.capri.cfg.get("local_model", "qwen3:8b"))
        form_ollama.addRow("Модель:", self.model_input)
        self.gpu_input = QSpinBox(); self.gpu_input.setRange(0, 99); self.gpu_input.setValue(int(self.capri.cfg.get("num_gpu", 24)))
        form_ollama.addRow("Слоев на GPU:", self.gpu_input)
        self.ctx_input = QSpinBox(); self.ctx_input.setRange(1024, 32768); self.ctx_input.setSingleStep(1024); self.ctx_input.setValue(int(self.capri.cfg.get("num_ctx", 8192)))
        form_ollama.addRow("Размер контекста:", self.ctx_input)
        self.predict_input = QSpinBox(); self.predict_input.setRange(100, 8192); self.predict_input.setSingleStep(100); self.predict_input.setValue(int(self.capri.cfg.get("num_predict", 4096)))
        form_ollama.addRow("Макс. токенов:", self.predict_input)
        self.group_ollama.setLayout(form_ollama)
        layout.addWidget(self.group_ollama)

        # --- Группа API (Общая для Claude, OpenAI, DeepSeek) ---
        self.group_api = QGroupBox("Настройки API")
        form_api = QFormLayout()
        self.api_key_input = QLineEdit(self.capri.cfg.get("api_key", ""))
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("sk-...")
        form_api.addRow("API Ключ:", self.api_key_input)
        
        self.api_model_input = QLineEdit(self.capri.cfg.get("api_model", "gpt-4o"))
        form_api.addRow("Модель API:", self.api_model_input)
        self.group_api.setLayout(form_api)
        layout.addWidget(self.group_api)

        # --- Общие настройки (Температура) ---
        form_common = QFormLayout()
        self.temp_input = QDoubleSpinBox(); self.temp_input.setRange(0.0, 2.0); self.temp_input.setSingleStep(0.1); self.temp_input.setValue(float(self.capri.cfg.get("temperature", 0.7)))
        form_common.addRow("Температура (Креативность):", self.temp_input)
        self.memory_limit_spin = QSpinBox()
        self.memory_limit_spin.setRange(5, 100)
        self.memory_limit_spin.setValue(int(self.capri.cfg.get("short_term_memory_limit", 30)))
        form_common.addRow("Сообщений в краткосрочной памяти:", self.memory_limit_spin)
        layout.addLayout(form_common)
        
        # Режим поиска в памяти
        self.memory_mode_combo = QComboBox()
        self.memory_mode_combo.addItems(["auto", "rag", "keyword"])
        self.memory_mode_combo.setCurrentText(self.capri.cfg.get("memory_search_mode", "auto"))
        form_common.addRow("Поиск в памяти:", self.memory_mode_combo)

        self.toggle_provider()

        # --- Свои правила ---
        group_rules = QGroupBox("Свои правила (Анти-тупость)")
        rules_layout = QVBoxLayout()
        rules_layout.addWidget(QLabel("Добавляются в конец промпта. Пример: 'ЗАПРЕЩЕНО писать скрипты для текста. Только игры!'"))
        self.custom_rules = QTextEdit()
        self.custom_rules.setText(self.capri.cfg.get("custom_rules", ""))
        self.custom_rules.setMinimumHeight(100)
        rules_layout.addWidget(self.custom_rules)
        group_rules.setLayout(rules_layout)
        layout.addWidget(group_rules)

    def toggle_provider(self):
        prov = self.provider_combo.currentText()
        is_ollama = "Ollama" in prov
        self.group_ollama.setVisible(is_ollama)
        self.group_api.setVisible(not is_ollama)
        
        if not is_ollama:
            if "Claude" in prov:
                self.api_model_input.setText("claude-3-5-sonnet-20241022")
            elif "OpenAI" in prov:
                self.api_model_input.setText("gpt-4o")
            elif "DeepSeek" in prov:
                self.api_model_input.setText("deepseek-chat")
            elif "Groq" in prov:
                self.api_model_input.setText("llama3-70b-8192")
            elif "OpenRouter" in prov:
                self.api_model_input.setText("anthropic/claude-3.5-sonnet")
            elif "Gemini" in prov:
                self.api_model_input.setText("gemini-1.5-pro")

    # ---------------- ВКЛАДКА 2: ПОВЕДЕНИЕ ----------------
    def setup_behavior_tab(self):
        layout = QVBoxLayout(self.tab_behavior)
        form = QFormLayout()

        self.chatter_min = QDoubleSpinBox(); self.chatter_min.setRange(0.1, 120.0); self.chatter_min.setValue(float(self.capri.cfg.get("chatter_min_minutes", 0.5)))
        form.addRow("Мин. минут до появления:", self.chatter_min)

        self.chatter_max = QDoubleSpinBox(); self.chatter_max.setRange(0.1, 120.0); self.chatter_max.setValue(float(self.capri.cfg.get("chatter_max_minutes", 1.0)))
        form.addRow("Макс. минут до появления:", self.chatter_max)

        self.roam_chance = QDoubleSpinBox(); self.roam_chance.setRange(0.0, 1.0); self.roam_chance.setSingleStep(0.1); self.roam_chance.setValue(float(self.capri.cfg.get("roam_chance", 0.8)))
        form.addRow("Шанс, что будет гулять (0-1):", self.roam_chance)

        # Блок автоскрытия
        self.chk_auto_hide = QCheckBox("Скрываться автоматически (если выключено — висит всегда)")
        hide_val = int(self.capri.cfg.get("hide_after_seconds", 60))
        self.chk_auto_hide.setChecked(hide_val > 0)
        form.addRow("", self.chk_auto_hide)

        self.hide_after = QSpinBox()
        self.hide_after.setRange(1, 9999999)
        self.hide_after.setValue(hide_val if hide_val > 0 else 60)
        self.hide_after.setEnabled(hide_val > 0) # Блокируем поле, если галочка не стоит
        self.chk_auto_hide.toggled.connect(self.hide_after.setEnabled)
        form.addRow("Прятаться через (сек):", self.hide_after)

        self.listen_window = QSpinBox(); self.listen_window.setRange(1, 30); self.listen_window.setValue(int(self.capri.cfg.get("listen_window_seconds", 8)))
        form.addRow("Слушать после имени (сек):", self.listen_window)

        layout.addLayout(form)

        self.chk_autonomy = QCheckBox("Разрешить автономные размышления (Self-Evolution)")
        self.chk_autonomy.setChecked(bool(self.capri.cfg.get("enable_autonomy", True)))
        layout.addWidget(self.chk_autonomy)

        self.autonomy_think = QDoubleSpinBox()
        self.autonomy_think.setRange(0.1, 120.0)
        self.autonomy_think.setSingleStep(0.5)
        self.autonomy_think.setValue(float(self.capri.cfg.get("autonomy_think_minutes", 2.0)))
        form.addRow("Начать размышлять после (минут):", self.autonomy_think)
        self.chk_chatter = QCheckBox("Появляться самой (автономность)"); self.chk_chatter.setChecked(bool(self.capri.cfg.get("chatter", True)))
        layout.addWidget(self.chk_chatter)
        self.chk_barge = QCheckBox("Можно перебивать голосом"); self.chk_barge.setChecked(bool(self.capri.cfg.get("barge_in", True)))
        layout.addWidget(self.chk_barge)
        self.chk_teleport = QCheckBox("Скакать молнией при ответе"); self.chk_teleport.setChecked(bool(self.capri.cfg.get("teleport_on_answer", True)))
        layout.addWidget(self.chk_teleport)
        layout.addStretch()

    # ---------------- ВКЛАДКА 3: ЗВУК ----------------
    def setup_sound_tab(self):
        layout = QVBoxLayout(self.tab_sound)
        
        # Громкость голоса
        layout.addWidget(QLabel("<b>Громкость голоса Капри:</b>"))
        row_vol = QHBoxLayout()
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100); self.vol_slider.setValue(int(self.capri.cfg.get("voice_volume", 100)))
        self.vol_lbl = QLabel(f"{self.vol_slider.value()}%")
        self.vol_slider.valueChanged.connect(lambda v: self.vol_lbl.setText(f"{v}%"))
        row_vol.addWidget(self.vol_slider)
        row_vol.addWidget(self.vol_lbl)
        layout.addLayout(row_vol)
        
        # Чувствительность микрофона
        layout.addWidget(QLabel("<b>Чувствительность микрофона:</b>"))
        row_sens = QHBoxLayout()
        self.sens_slider = QSlider(Qt.Orientation.Horizontal)
        self.sens_slider.setRange(0, 100); self.sens_slider.setValue(int(self.capri.cfg.get("mic_sensitivity", 100)))
        self.sens_lbl = QLabel(f"{self.sens_slider.value()}%")
        self.sens_slider.valueChanged.connect(lambda v: self.sens_lbl.setText(f"{v}%"))
        row_sens.addWidget(self.sens_slider)
        row_sens.addWidget(self.sens_lbl)
        layout.addLayout(row_sens)
        
        layout.addWidget(QLabel("<b>Движок озвучки:</b>"))
        self.tts_combo = QComboBox()
        self.tts_combo.addItems(["silero", "edge"])
        self.tts_combo.setCurrentText(self.capri.cfg.get("tts_engine", "silero"))
        layout.addWidget(self.tts_combo)

        # --- НОВЫЙ БЛОК: Тонкая настройка голоса ---
        group_voice = QGroupBox("Настройки конкретного движка")
        form_voice = QFormLayout()

        # Выбор имени голоса (теперь можно писать вручную!)
        self.voice_name_combo = QComboBox()
        self.voice_name_combo.setEditable(True) # <--- РАЗРЕШАЕМ ВВОДИТЬ ТЕКСТ
        form_voice.addRow("Имя голоса:", self.voice_name_combo)
        
        # Функция для обновления списка голосов при смене движка
        def update_voice_list():
            engine = self.tts_combo.currentText().lower()
            self.voice_name_combo.clear()
            if engine == "silero":
                self.voice_name_combo.addItems(["baya", "xenia", "kseniya", "aidar", "eugene"])
                self.voice_name_combo.setCurrentText(self.capri.cfg.get("silero_voice", "baya"))
            else:
                self.voice_name_combo.addItems(["ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural", "ru-RU-DariyaNeural"])
                self.voice_name_combo.setCurrentText(self.capri.cfg.get("voice", "ru-RU-SvetlanaNeural"))
                
        self.tts_combo.currentIndexChanged.connect(update_voice_list)
        update_voice_list() # Вызываем сразу при открытии окна

        # Скорость речи (для Edge)
        self.edge_rate_spin = QSpinBox()
        self.edge_rate_spin.setRange(-50, 50)
        self.edge_rate_spin.setSuffix("%")
        current_rate = self.capri.cfg.get("edge_rate", "+10%").replace("%", "").replace("+", "")
        try: self.edge_rate_spin.setValue(int(current_rate))
        except: self.edge_rate_spin.setValue(10)
        form_voice.addRow("Скорость речи (Edge):", self.edge_rate_spin)

        # Высота тона (для Edge)
        self.edge_pitch_spin = QSpinBox()
        self.edge_pitch_spin.setRange(-50, 50)
        self.edge_pitch_spin.setSuffix("Hz")
        current_pitch = self.capri.cfg.get("edge_pitch", "+15Hz").replace("Hz", "").replace("+", "")
        try: self.edge_pitch_spin.setValue(int(current_pitch))
        except: self.edge_pitch_spin.setValue(15)
        form_voice.addRow("Высота тона (Edge):", self.edge_pitch_spin)

        # Высота тона (для Silero)
        self.silero_pitch_combo = QComboBox()
        self.silero_pitch_combo.addItems(["x-low", "low", "medium", "high", "x-high"])
        self.silero_pitch_combo.setCurrentText(self.capri.cfg.get("silero_pitch", "high"))
        form_voice.addRow("Высота тона (Silero):", self.silero_pitch_combo)

        group_voice.setLayout(form_voice)
        layout.addWidget(group_voice)
        
        layout.addStretch()

        # ---------------- ПИНКИ И ЛИМИТЫ ----------------
    def setup_kicks_tab(self):
        layout = QVBoxLayout(self.tab_kicks)
        form = QFormLayout()

        layout.addWidget(QLabel("<b>Лимиты автономности:</b>"))
        
        self.max_errors_spin = QSpinBox()
        self.max_errors_spin.setRange(1, 20)
        self.max_errors_spin.setValue(int(self.capri.cfg.get("max_consecutive_errors", 3)))
        form.addRow("Ошибок до сброса (Анти-цикл):", self.max_errors_spin)

        layout.addSpacing(10)
        layout.addWidget(QLabel("<b>Пинки внутри одной цепочки (Смена темы):</b>"))
        
        self.chk_enable_kick = QCheckBox("Включить 'пинки'")
        self.chk_enable_kick.setChecked(bool(self.capri.cfg.get("enable_kick", True)))
        form.addRow("", self.chk_enable_kick)

        self.kick_freq_spin = QSpinBox()
        self.kick_freq_spin.setRange(1, 30)
        self.kick_freq_spin.setValue(int(self.capri.cfg.get("kick_frequency", 5)))
        form.addRow("Шагов до пинка:", self.kick_freq_spin)

        self.kick_prompt_edit = QTextEdit()
        self.kick_prompt_edit.setMaximumHeight(50)
        self.kick_prompt_edit.setText(self.capri.cfg.get("kick_prompt", ""))
        form.addRow("Текст пинка:", self.kick_prompt_edit)

        layout.addSpacing(10)
        layout.addWidget(QLabel("<b>Пинки между цепочками (Задача на новый проект):</b>"))
        
        self.chain_freq_spin = QSpinBox()
        self.chain_freq_spin.setRange(0, 50)
        self.chain_freq_spin.setValue(int(self.capri.cfg.get("chain_kick_freq", 2)))
        form.addRow("Обычный пинок каждые (цеп.):", self.chain_freq_spin)
        
        self.chain_prompt_edit = QTextEdit()
        self.chain_prompt_edit.setMaximumHeight(50)
        self.chain_prompt_edit.setText(self.capri.cfg.get("chain_kick_prompt", ""))
        form.addRow("Текст обычного пинка:", self.chain_prompt_edit)

        self.chain_super_freq_spin = QSpinBox()
        self.chain_super_freq_spin.setRange(0, 50)
        self.chain_super_freq_spin.setValue(int(self.capri.cfg.get("chain_kick_super_freq", 6)))
        form.addRow("Супер-пинок каждые (цеп.):", self.chain_super_freq_spin)
        
        self.chain_super_prompt_edit = QTextEdit()
        self.chain_super_prompt_edit.setMaximumHeight(50)
        self.chain_super_prompt_edit.setText(self.capri.cfg.get("chain_kick_super_prompt", ""))
        form.addRow("Текст супер-пинка:", self.chain_super_prompt_edit)

        self.max_steps_spin = QSpinBox()
        self.max_steps_spin.setRange(1, 100)
        self.max_steps_spin.setValue(int(self.capri.cfg.get("max_steps_chain", 30)))
        form.addRow("Макс. шагов в одной цепочке:", self.max_steps_spin)

        self.chk_allow_script = QCheckBox("Разрешить писать скрипты (write_script)")
        self.chk_allow_script.setChecked(bool(self.capri.cfg.get("allow_write_script", True)))
        form.addRow("", self.chk_allow_script)

        layout.addLayout(form)
        layout.addStretch()

    # ---------------- ВКЛАДКА 4: ПЕРСОНАЛИЗАЦИЯ ----------------
    def setup_pers_tab(self):
        layout = QVBoxLayout(self.tab_pers)
        layout.addWidget(QLabel("<b>Как тебя зовут?</b>"))
        self.name_input = QLineEdit(self.capri.cfg.get("user_name", ""))
        layout.addWidget(self.name_input)
        
        layout.addWidget(QLabel("<b>Твой пол:</b>"))
        self.gender_group = QButtonGroup()
        self.radio_male = QRadioButton("Мужской")
        self.radio_female = QRadioButton("Женский")
        self.gender_group.addButton(self.radio_male)
        self.gender_group.addButton(self.radio_female)
        if self.capri.cfg.get("user_gender") == "female": self.radio_female.setChecked(True)
        else: self.radio_male.setChecked(True)
        layout.addWidget(self.radio_male)
        layout.addWidget(self.radio_female)
        
        layout.addWidget(QLabel("<b>Слова-активаторы (через запятую):</b>"))
        self.wake_input = QLineEdit(", ".join(self.capri.cfg.get("wake_words", ["капри"])))
        layout.addWidget(self.wake_input)
        layout.addStretch()

    # ---------------- ВКЛАДКА 5: ПРОМПТЫ ----------------
    def _make_prompt_row(self, label_text, default_text, cfg_key):
        row = QHBoxLayout()
        lbl = QLabel(f"<b>{label_text}</b>")
        btn = QPushButton("Сбросить")
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(btn)
        edit = QTextEdit()
        edit.setMinimumHeight(100)
        edit.setText(self.capri.cfg.get(cfg_key, "") or default_text)
        btn.clicked.connect(lambda: edit.setText(default_text))
        return row, edit

    def setup_prompts_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        
        row_char, self.prompt_char = self._make_prompt_row("Характер:", CHARACTER, "prompt_character")
        layout.addLayout(row_char)
        layout.addWidget(self.prompt_char)
        
        row_speech, self.prompt_speech = self._make_prompt_row("Правила речи:", SPEECH_RULES, "prompt_speech")
        layout.addLayout(row_speech)
        layout.addWidget(self.prompt_speech)
        
        row_agent, self.prompt_agent = self._make_prompt_row("Промпт агента:", DEFAULT_AGENT_PROMPT, "prompt_agent")
        layout.addLayout(row_agent)
        layout.addWidget(self.prompt_agent)
        
        scroll.setWidget(content)
        tab_layout = QVBoxLayout(self.tab_prompts)
        tab_layout.addWidget(scroll)

    # ---------------- ВКЛАДКА 6: ПРОГРАММЫ ----------------
    def setup_paths_tab(self):
        layout = QVBoxLayout(self.tab_paths)
        layout.addWidget(QLabel("<b>Твои программы и сайты</b>"))
        
        info = QLabel(
            "Здесь ты можешь прописать точные пути к программам (например, C:\\\\Games\\\\game.exe)\n"
            "или сохранить свои любимые сайты.\n\n"
            "Капри будет использовать эти пути, когда ты попросишь её что-то открыть."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        
        btn_open_entries = QPushButton("Открыть редактор программ и сайтов...")
        btn_open_entries.setMinimumHeight(40)
        btn_open_entries.clicked.connect(self.open_entries)
        layout.addWidget(btn_open_entries)
        layout.addStretch()

    def open_entries(self):
        from entries_dialog import EntriesDialog
        self.capri.reload_config_if_changed(speak=False)
        EntriesDialog(self.capri.actions).exec()

    # ---------------- ВКЛАДКА 7: ЗРЕНИЕ ----------------
    def setup_vision_tab(self):
        layout = QVBoxLayout(self.tab_vision)
        form = QFormLayout()
        
        # 1. Галочка включения
        self.chk_vision = QCheckBox("Разрешить Капри использовать зрение (скриншоты)")
        self.chk_vision.setChecked(bool(self.capri.cfg.get("enable_vision", True)))
        form.addRow("", self.chk_vision)

        # 2. Выбор модели
        self.vision_model_input = QLineEdit(self.capri.cfg.get("vision_model", "minicpm-v"))
        form.addRow("Модель для зрения (Ollama):", self.vision_model_input)

        # 3. НОВОЕ: Качество скриншота (сжатие)
        self.vision_quality_spin = QSpinBox()
        self.vision_quality_spin.setRange(10, 100)
        self.vision_quality_spin.setValue(int(self.capri.cfg.get("vision_quality", 70)))
        form.addRow("Качество скриншота (%):", self.vision_quality_spin)

        # 4. НОВОЕ: Лимит слов при описании
        self.vision_tokens_spin = QSpinBox()
        self.vision_tokens_spin.setRange(10, 500)
        self.vision_tokens_spin.setValue(int(self.capri.cfg.get("vision_tokens", 80)))
        form.addRow("Макс. слов в описании:", self.vision_tokens_spin)
        
        layout.addLayout(form)
        
        hint = QLabel("Если включено, Капри сможет делать скриншоты и 'смотреть' на них через выбранную модель.\n"
                      "Рекомендуется minicpm-v (хорошо работает с русским языком).\n"
                      "Качество 70% — оптимально для скорости. Если поставить 100%, скриншоты будут тяжелее, и модель будет думать дольше.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()

    # ---------------- ВКЛАДКА 8: СИСТЕМА ----------------
    def setup_system_tab(self):
        layout = QVBoxLayout(self.tab_system)
        
        layout.addWidget(QLabel("<b>Уведомления:</b>"))
        self.chk_tg_notify = QCheckBox("Читать и комментировать уведомления Telegram")
        self.chk_tg_notify.setChecked(bool(self.capri.cfg.get("enable_tg_notify", True)))
        layout.addWidget(self.chk_tg_notify)
        
        self.tg_interval_spin = QSpinBox()
        self.tg_interval_spin.setRange(2, 60)
        self.tg_interval_spin.setValue(int(self.capri.cfg.get("tg_notify_interval", 10)))
        layout.addWidget(QLabel("Интервал проверки уведомлений (сек):"))
        layout.addWidget(self.tg_interval_spin)

        layout.addSpacing(20)
        layout.addWidget(QLabel("<b>Danger Zone (Опасная зона):</b>"))
        
        btn_open_plugins = QPushButton("Открыть папку plugins")
        btn_open_plugins.clicked.connect(lambda: os.startfile(os.path.join(os.path.dirname(__file__), "plugins")))
        layout.addWidget(btn_open_plugins)

        btn_open_log = QPushButton("Открыть capri.log (логи)")
        btn_open_log.clicked.connect(lambda: os.startfile(os.path.join(os.path.dirname(__file__), "capri.log")))
        layout.addWidget(btn_open_log)

        btn_open_memory = QPushButton("Открыть папку памяти (memory)")
        btn_open_memory.clicked.connect(lambda: os.startfile(os.path.join(os.path.dirname(__file__), "memory")))
        layout.addWidget(btn_open_memory)

        btn_open_history = QPushButton("Открыть файл истории (history.json)")
        btn_open_history.clicked.connect(lambda: os.startfile(os.path.join(os.path.dirname(__file__), "history.json")))
        layout.addWidget(btn_open_history)

        btn_clear_rag = QPushButton("Очистить векторную память (RAG)")
        btn_clear_rag.setStyleSheet("background: #5a2a50;")
        btn_clear_rag.clicked.connect(self.clear_rag_memory)
        layout.addWidget(btn_clear_rag)

        layout.addSpacing(10)

        btn_full_wipe = QPushButton("Полная очистка памяти")
        btn_full_wipe.setStyleSheet("background: #8b0000; color: white; font-weight: bold; padding: 5px;")
        btn_full_wipe.clicked.connect(self.full_memory_wipe)
        layout.addWidget(btn_full_wipe)

        layout.addStretch()

    def clear_rag_memory(self):
        box = QMessageBox(QMessageBox.Icon.Warning, "Очистка", "Точно удалить всю долговременную память? (memories.md останется, но база ChromaDB будет стерта)", parent=self)
        yes = box.addButton("Удалить", QMessageBox.ButtonRole.YesRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.NoRole)
        box.exec()
        
        if box.clickedButton() is yes:
            try:
                import memory_rag
                # Получаем все ID и удаляем их
                existing_data = memory_rag.collection.get()
                if existing_data and existing_data.get('ids'):
                    memory_rag.collection.delete(ids=existing_data['ids'])
                QMessageBox.information(self, "Успех", "Векторная база очищена. Текстовые файлы остались на месте.")
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось очистить: {e}")

    def full_memory_wipe(self):
        box = QMessageBox(QMessageBox.Icon.Warning, "Амнезия", 
                          "ВНИМАНИЕ! Это полностью сотрет ВСЕ воспоминания Капри:\n"
                          "- краткосрочную историю диалогов (history.json)\n"
                          "- дневник памяти (memories.md)\n"
                          "- список идей (ideas.md)\n"
                          "- векторную базу (ChromaDB)\n\n"
                          "Капри станет как новорожденная. Ты уверен?", parent=self)
        yes = box.addButton("СТЕРЕТЬ ВСЁ", QMessageBox.ButtonRole.YesRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.NoRole)
        box.exec()
        
        if box.clickedButton() is yes:
            import json
            import main
            
            base_dir = main.BASE
            
            try:
                # 1. Очищаем краткосрочную память
                hist_path = os.path.join(base_dir, "history.json")
                if os.path.exists(hist_path):
                    with open(hist_path, "w", encoding="utf-8") as f:
                        json.dump([], f) 
                        
                if hasattr(self.capri, "local") and self.capri.local:
                    self.capri.local.history = [] 
                    
                # 2. Очищаем долговременную память
                mem_dir = os.path.join(base_dir, "memory")
                if os.path.exists(mem_dir):
                    for f in ["memories.md", "ideas.md", "done.md"]:
                        fp = os.path.join(mem_dir, f)
                        if os.path.exists(fp):
                            open(fp, "w").close() 
                            
                # 3. Очищаем базу ChromaDB через её собственный API
                try:
                    import memory_rag
                    existing_data = memory_rag.collection.get()
                    if existing_data and existing_data.get('ids'):
                        memory_rag.collection.delete(ids=existing_data['ids'])
                except Exception as e:
                    # Если база не инициализирована или пуста, просто пропускаем
                    pass
                    
                QMessageBox.information(self, "Успех", "Память очищена! Текстовые файлы стерты, а векторная база обнулена.")
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось очистить память:\n{e}")
    
    # ---------------- ВКЛАДКА 9: БЭКАПЫ ----------------
    def setup_backup_tab(self):
        layout = QVBoxLayout(self.tab_backup)
        form = QFormLayout()

        self.chk_enable_backup = QCheckBox("Включить авто-бэкап при запуске")
        self.chk_enable_backup.setChecked(bool(self.capri.cfg.get("enable_backup", True)))
        form.addRow("", self.chk_enable_backup)

        self.backup_path_input = QLineEdit(self.capri.cfg.get("backup_dir", r"G:\Capri_Backups"))
        form.addRow("Папка для бэкапов (флешка):", self.backup_path_input)

        self.backup_max_count = QSpinBox()
        self.backup_max_count.setRange(1, 100)
        self.backup_max_count.setValue(int(self.capri.cfg.get("backup_max_count", 30)))
        form.addRow("Максимум архивов:", self.backup_max_count)

        layout.addLayout(form)
        
        info = QLabel("Капри делает бэкап всей папки проекта при каждом запуске.\n"
                      "Если указанной папки нет, бэкап сохранится в локальную папку 'backups/usb_backups'.")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addStretch()

    # ---------------- СОХРАНЕНИЕ ----------------
    def save_settings(self, close_window=True):
        from main import save_setting
        
        # 1. Провайдер
        prov = self.provider_combo.currentText()
        if "Ollama" in prov: save_setting("provider", "ollama"); save_setting("enable_ai", False)
        elif "Claude" in prov: save_setting("provider", "claude"); save_setting("enable_ai", True)
        elif "OpenAI" in prov: save_setting("provider", "openai"); save_setting("enable_ai", True)
        elif "DeepSeek" in prov: save_setting("provider", "deepseek"); save_setting("enable_ai", True)
        elif "Groq" in prov: save_setting("provider", "groq"); save_setting("enable_ai", True)
        elif "OpenRouter" in prov: save_setting("provider", "openrouter"); save_setting("enable_ai", True)
        elif "Gemini" in prov: save_setting("provider", "gemini"); save_setting("enable_ai", True)
        
        save_setting("api_key", self.api_key_input.text().strip())
        save_setting("api_model", self.api_model_input.text().strip())
        
        # 2. Ollama
        save_setting("local_model", self.model_input.text().strip())
        save_setting("num_gpu", self.gpu_input.value())
        save_setting("num_ctx", self.ctx_input.value())
        save_setting("num_predict", self.predict_input.value())
        save_setting("temperature", self.temp_input.value())
        save_setting("memory_search_mode", self.memory_mode_combo.currentText())
        
        # 3. Бэкапы
        save_setting("enable_backup", self.chk_enable_backup.isChecked())
        save_setting("backup_dir", self.backup_path_input.text().strip())
        save_setting("backup_max_count", self.backup_max_count.value())

        # 4. Зрение
        save_setting("enable_vision", self.chk_vision.isChecked())
        save_setting("vision_model", self.vision_model_input.text().strip())
        save_setting("vision_quality", self.vision_quality_spin.value())
        save_setting("vision_tokens", self.vision_tokens_spin.value())

        # 5. Поведение
        save_setting("chatter_min_minutes", self.chatter_min.value())
        save_setting("chatter_max_minutes", self.chatter_max.value())
        save_setting("roam_chance", self.roam_chance.value())
        save_setting("autonomy_think_minutes", self.autonomy_think.value())
        save_setting("listen_window_seconds", self.listen_window.value())
        save_setting("chatter", self.chk_chatter.isChecked())
        save_setting("barge_in", self.chk_barge.isChecked())
        save_setting("teleport_on_answer", self.chk_teleport.isChecked())
        save_setting("enable_autonomy", self.chk_autonomy.isChecked())
        
        hide_val = self.hide_after.value() if self.chk_auto_hide.isChecked() else 0
        save_setting("hide_after_seconds", hide_val)

        # 6. Пинки и Лимиты
        save_setting("max_consecutive_errors", self.max_errors_spin.value())
        save_setting("enable_kick", self.chk_enable_kick.isChecked())
        save_setting("kick_frequency", self.kick_freq_spin.value())
        save_setting("kick_prompt", self.kick_prompt_edit.toPlainText())
        save_setting("chain_kick_freq", self.chain_freq_spin.value())
        save_setting("chain_kick_prompt", self.chain_prompt_edit.toPlainText())
        save_setting("chain_kick_super_freq", self.chain_super_freq_spin.value())
        save_setting("chain_kick_super_prompt", self.chain_super_prompt_edit.toPlainText())
        save_setting("max_steps_chain", self.max_steps_spin.value())
        save_setting("allow_write_script", self.chk_allow_script.isChecked())

        # 7. Звук
        save_setting("voice_volume", self.vol_slider.value())
        save_setting("mic_sensitivity", self.sens_slider.value())
        
        engine = self.tts_combo.currentText().lower()
        save_setting("tts_engine", engine)
        
        voice_name = self.voice_name_combo.currentText().strip()
        if not voice_name:
            voice_name = "baya" if engine == "silero" else "ru-RU-SvetlanaNeural"
        if engine == "silero":
            save_setting("silero_voice", voice_name)
        else:
            save_setting("voice", voice_name)
            
        save_setting("edge_rate", f"{self.edge_rate_spin.value():+d}%")
        save_setting("edge_pitch", f"{self.edge_pitch_spin.value():+d}Hz")
        save_setting("silero_pitch", self.silero_pitch_combo.currentText())

        # 8. Персонализация и Промпты
        gender = "female" if self.radio_female.isChecked() else "male"
        self.capri.set_profile("custom" if self.name_input.text() else "none", self.name_input.text(), gender)
        
        wake_words = [w.strip() for w in self.wake_input.text().split(",") if w.strip()]
        if wake_words: save_setting("wake_words", wake_words)
            
        save_setting("prompt_character", self.prompt_char.toPlainText())
        save_setting("prompt_speech", self.prompt_speech.toPlainText())
        save_setting("prompt_agent", self.prompt_agent.toPlainText())
        save_setting("custom_rules", self.custom_rules.toPlainText())

        # 2. Применяем настройки НА ЛЕТУ (без перезапуска)
        self.capri.cfg.update({
            "hide_after_seconds": hide_val,
            "voice_volume": self.vol_slider.value(),
            "mic_sensitivity": self.sens_slider.value(),
            "chatter": self.chk_chatter.isChecked(),
            "barge_in": self.chk_barge.isChecked(),
            "teleport_on_answer": self.chk_teleport.isChecked(),
            "custom_rules": self.custom_rules.toPlainText(),
            "prompt_character": self.prompt_char.toPlainText(),
            "prompt_speech": self.prompt_speech.toPlainText(),
            "prompt_agent": self.prompt_agent.toPlainText(),
            "wake_words": wake_words,
            "user_name": self.name_input.text(),
            "user_gender": gender,
            "enable_vision": self.chk_vision.isChecked(),
            "vision_model": self.vision_model_input.text().strip(),
            "backup_dir": self.backup_path_input.text().strip(),
            "backup_max_count": self.backup_max_count.value(),
            "enable_backup": self.chk_enable_backup.isChecked(),
            "tts_engine": engine,
            "edge_rate": f"{self.edge_rate_spin.value():+d}%",
            "edge_pitch": f"{self.edge_pitch_spin.value():+d}Hz",
            "silero_pitch": self.silero_pitch_combo.currentText(),
            "memory_search_mode": self.memory_mode_combo.currentText(),
            "autonomy_think_minutes": self.autonomy_think.value(),
            "max_consecutive_errors": self.max_errors_spin.value(),
            "enable_kick": self.chk_enable_kick.isChecked(),
            "kick_frequency": self.kick_freq_spin.value(),
            "kick_prompt": self.kick_prompt_edit.toPlainText(),
            "chain_kick_freq": self.chain_freq_spin.value(),
            "chain_kick_prompt": self.chain_prompt_edit.toPlainText(),
            "chain_kick_super_freq": self.chain_super_freq_spin.value(),
            "chain_kick_super_prompt": self.chain_super_prompt_edit.toPlainText(),
            "vision_quality": self.vision_quality_spin.value(),
            "vision_tokens": self.vision_tokens_spin.value(),
            "enable_autonomy": self.chk_autonomy.isChecked(),
            "silero_voice": voice_name if engine == "silero" else self.capri.cfg.get("silero_voice", "baya"),
            "voice": voice_name if engine == "edge" else self.capri.cfg.get("voice", "ru-RU-SvetlanaNeural"),
        })

        self.capri.set_voice_volume(self.vol_slider.value())
        self.capri.set_mic_tuning(sensitivity=self.sens_slider.value())
        self.capri.actions.set_lists(self.capri.cfg)
        self.capri.speaker = Speaker(self.capri.cfg)
        
        if self.capri.local:
            self.capri.local.model = self.model_input.text().strip()
            self.capri.local.cfg = self.capri.cfg

        # ПРИМЕНЯЕМ АВТОСКРЫТИЕ К АВАТАРУ НА ЛЕТУ
        for widget in main.QApplication.topLevelWidgets():
            if isinstance(widget, main.Avatar):
                widget.hide_after = float(hide_val)
                break

        log.info("Настройки применены на лету")
        if close_window:
            self.close()