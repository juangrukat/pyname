import httpx
from pathlib import Path
import json

from .base import BaseLLMProvider
from ..models import LLMConfig, FileMetadata, LLMRenameResponse, LLMProvider, ImageMode, PromptOverrides
from ..media_utils import (
    encode_image_optimized,
    extract_video_frames,
    model_supports_vision,
    is_image_file,
    is_video_file,
    should_debug,
    format_response_debug,
)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider implementation."""
    
    # GPT-5 models with vision capability
    KNOWN_VISION_MODELS = {"gpt-5-mini", "gpt-5-nano"}
    
    def __init__(self, config: LLMConfig, prompts: PromptOverrides | None = None):
        super().__init__(config, prompts)
        self.base_url = config.api_base.rstrip("/")
        headers = {
            "Content-Type": "application/json"
        }
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        self.client = httpx.AsyncClient(
            timeout=config.timeout_seconds,
            headers=headers
        )
    
    async def health_check(self) -> bool:
        """Check if OpenAI API is accessible."""
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
        """Get rename suggestion from OpenAI."""
        prompt = self.build_prompt(metadata)
        
        # Determine file type and vision capability
        is_image = is_image_file(metadata.extension)
        is_video = is_video_file(metadata.extension)
        has_vision = self._model_supports_vision()
        send_image = self._should_send_image(is_image, has_vision)
        
        # Extract video frames if applicable (OpenAI and LM Studio both support vision)
        video_frames: list[str] = []
        if (
            is_video
            and has_vision
            and (metadata.video_extract_count or 0) > 0
            and self.config.provider in {LLMProvider.OPENAI, LLMProvider.LMSTUDIO}
        ):
            duration = metadata.video.duration_seconds if metadata.video else None
            video_frames = await extract_video_frames(
                file_path,
                metadata.video_extract_count or 0,
                duration
            )
            if self._should_debug():
                provider_name = "LMStudio" if self.config.provider == LLMProvider.LMSTUDIO else "OpenAI"
                print(f"{provider_name} video frames extracted: {len(video_frames)}")
        
        if self._should_debug():
            print("OpenAI prompt info:", self._format_prompt_debug(metadata, prompt))

        if self._use_responses_api():
            input_content = [{"type": "input_text", "text": prompt}]
            if send_image:
                image_data, media_type = await encode_image_optimized(file_path)
                input_content.append({
                    "type": "input_image",
                    "image_url": f"data:{media_type};base64,{image_data}"
                })
            for frame in video_frames:
                input_content.append({
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{frame}"
                })

            payload = {
                "model": self.config.model,
                "instructions": self.get_system_prompt(metadata),
                "input": [{"role": "user", "content": input_content}],
                "max_output_tokens": self._gpt5_max_output_tokens(),
                "reasoning": {"effort": "medium"}
            }
            if self._supports_temperature():
                payload["temperature"] = self.config.temperature
            if self.config.provider != LLMProvider.LMSTUDIO:
                payload["text"] = {
                    "format": self._rename_response_format(),
                    "verbosity": "low"
                }

            response = await self.client.post(
                f"{self.base_url}/responses",
                json=payload
            )
            self._raise_for_status(response)
            result = response.json()
            if self._should_debug():
                print("OpenAI response payload:", format_response_debug(result))
            try:
                response_text = self._extract_response_text(result)
            except ValueError as exc:
                debug_payload = format_response_debug(result)
                raise ValueError(
                    f"{exc}. Response payload: {debug_payload}"
                ) from exc
        else:
            # Build messages for Chat Completions
            messages = [
                {"role": "system", "content": self.get_system_prompt(metadata)}
            ]
            if send_image or video_frames:
                content_blocks = [{"type": "text", "text": prompt}]
                if send_image:
                    image_data, media_type = await encode_image_optimized(file_path)
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_data}",
                            "detail": "low"
                        }
                    })
                for frame in video_frames:
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{frame}",
                            "detail": "low"
                        }
                    })
                messages.append({"role": "user", "content": content_blocks})
            else:
                messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.config.model,
                "messages": messages,
                "max_tokens": self.config.max_tokens
            }
            if self._supports_temperature():
                payload["temperature"] = self.config.temperature
            if self.config.provider != LLMProvider.LMSTUDIO:
                payload["response_format"] = {"type": "json_object"}

            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload
            )
            self._raise_for_status(response)
            
            result = response.json()
            if self._should_debug():
                print("OpenAI response payload:", format_response_debug(result))
            try:
                response_text = result["choices"][0]["message"]["content"]
            except (KeyError, TypeError) as exc:
                debug_payload = format_response_debug(result)
                raise ValueError(
                    f"Unexpected OpenAI response shape. Response payload: {debug_payload}"
                ) from exc
        
        return self._parse_response(response_text)

    def _model_supports_vision(self) -> bool:
        """Infer vision capability from model name using shared detection."""
        model = self.config.model.lower()
        # Check OpenAI-specific GPT-5 models first
        if any(v in model for v in self.KNOWN_VISION_MODELS):
            return True
        # Use shared detection for other models (LM Studio, compatible APIs)
        return model_supports_vision(self.config.model)

    def _should_send_image(self, is_image: bool, has_vision: bool) -> bool:
        """Determine if we should send image data."""
        if not is_image:
            return False
        if self.config.image_mode == ImageMode.BASE64:
            return True
        if self.config.image_mode == ImageMode.NATIVE:
            return True
        return has_vision

    def _use_responses_api(self) -> bool:
        """Use the Responses API for GPT-5 models."""
        return (
            self.config.provider == LLMProvider.OPENAI
            and self.config.model.lower().startswith("gpt-5")
        )

    def _supports_temperature(self) -> bool:
        """Check if the current model accepts temperature."""
        return not self.config.model.lower().startswith("gpt-5")

    def _gpt5_max_output_tokens(self) -> int:
        """Ensure GPT-5 has enough output tokens for high reasoning."""
        return max(self.config.max_tokens, 3000)
    
    def _should_debug(self) -> bool:
        """Check if debug logging is enabled."""
        if self.config.provider == LLMProvider.LMSTUDIO:
            return should_debug("PYNAME_DEBUG_LMSTUDIO") or should_debug("PYNAME_DEBUG")
        return should_debug("PYNAME_DEBUG_OPENAI") or should_debug("PYNAME_DEBUG")
    
    def _parse_response(self, response_text: str) -> LLMRenameResponse:
        """Parse and validate LLM response."""
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            from json_repair import repair_json
            data = json.loads(repair_json(response_text))
        
        return LLMRenameResponse(**data)

    @classmethod
    def _extract_response_text(cls, result: dict) -> str:
        """Extract text from the Responses API payload."""
        output_text = cls._normalize_text(result.get("output_text"))
        if output_text:
            return output_text
        output_json = cls._normalize_json(result.get("output_json"))
        if output_json:
            return output_json
        output_parsed = cls._normalize_json(result.get("output_parsed"))
        if output_parsed:
            return output_parsed

        output = result.get("output", [])
        if isinstance(output, list):
            for item in output:
                text = cls._scan_output_item(item)
                if text:
                    return text
        elif isinstance(output, dict):
            text = cls._scan_output_item(output)
            if text:
                return text
        error = result.get("error")
        if error:
            raise ValueError(f"OpenAI response error: {error}")
        status = result.get("status")
        if status and status != "completed":
            details = result.get("incomplete_details") or {}
            raise ValueError(f"OpenAI response status {status}: {details}")
        raise ValueError("No text content in OpenAI response.")

    @classmethod
    def _scan_output_item(cls, item: object) -> str | None:
        if not isinstance(item, dict):
            return None

        output_json = cls._normalize_json(item.get("output_json"))
        if output_json:
            return output_json
        output_parsed = cls._normalize_json(item.get("output_parsed"))
        if output_parsed:
            return output_parsed

        text = cls._normalize_text(item.get("text"))
        if text:
            return text
        json_payload = cls._normalize_json(item.get("json"))
        if json_payload:
            return json_payload

        content = item.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "refusal":
                    refusal = cls._normalize_text(block.get("refusal") or block.get("text"))
                    if refusal:
                        raise ValueError(f"OpenAI response refusal: {refusal}")
                output_json = cls._normalize_json(block.get("output_json"))
                if output_json:
                    return output_json
                output_parsed = cls._normalize_json(block.get("output_parsed"))
                if output_parsed:
                    return output_parsed
                json_payload = cls._normalize_json(block.get("json"))
                if json_payload:
                    return json_payload
                text = cls._normalize_text(block.get("text"))
                if text:
                    return text
        if isinstance(content, dict):
            output_json = cls._normalize_json(content.get("output_json"))
            if output_json:
                return output_json
            output_parsed = cls._normalize_json(content.get("output_parsed"))
            if output_parsed:
                return output_parsed
            json_payload = cls._normalize_json(content.get("json"))
            if json_payload:
                return json_payload
            text = cls._normalize_text(content.get("text") or content.get("output_text"))
            if text:
                return text
        return None

    @staticmethod
    def _normalize_text(value: object) -> str | None:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        if isinstance(value, dict):
            for key in ("text", "value", "output_text"):
                inner = value.get(key)
                if isinstance(inner, str):
                    stripped = inner.strip()
                    if stripped:
                        return stripped
        return None

    @staticmethod
    def _normalize_json(value: object) -> str | None:
        if isinstance(value, (dict, list)) and value:
            return json.dumps(value)
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        return None

    @staticmethod
    def _format_prompt_debug(metadata: FileMetadata, prompt: str) -> str:
        """Summarize prompt and content excerpt for tracing."""
        excerpt = metadata.content_excerpt or ""
        return (
            f"prompt_chars={len(prompt)} "
            f"content_chars={len(excerpt)} "
            f"content_source={metadata.content_source or 'none'} "
            f"content_truncated={metadata.content_truncated} "
            f"video_extract_count={metadata.video_extract_count or 0}"
        )
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Raise with response body for easier debugging."""
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip() or "No response body"
            raise ValueError(
                f"OpenAI API error {response.status_code}: {detail}"
            ) from exc

    @staticmethod
    def _rename_response_format() -> dict:
        """JSON schema format for rename responses."""
        return {
            "type": "json_schema",
            "name": "rename_response",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "suggested_name": {"type": "string"},
                    "reasoning": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 10
                    }
                },
                "required": ["suggested_name", "reasoning", "confidence", "tags"],
                "additionalProperties": False
            }
        }
