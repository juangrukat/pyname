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


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API provider implementation."""
    
    # Claude 3+ models support vision
    KNOWN_VISION_MODELS = {"claude-3", "claude-3.5", "claude-sonnet", "claude-opus", "claude-haiku"}
    
    def __init__(self, config: LLMConfig, prompts: PromptOverrides | None = None):
        super().__init__(config, prompts)
        self.base_url = config.api_base.rstrip("/")
        headers = {
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        if config.api_key:
            headers["x-api-key"] = config.api_key
        self.client = httpx.AsyncClient(
            timeout=config.timeout_seconds,
            headers=headers
        )
    
    async def health_check(self) -> bool:
        """Check if Anthropic API is accessible."""
        # Anthropic doesn't have a simple health endpoint
        # We'll just verify we can make a minimal request
        try:
            # This will fail but we can check if it's an auth error vs connection error
            response = await self.client.post(
                f"{self.base_url}/messages",
                json={"model": "claude-3-haiku-20240307", "max_tokens": 1, "messages": []}
            )
            # Even a 400 error means the API is reachable
            return response.status_code in {200, 400, 401}
        except httpx.RequestError:
            return False
    
    async def get_rename_suggestion(
        self,
        file_path: Path,
        metadata: FileMetadata
    ) -> LLMRenameResponse:
        """Get rename suggestion from Anthropic Claude."""
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
                print(f"Anthropic video frames extracted: {len(video_frames)}")
        
        if self._should_debug():
            print("Anthropic prompt info:", format_prompt_debug(prompt, metadata.content_excerpt))
        
        # Build content blocks
        content = []
        
        # Add image if applicable (optimized encoding)
        if send_image:
            image_data, media_type = await encode_image_optimized(file_path)
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data
                }
            })
        
        # Add video frames
        for frame in video_frames:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": frame
                }
            })
        
        # Add text prompt
        content.append({"type": "text", "text": prompt})
        
        response = await self.client.post(
            f"{self.base_url}/messages",
            json={
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "system": self.get_system_prompt(metadata),
                "messages": [{"role": "user", "content": content}]
            }
        )
        self._raise_for_status(response)
        
        result = response.json()
        if self._should_debug():
            print("Anthropic response payload:", format_response_debug(result))
        
        response_text = result["content"][0]["text"]
        
        return self._parse_response(response_text)
    
    def _model_supports_vision(self) -> bool:
        """Infer vision capability from model name using shared detection."""
        return model_supports_vision(self.config.model, self.KNOWN_VISION_MODELS)

    def _should_send_image(self, is_image: bool, has_vision: bool) -> bool:
        """Determine if we should send image data."""
        if not is_image:
            return False
        if self.config.image_mode == ImageMode.BASE64:
            return True
        if self.config.image_mode == ImageMode.NATIVE:
            return has_vision
        # AUTO mode
        return has_vision
    
    def _should_debug(self) -> bool:
        """Check if debug logging is enabled."""
        return should_debug("PYNAME_DEBUG_ANTHROPIC") or should_debug("PYNAME_DEBUG")
    
    def _parse_response(self, response_text: str) -> LLMRenameResponse:
        """Parse and validate LLM response."""
        text = response_text.strip()
        
        # Claude sometimes wraps JSON in markdown
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            text = text[start:end].strip()
        
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            from json_repair import repair_json
            data = json.loads(repair_json(text))
        
        return LLMRenameResponse(**data)
    
    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Raise with response body for easier debugging."""
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip() or "No response body"
            raise ValueError(
                f"Anthropic API error {response.status_code}: {detail}"
            ) from exc
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
