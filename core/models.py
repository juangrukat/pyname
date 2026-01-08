from __future__ import annotations
from pydantic import BaseModel, Field, field_validator, computed_field
from typing import Literal
from pathlib import Path
from datetime import datetime
from enum import Enum
import re


class CaseStyle(str, Enum):
    """Supported filename case transformations."""
    CAMEL = "camelCase"
    CAPITAL = "capitalCase"
    CONSTANT = "constantCase"
    DOT = "dotCase"
    KEBAB = "kebabCase"
    NO = "noCase"
    PASCAL = "pascalCase"
    PASCAL_SNAKE = "pascalSnakeCase"
    PATH = "pathCase"
    SENTENCE = "sentenceCase"
    SNAKE = "snakeCase"
    TRAIN = "trainCase"


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LMSTUDIO = "lmstudio"


class TagMode(str, Enum):
    """How to apply Finder tags."""
    APPEND = "append"
    REPLACE = "replace"


class ImageMode(str, Enum):
    """How to send images to the LLM."""
    NATIVE = "native"      # Use provider's native image handling
    BASE64 = "base64"      # Force base64 encoding
    AUTO = "auto"          # Let provider decide


# ─────────────────────────────────────────────────────────────────────────────
# Metadata Models
# ─────────────────────────────────────────────────────────────────────────────

class ImageMetadata(BaseModel):
    """Extracted image metadata."""
    date_taken: datetime | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    lens_model: str | None = None
    focal_length: str | None = None
    aperture: str | None = None
    iso: int | None = None
    gps_latitude: float | None = None
    gps_longitude: float | None = None
    width: int | None = None
    height: int | None = None


class VideoMetadata(BaseModel):
    """Extracted video metadata."""
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    codec: str | None = None
    bitrate: int | None = None
    fps: float | None = None
    creation_time: datetime | None = None


class FileMetadata(BaseModel):
    """Combined file metadata."""
    file_path: Path
    file_name: str
    extension: str
    size_bytes: int
    created_at: datetime
    modified_at: datetime
    image: ImageMetadata | None = None
    video: VideoMetadata | None = None
    video_extract_count: int | None = None
    parent_folder_name: str | None = None
    folder_context: str | None = None
    include_current_filename: bool = True
    content_excerpt: str | None = None
    content_truncated: bool = False
    content_source: str | None = None
    tag_count: int | None = None
    tag_prompt: str | None = None
    neighbor_names: list[str] = Field(default_factory=list)
    
    @computed_field
    @property
    def size_human(self) -> str:
        """Human-readable file size."""
        size = self.size_bytes
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


# ─────────────────────────────────────────────────────────────────────────────
# LLM Response Models
# ─────────────────────────────────────────────────────────────────────────────

class LLMRenameResponse(BaseModel):
    """Validated LLM response for file renaming."""
    
    suggested_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Suggested filename without extension"
    )
    reasoning: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Brief explanation for the suggestion"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Model's confidence in suggestion (0-1)"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Suggested macOS Finder tags"
    )
    
    @field_validator("suggested_name")
    @classmethod
    def sanitize_suggested_name(cls, v: str) -> str:
        """Basic sanitization - full sanitization happens in safety module."""
        v = v.strip()
        # Remove obvious markdown artifacts
        v = re.sub(r'^[`"\']|[`"\']$', '', v)
        if not v:
            raise ValueError("suggested_name cannot be empty")
        return v
    
    @field_validator("tags")
    @classmethod
    def clean_tags(cls, v: list[str]) -> list[str]:
        """Clean and limit tags."""
        cleaned = []
        for tag in v:
            tag = tag.strip()
            if tag and len(tag) <= 50:
                cleaned.append(tag)
            if len(cleaned) >= 10:
                break
        return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# Processing Models
# ─────────────────────────────────────────────────────────────────────────────

class ProcessingState(str, Enum):
    """Current state of the processing pipeline."""
    IDLE = "idle"
    ANALYZING = "analyzing"
    PROCESSING = "processing"
    PAUSED = "paused"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"


