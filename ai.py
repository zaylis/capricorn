"""Ответы на вопросы через API (OpenAI, Claude, DeepSeek, Groq, OpenRouter)."""
import datetime
import logging
import os
from openai import OpenAI

from persona import CHARACTER, SPEECH_RULES, user_context

log = logging.getLogger("capri")

SYSTEM = f"""{CHARACTER}

{SPEECH_RULES}
Для свежих фактов (погода, новости, курсы, расписания) используй веб-поиск.
Командами ПК (открыть сайт/приложение, громкость, яркость, диагностика) занимается отдельный модуль;
если просят то, чего ты сделать не можешь, скажи, какую команду произнести, например «Капри, открой ютуб»."""

class AI:
    def __init__(self, cfg):
        self.cfg = cfg
        self.provider = cfg.get("provider", "ollama")
        self.model = cfg.get("api_model", "gpt-4o")
        self.api_key = cfg.get("api_key", "")
        self.history = []
        self.client = None
        
        if self.api_key and self.provider != "ollama":
            base_url = None
            if self.provider == "deepseek":
                base_url = "https://api.deepseek.com"
            elif self.provider == "groq":
                base_url = "https://api.groq.com/openai/v1"
            elif self.provider == "openrouter":
                base_url = "https://openrouter.ai/api/v1"
            elif self.provider == "gemini":
                base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
                
            if self.provider == "claude":
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            else:
                self.client = OpenAI(api_key=self.api_key, base_url=base_url)

    @property
    def available(self):
        return self.client is not None

    def ask(self, question):
        if not self.available:
            return "Чтобы я отвечала на вопросы, настрой API-ключ в настройках."
            
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        self.history.append({"role": "user", "content": f"[{now}] {question}"})
        self.history = self.history[-10:] # Держим контекст последних 10 сообщений

        try:
            if self.provider == "claude":
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=2000,
                    system=SYSTEM + "\n" + user_context(),
                    messages=self.history
                )
                answer = resp.content[0].text
            else:
                # Универсальный вызов для OpenAI, DeepSeek, Groq, OpenRouter, Gemini
                messages = [{"role": "system", "content": SYSTEM + "\n" + user_context()}] + self.history
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=float(self.cfg.get("temperature", 0.7)),
                    max_tokens=2000
                )
                answer = resp.choices[0].message.content
                
            self.history.append({"role": "assistant", "content": answer})
            return answer.strip()
            
        except Exception as e:
            log.error("Ошибка API (%s): %s", self.provider, e)
            self.history.pop() # Удаляем последний вопрос, чтобы не ломать историю
            return "Произошла ошибка при обращении к API. Проверь ключ и интернет."

    def summarize_report(self, report):
        # (Оставь как было, если нужно, либо адаптируй под новые провайдеры)
        return None