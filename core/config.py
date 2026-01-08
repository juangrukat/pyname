import json
import os
import aiofiles
from pathlib import Path
from typing import Optional

from .models import AppConfig, LLMProvider


class ConfigManager:
    """Manage application configuration."""
    
    def __init__(self, config_file: Path | None = None):
        self.config_file = config_file or Path("data/config.json")
        self._config: Optional[AppConfig] = None
        self._ensure_data_dir()
    
    def _ensure_data_dir(self) -> None:
        """Ensure the data directory exists."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
    
    async def load(self) -> AppConfig:
        """Load configuration from file."""
        if self._config is not None:
            return self._config
        
        if not self.config_file.exists():
            self._config = AppConfig()
            await self.save(self._config)
            return self._config
        
        try:
            async with aiofiles.open(self.config_file, "r") as f:
                content = await f.read()
                data = json.loads(content)
                self._config = AppConfig(**data)
        except (json.JSONDecodeError, ValueError):
            self._config = AppConfig()
        
        return self._config
    
    async def save(self, config: Optional[AppConfig] = None) -> None:
        """Save configuration to file."""
        if config is not None:
            self._config = config
        
        if self._config is None:
            return
        
        async with aiofiles.open(self.config_file, "w") as f:
            await f.write(self._config.model_dump_json(indent=2))
    
    async def update(self, **kwargs) -> AppConfig:
        """Update specific configuration values."""
        config = await self.load()
        
        # Handle nested updates
        config_dict = config.model_dump()
        
        for key, value in kwargs.items():
            if "." in key:
                # Nested key like "llm.model"
                parts = key.split(".")
                target = config_dict
                for part in parts[:-1]:
                    target = target[part]
                target[parts[-1]] = value
            else:
                config_dict[key] = value
        
        self._config = AppConfig(**config_dict)
        await self.save()
        
        return self._config
    
    def get_sync(self) -> AppConfig:
        """Get config synchronously (use cached value or defaults)."""
        if self._config is not None:
            return self._config
        
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    self._config = AppConfig(**data)
                    return self._config
            except (json.JSONDecodeError, ValueError):
                pass
        
        return AppConfig()

    def get_runtime_sync(self) -> AppConfig:
        """Get config with API key resolved for the current provider."""
        config = self.get_sync()
        return self._apply_provider_api_key(config)

    def env_api_key_status(self) -> dict[str, bool]:
        """Return which env vars are available for API keys."""
        return {
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
        }

    def api_key_status(self) -> dict[str, dict[str, bool]]:
        """Return status of API keys (stored and env) for each provider."""
        config = self.get_sync()
        return {
            "openai": {
                "stored": bool(config.llm.api_keys.openai),
                "env": bool(os.getenv("OPENAI_API_KEY")),
            },
            "anthropic": {
                "stored": bool(config.llm.api_keys.anthropic),
                "env": bool(os.getenv("ANTHROPIC_API_KEY")),
            },
            "openrouter": {
                "stored": bool(config.llm.api_keys.openrouter),
                "env": bool(os.getenv("OPENROUTER_API_KEY")),
            },
        }

    def _apply_provider_api_key(self, config: AppConfig) -> AppConfig:
        """Resolve API key for the current provider from api_keys or env vars."""
        provider = config.llm.provider
        api_keys = config.llm.api_keys
        
        # Map provider to stored key and env var
        key_map = {
            LLMProvider.OPENAI: (api_keys.openai, "OPENAI_API_KEY"),
            LLMProvider.ANTHROPIC: (api_keys.anthropic, "ANTHROPIC_API_KEY"),
            LLMProvider.OPENROUTER: (api_keys.openrouter, "OPENROUTER_API_KEY"),
            LLMProvider.LMSTUDIO: (api_keys.openai, "OPENAI_API_KEY"),  # LM Studio can use OpenAI key
            LLMProvider.OLLAMA: (None, None),  # Ollama doesn't need API key
        }
        
        stored_key, env_var = key_map.get(provider, (None, None))
        
        # Resolve the key: stored key takes priority, then env var
        resolved_key = None
        if stored_key:
            resolved_key = self._resolve_env_var(stored_key)
        if not resolved_key and env_var:
            resolved_key = os.getenv(env_var)
        
        if resolved_key:
            updated_llm = config.llm.model_copy(update={"api_key": resolved_key})
            return config.model_copy(update={"llm": updated_llm})
        
        return config

    @staticmethod
    def _resolve_env_var(value: str) -> str | None:
        """Resolve environment variable references like $VAR or ${VAR}."""
        if not value:
            return value
        
        value = value.strip()
        
        # Handle ${VAR} format
        if value.startswith("${") and value.endswith("}"):
            var_name = value[2:-1]
            return os.getenv(var_name)
        
        # Handle $VAR format
        if value.startswith("$"):
            var_name = value[1:]
            return os.getenv(var_name)
        
        # Not an env var reference, return as-is
        return value
