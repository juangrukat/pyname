import httpx
from pathlib import Path
import json

from .base import BaseLLMProvider
from ..models import LLMConfig, FileMetadata, LLMRenameResponse, PromptOverrides
from ..media_utils import (
    encode_image_optimized,
    extract_video_frames,
    is_image_file,
    is_video_file,
    should_debug,
    format_prompt_debug,
    format_response_debug,
)


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter API provider implementation (OpenAI-compatible)."""
    
    def __init__(self, config: LLMConfig, prompts: PromptOverrides | None = None):
        super().__init__(config, prompts)
        self.base_url = config.api_base.rstrip("/")
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/juangrukat/pyname",
            "X-Title": "PyName File Renamer",
        }
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        self.client = httpx.AsyncClient(
            timeout=config.timeout_seconds,
            headers=headers
        )
    
    async def health_check(self) -> bool:
        """Check if OpenRouter API is accessible."""
        try:
            response = await self.client.get(
                f"{self.base_url}/models",
            )
            return response.status_code == 200
        except httpx.RequestError:
            return False
    
    async def get_rename_suggestion(
        self,
        file_path: Path,
        metadata: FileMetadata
    ) -> LLMRenameResponse:
        """Get rename suggestion from OpenRouter."""
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
                print(f"OpenRouter video frames extracted: {len(video_frames)}")
        
        if self._should_debug():
            print("OpenRouter prompt info:", format_prompt_debug(prompt, metadata.content_excerpt))
        
        # Build messages for Chat Completions (OpenAI-compatible format)
        messages = [
            {"role": "system", "content": self.get_system_prompt(metadata)}
        ]
        
        if send_image or video_frames:
            # Multimodal content with images
            content_blocks = [{"type": "text", "text": prompt}]
            
            if send_image:
                image_data, media_type = await encode_image_optimized(file_path)
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{image_data}"
                    }
                })
            
            for frame in video_frames:
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{frame}"
                    }
                })
            
            messages.append({"role": "user", "content": content_blocks})
        else:
            # Text-only content
            messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "response_format": {"type": "json_object"}
        }
        
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            json=payload
        )
        self._raise_for_status(response)
        
        result = response.json()
        if self._should_debug():
            print("OpenRouter response payload:", format_response_debug(result))
        
        try:
            response_text = result["choices"][0]["message"]["content"]
        except (KeyError, TypeError) as exc:
            debug_payload = format_response_debug(result)
            raise ValueError(
                f"Unexpected OpenRouter response shape. Response payload: {debug_payload}"
            ) from exc
        
        return self._parse_response(response_text)
    
    def _model_supports_vision(self) -> bool:
        """
        For OpenRouter, always assume vision capability.
        
        The user is responsible for selecting a vision-capable model
        on OpenRouter. We always send images and let the model handle it.
        """
        return True

    def _should_send_image(self, is_image: bool, has_vision: bool) -> bool:
        """
        For OpenRouter, always send image data if the file is an image.
        
        OpenRouter doesn't support the 'detail' parameter - models use
        their default settings. Users must select a vision-capable model.
        """
        return is_image
    
    def _should_debug(self) -> bool:
        """Check if debug logging is enabled."""
        return should_debug("PYNAME_DEBUG_OPENROUTER") or should_debug("PYNAME_DEBUG")
    
    def _parse_response(self, response_text: str) -> LLMRenameResponse:
        """Parse and validate LLM response."""
        text = response_text.strip()
        
        # Handle markdown-wrapped JSON
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
                f"OpenRouter API error {response.status_code}: {detail}"
            ) from exc
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
