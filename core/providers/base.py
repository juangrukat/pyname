from abc import ABC, abstractmethod
from pathlib import Path
from ..models import LLMConfig, FileMetadata, LLMRenameResponse, PromptOverrides
from ..prompts import PromptBuilder


class BaseLLMProvider(ABC):
    """Abstract base for LLM providers."""
    
    def __init__(self, config: LLMConfig, prompts: PromptOverrides | None = None):
        self.config = config
        self.prompts = prompts
    
    @abstractmethod
    async def get_rename_suggestion(
        self,
        file_path: Path,
        metadata: FileMetadata
    ) -> LLMRenameResponse:
        """Get rename suggestion from LLM."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is available."""
        pass
    
    def build_prompt(self, metadata: FileMetadata) -> str:
        """Build the prompt for the LLM."""
        return PromptBuilder.get_user_prompt(metadata, self.prompts)

    def get_system_prompt(self, metadata: FileMetadata) -> str:
        """Get system prompt for the file type."""
        return PromptBuilder.get_system_prompt(metadata, self.prompts)
    
    @property
    def system_prompt(self) -> str:
        return PromptBuilder.SYSTEM_PROMPT_BASE