class FileProcessingResult(BaseModel):
    """Result of processing a single file."""
    original_path: Path
    original_name: str
    suggested_name: str
    final_name: str | None = None      # After transformation & sanitization
    new_path: Path | None = None       # After collision resolution
    reasoning: str
    tags: list[str] = Field(default_factory=list)
    apply_tags: bool = True
    system_prompt: str | None = None
    user_prompt: str | None = None
    confidence: float
    status: Literal["pending", "approved", "rejected", "applied", "failed"]
    error_message: str | None = None
    applied_at: datetime | None = None


class ProcessingStatus(BaseModel):
    """Status update for the frontend."""
    state: ProcessingState
    current_file: str | None = None
    current_index: int = 0
    total_files: int = 0
    message: str = ""
    results: list[FileProcessingResult] = Field(default_factory=list)
    
    @computed_field
    @property
    def progress_percent(self) -> float:
        if self.total_files == 0:
            return 0.0
        return round((self.current_index / self.total_files) * 100, 1)


# ─────────────────────────────────────────────────────────────────────────────
# History Models
# ─────────────────────────────────────────────────────────────────────────────

class RenameOperation(BaseModel):
    """Single rename operation for history."""
    original_path: Path
    new_path: Path
    original_name: str
    new_name: str
    tags_applied: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)


class HistoryBatch(BaseModel):
    """A batch of rename operations."""
    batch_id: str
    operations: list[RenameOperation]
    created_at: datetime = Field(default_factory=datetime.now)
    undone: bool = False
    undone_at: datetime | None = None
    
    @computed_field
    @property
    def file_count(self) -> int:
        return len(self.operations)

# core/models.py (continued)

class LLMConfig(BaseModel):
    """LLM provider configuration."""
    provider: LLMProvider = LLMProvider.OLLAMA
    model: str = "llava:latest"
    api_base: str = "http://localhost:11434"
    api_key: str | None = None
    image_mode: ImageMode = ImageMode.AUTO
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=500, ge=50)
    timeout_seconds: int = Field(default=60, ge=10, le=300)


class ProcessingConfig(BaseModel):
    """Processing behavior configuration."""
    case_style: CaseStyle = CaseStyle.KEBAB
    preserve_extension: bool = True
    include_date_prefix: bool = False
    date_format: str = "%Y-%m-%d"
    include_current_filename: bool = True
    include_parent_folder: bool = False
    include_neighbor_names: bool = True
    neighbor_context_count: int = Field(default=3, ge=0, le=10)
    folder_context_depth: int = Field(default=1, ge=0, le=10)
    include_file_content: bool = False
    content_max_chars: int = Field(default=2000, ge=200, le=20000)
    video_extract_count: int = Field(default=3, ge=0, le=10)
    max_concurrency: int = Field(default=1, ge=1, le=50)
    auto_apply_tags: bool = True
    tag_count: int = Field(default=5, ge=0, le=10)
    tag_prompt: str = ""
    tag_mode: TagMode = TagMode.APPEND
    drop_folder_depth: int = Field(default=1, ge=0, le=10)
    dry_run: bool = True


class PromptSection(BaseModel):
    """Prompt overrides for a file type."""
    image: str | None = None
    video: str | None = None
    document: str | None = None
    generic: str | None = None


class PromptOverrides(BaseModel):
    """Optional prompt overrides."""
    system: PromptSection = Field(default_factory=PromptSection)
    user: PromptSection = Field(default_factory=PromptSection)


class AppConfig(BaseModel):
    """Complete application configuration."""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    prompts: PromptOverrides = Field(default_factory=PromptOverrides)
    
    # UI preferences
    window_width: int = 900
    window_height: int = 700
    confirm_before_apply: bool = True
    show_reasoning: bool = True
    show_prompt_preview: bool = False
    prompt_preview_chars: int = Field(default=2000, ge=200, le=20000)
    
    class Config:
        use_enum_values = True
