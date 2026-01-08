from .models import LLMConfig, LLMProvider, PromptOverrides
from .providers.base import BaseLLMProvider
from .providers.ollama import OllamaProvider
from .providers.openai import OpenAIProvider
from .providers.anthropic import AnthropicProvider
from .providers.openrouter import OpenRouterProvider


class LLMClient:
    """Factory and wrapper for LLM providers."""
    
    _providers = {
        LLMProvider.OLLAMA: OllamaProvider,
        LLMProvider.OPENAI: OpenAIProvider,
        LLMProvider.ANTHROPIC: AnthropicProvider,
        LLMProvider.LMSTUDIO: OpenAIProvider,
        LLMProvider.OPENROUTER: OpenRouterProvider,
    }
    
    def __init__(self, config: LLMConfig, prompts: PromptOverrides | None = None):
        self.config = config
        self.prompts = prompts
        provider_class = self._providers.get(config.provider)
        if not provider_class:
            raise ValueError(f"Unknown provider: {config.provider}")
        self._provider: BaseLLMProvider = provider_class(config, prompts)
    
    def __getattr__(self, name):
        """Delegate to underlying provider."""
        return getattr(self._provider, name)
    
    async def close(self):
        """Close provider resources."""
        await self._provider.close()
