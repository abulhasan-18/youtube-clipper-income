import os
import json
import logging
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("Clipper.AI")

class AIRouter:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.cerebras_key = os.getenv("CEREBRAS_API_KEY")

        self._init_clients()

    def _init_clients(self):
        # Groq Client
        self.groq_client = None
        if self.groq_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=self.groq_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Groq client: {e}")

        # Cerebras Client
        self.cerebras_client = None
        if self.cerebras_key:
            try:
                from cerebras.cloud.sdk import Cerebras
                self.cerebras_client = Cerebras(api_key=self.cerebras_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Cerebras client: {e}")

        # OpenRouter Client
        self.openrouter_client = None
        if self.openrouter_key:
            try:
                from openai import OpenAI
                self.openrouter_client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=self.openrouter_key,
                    default_headers={
                        "HTTP-Referer": "https://clipper-automation.local",
                        "X-Title": "Clipper Automation",
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to initialize OpenRouter client: {e}")

        # Gemini Client
        self.gemini_client = None
        if self.gemini_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=self.gemini_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")

    def generate_chat(self, prompt: str, system_prompt: str = "",
                      preferred_provider: str = "groq",
                      json_mode: bool = False,
                      max_tokens: int = 1500) -> str:
        """
        Executes chat completion with automatic cascading failover:
        groq -> openrouter -> gemini -> cerebras
        """
        providers = [preferred_provider]
        for p in ["groq", "openrouter", "gemini", "cerebras"]:
            if p not in providers:
                providers.append(p)

        last_err = None
        for provider in providers:
            try:
                if provider == "groq" and self.groq_client:
                    return self._call_groq(prompt, system_prompt, json_mode, max_tokens)
                elif provider == "openrouter" and self.openrouter_client:
                    return self._call_openrouter(prompt, system_prompt, json_mode, max_tokens)
                elif provider == "gemini" and self.gemini_client:
                    return self._call_gemini(prompt, system_prompt, json_mode)
                elif provider == "cerebras" and self.cerebras_client:
                    return self._call_cerebras(prompt, system_prompt, json_mode, max_tokens)
            except Exception as e:
                logger.warning(f"Provider {provider} failed: {e}. Cascading to next fallback...")
                last_err = e

        raise RuntimeError(f"All AI providers failed. Last error: {last_err}")

    def _call_groq(self, prompt: str, system_prompt: str, json_mode: bool, max_tokens: int) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Groq on-demand tier enforces a strict 1000 Output Tokens Per Minute (OTPM) limit
        groq_max_tokens = min(max_tokens, 800)
        kwargs = {
            "model": "qwen/qwen3.8-27b",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": groq_max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.groq_client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def _call_openrouter(self, prompt: str, system_prompt: str, json_mode: bool, max_tokens: int) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": "deepseek/deepseek-chat",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.openrouter_client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def _call_gemini(self, prompt: str, system_prompt: str, json_mode: bool) -> str:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        config = {}
        if json_mode:
            config["response_mime_type"] = "application/json"

        response = self.gemini_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=full_prompt,
            config=config if config else None
        )
        return response.text

    def _call_cerebras(self, prompt: str, system_prompt: str, json_mode: bool, max_tokens: int) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": "gpt-oss-120b",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.cerebras_client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
