from __future__ import annotations
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Callable, AsyncIterator
import uuid

from .models import (
    AppConfig, FileMetadata, FileProcessingResult,
    ProcessingStatus, ProcessingState, HistoryBatch, RenameOperation
)
from .llm import LLMClient
from .metadata import MetadataExtractor
from .safety import SafetyChecker
from .transformer import NameTransformer
from .tagging import TagManager
from .history import HistoryManager
from .prompts import PromptBuilder


class FileProcessor:
    """Main processing pipeline orchestrator."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.llm = LLMClient(config.llm, config.prompts)
        self.metadata_extractor = MetadataExtractor()
        self.safety = SafetyChecker()
        self.transformer = NameTransformer()
        self.tagger = TagManager()
        self.history = HistoryManager()
        
        self._cancel_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        
        # Track files renamed in current session to exclude from neighbor context
        self._session_renamed: set[Path] = set()
    
    def reset_session(self) -> None:
        """Reset session state for new batch."""
        self._cancel_event.clear()
        self._pause_event.set()
        self._session_renamed.clear()
    
    def cancel(self) -> None:
        """Request cancellation of current processing."""
        self._cancel_event.set()
    
    def pause(self) -> None:
        """Pause processing."""
        self._pause_event.clear()
    
    def resume(self) -> None:
        """Resume processing."""
        self._pause_event.set()
    
    async def process_files(
        self,
        file_paths: list[Path],
        on_status: Callable[[ProcessingStatus], None] | None = None
    ) -> list[FileProcessingResult]:
        """
        Process files and generate rename suggestions.
        
        Args:
            file_paths: List of files to process
            on_status: Callback for status updates
            
        Returns:
            List of processing results
        """
        self.reset_session()
        results: list[FileProcessingResult] = []
        results_by_index: dict[int, FileProcessingResult] = {}
        total = len(file_paths)
        completed = 0
        lock = asyncio.Lock()
        max_concurrency = max(1, self.config.processing.max_concurrency)
        semaphore = asyncio.Semaphore(max_concurrency)
        
        def emit_status(
            state: ProcessingState,
            index: int = 0,
            current: str | None = None,
            message: str = ""
        ):
            if on_status:
                on_status(ProcessingStatus(
                    state=state,
                    current_file=current,
                    current_index=index,
                    total_files=total,
                    message=message,
                    results=results
                ))
        
        emit_status(ProcessingState.ANALYZING, message="Starting analysis...")

        async def process_one(index: int, file_path: Path) -> None:
            nonlocal completed
            if self._cancel_event.is_set():
                return

            async with semaphore:
                if self._cancel_event.is_set():
                    return

                await self._pause_event.wait()

                file_name = file_path.name
                emit_status(ProcessingState.PROCESSING, completed, file_name, f"Processing {file_name}")

                try:
                    result = await self._process_single_file(file_path)
                except Exception as e:
                    result = FileProcessingResult(
                        original_path=file_path,
                        original_name=file_name,
                        suggested_name=file_name,
                        reasoning="",
                        apply_tags=False,
                        confidence=0.0,
                        status="failed",
                        error_message=str(e)
                    )

                async with lock:
                    results_by_index[index] = result
                    results.append(result)
                    completed += 1
                    emit_status(ProcessingState.PROCESSING, completed, file_name)

        tasks = [
            asyncio.create_task(process_one(index, file_path))
            for index, file_path in enumerate(file_paths)
        ]

        if tasks:
            await asyncio.gather(*tasks)
        
        final_state = (
            ProcessingState.CANCELLED 
            if self._cancel_event.is_set() 
            else ProcessingState.COMPLETE
        )
        emit_status(final_state, completed, message="Processing complete")
        
        return [results_by_index[i] for i in sorted(results_by_index)]
    
    async def _process_single_file(self, file_path: Path) -> FileProcessingResult:
        """Process a single file and return result."""
        # Extract metadata
        neighbor_count = (
            self.config.processing.neighbor_context_count
            if self.config.processing.include_neighbor_names
            else 0
        )
        include_content = self.config.processing.include_file_content
        content_max_chars = self.config.processing.content_max_chars
        metadata = await self.metadata_extractor.extract(
            file_path,
            neighbor_count=neighbor_count,
            exclude_paths=self._session_renamed,
            include_content=include_content,
            content_max_chars=content_max_chars
        )
        if self.config.processing.include_parent_folder:
            metadata.parent_folder_name = file_path.parent.name
        metadata.folder_context = self._build_folder_context(
            file_path,
            self.config.processing.folder_context_depth
        )
        metadata.include_current_filename = self.config.processing.include_current_filename
        metadata.video_extract_count = self.config.processing.video_extract_count
        metadata.tag_count = self.config.processing.tag_count
        tag_prompt = (self.config.processing.tag_prompt or "").strip()
        metadata.tag_prompt = tag_prompt or None

        # Get LLM suggestion
        llm_response = await self.llm.get_rename_suggestion(
            file_path=file_path,
            metadata=metadata
        )

        tag_count = metadata.tag_count
        if tag_count is not None:
            if tag_count <= 0:
                llm_response.tags = []
            elif llm_response.tags:
                llm_response.tags = llm_response.tags[:tag_count]
        
        # Transform name to desired case style
        transformed_name = self.transformer.transform(
            llm_response.suggested_name,
            self.config.processing.case_style
        )
        
        # Optional date prefix
        if self.config.processing.include_date_prefix:
            date_source = (
                metadata.image.date_taken if metadata.image 
                else metadata.created_at
            )
            date_str = date_source.strftime(self.config.processing.date_format)
            transformed_name = f"{date_str}_{transformed_name}"
        
        # Sanitize for filesystem
        sanitized_name = self.safety.sanitize_filename(transformed_name)
        
        # Add extension
        if self.config.processing.preserve_extension:
            final_name = f"{sanitized_name}{metadata.extension}"
        else:
            final_name = sanitized_name
        
        # Resolve collisions
        new_path = self.safety.resolve_collision(
            file_path.parent / final_name
        )
        
        system_prompt = None
        user_prompt = None
        if self.config.show_prompt_preview:
            system_prompt = PromptBuilder.get_system_prompt(metadata, self.config.prompts)
            user_prompt = PromptBuilder.get_user_prompt(metadata, self.config.prompts)
            system_prompt = self._truncate_prompt(system_prompt)
            user_prompt = self._truncate_prompt(user_prompt)

        return FileProcessingResult(
            original_path=file_path,
            original_name=metadata.file_name,
            suggested_name=llm_response.suggested_name,
            final_name=new_path.name,
            new_path=new_path,
            reasoning=llm_response.reasoning,
            tags=llm_response.tags,
            apply_tags=self.config.processing.auto_apply_tags,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            confidence=llm_response.confidence,
            status="pending"
        )

    @staticmethod
    def _build_folder_context(file_path: Path, depth: int) -> str | None:
        """Build a folder context string based on parent depth."""
        if depth <= 0:
            return None

        parts: list[str] = []
        current = file_path.parent
        for _ in range(depth):
            if not current or not current.name:
                break
            parts.append(current.name)
            current = current.parent

        if not parts:
            return None

        parts.reverse()
        return " / ".join(parts)

    def _truncate_prompt(self, text: str | None) -> str | None:
        """Trim prompt previews to configured length."""
        if not text:
            return text
        max_chars = self.config.prompt_preview_chars
        if max_chars <= 0:
            return text
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars].rstrip()}\n...[truncated]"
    
    async def apply_results(
        self,
        results: list[FileProcessingResult],
        on_progress: Callable[[int, int], None] | None = None
    ) -> HistoryBatch:
        """
        Apply approved rename operations.
        
        Args:
            results: List of results to apply (only 'approved' status will be processed)
            on_progress: Callback with (current, total)
            
        Returns:
            History batch for undo capability
        """
        approved = [r for r in results if r.status == "approved"]
        operations: list[RenameOperation] = []
        
        for index, result in enumerate(approved):
            if on_progress:
                on_progress(index, len(approved))
            
            if result.new_path is None:
                continue
            
            try:
                # Perform rename
                result.original_path.rename(result.new_path)
                
                # Apply tags if enabled
                if (
                    self.config.processing.auto_apply_tags
                    and result.apply_tags
                    and result.tags
                ):
                    tag_mode = self.config.processing.tag_mode
                    tag_mode_value = tag_mode.value if hasattr(tag_mode, "value") else str(tag_mode)
                    await self.tagger.apply_tags(
                        result.new_path,
                        result.tags,
                        mode=tag_mode_value
                    )
                
                # Record operation
                operations.append(RenameOperation(
                    original_path=result.original_path,
                    new_path=result.new_path,
                    original_name=result.original_name,
                    new_name=result.new_path.name,
                    tags_applied=result.tags
                ))
                
                # Track for neighbor context exclusion
                self._session_renamed.add(result.new_path)
                
                result.status = "applied"
                result.applied_at = datetime.now()
                
            except OSError as e:
                result.status = "failed"
                result.error_message = str(e)
        
        # Save to history
        batch = HistoryBatch(
            batch_id=str(uuid.uuid4()),
            operations=operations
        )
        await self.history.save_batch(batch)
        
        return batch
