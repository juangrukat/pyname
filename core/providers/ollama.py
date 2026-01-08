import httpx
from pathlib import Path
import json

from .base import BaseLLMProvider
from ..models import LLMConfig, FileMetadata, LLMRenameResponse, ImageMode, PromptOverrides
from ..media_utils import (
    encode_image_optimized,
    extract_video_frames,
    model_supports_vision,
    is_image_file,
    is_video_file,
    should_debug,
    format_prompt_debug,
    format_response_debug,
)


class OllamaProvider(BaseLLMProvider):
    """Ollama LLM provider implementation."""
    
    # Provider-specific known vision models
    KNOWN_VISION_MODELS = {"llava", "llava-llama3", "bakllava", "moondream"}
    
    def __init__(self, config: LLMConfig, prompts: PromptOverrides | None = None):
        super().__init__(config, prompts)
        self.base_url = config.api_base.rstrip("/")
        self.client = httpx.AsyncClient(timeout=config.timeout_seconds)
    
    async def health_check(self) -> bool:
        """Check if Ollama is running."""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except httpx.RequestError:
            return False
    
    async def get_rename_suggestion(
        self,
        file_path: Path,
        metadata: FileMetadata
    ) -> LLMRenameResponse:
        """Get rename suggestion from Ollama."""
        prompt = self.build_prompt(metadata)
        
        # Determine file type and vision capability
        is_image = is_image_file(metadata.extension)
        is_video = is_video_file(metadata.extension)
        has_vision = self._model_supports_vision()
        send_image = self._should_send_image(is_image, has_vision)
        
        # Extract video frames if applicable
        video_frames: list[str] = []
        if is_video and has_vision and (metadata.video_extract_count or 0) > 0:
            duration = metadata.video.duration_seconds if metadata.video else None
            video_frames = await extract_video_frames(
                file_path,
                metadata.video_extract_count or 0,
                duration
            )
            if self._should_debug():
                print(f"Ollama video frames extracted: {len(video_frames)}")
        
        if self._should_debug():
            print("Ollama prompt info:", format_prompt_debug(prompt, metadata.content_excerpt))
        
        request_body = {
            "model": self.config.model,
            "prompt": prompt,
            "system": self.get_system_prompt(metadata),
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens
            }
        }
        
        # Add images if applicable (optimized encoding)
        images: list[str] = []
        if send_image:
            image_data, _ = await encode_image_optimized(file_path)
            images.append(image_data)
        
        # Add video frames
        images.extend(video_frames)
        
        if images:
            request_body["images"] = images
        
        response = await self.client.post(
            f"{self.base_url}/api/generate",
            json=request_body
        )
        self._raise_for_status(response)
        
        result = response.json()
        if self._should_debug():
            print("Ollama response payload:", format_response_debug(result))
        
        response_text = result.get("response", "")
        
        return self._parse_response(response_text)
    
    def _model_supports_vision(self) -> bool:
        """Infer vision capability from model name using shared detection."""
        return model_supports_vision(self.config.model, self.KNOWN_VISION_MODELS)
    
    def _should_send_image(self, is_image: bool, has_vision: bool) -> bool:
        """Determine if we should send the image to the model."""
        if not is_image:
            return False
        if self.config.image_mode == ImageMode.NATIVE:
            return has_vision
        if self.config.image_mode == ImageMode.BASE64:
            return True
        # AUTO mode
        return has_vision
    
    def _should_debug(self) -> bool:
        """Check if debug logging is enabled."""
        return should_debug("PYNAME_DEBUG_OLLAMA") or should_debug("PYNAME_DEBUG")
    
    def _parse_response(self, response_text: str) -> LLMRenameResponse:
        """Parse and validate LLM response."""
        # Clean up common LLM response issues
        text = response_text.strip()
        
        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines if they're code fences
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        
        # Try to parse JSON
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                except json.JSONDecodeError:
                    # Use json_repair as last resort
                    from json_repair import repair_json
                    data = json.loads(repair_json(text))
            else:
                raise ValueError(f"Could not parse LLM response as JSON: {text[:200]}")
        
        return LLMRenameResponse(**data)
    
    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Raise with response body for easier debugging."""
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip() or "No response body"
            raise ValueError(
                f"Ollama API error {response.status_code}: {detail}"
            ) from exc
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
