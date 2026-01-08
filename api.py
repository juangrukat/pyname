from __future__ import annotations
import asyncio
import threading
import json
from pathlib import Path
from typing import Callable
import webview

from core.config import ConfigManager
from core.processor import FileProcessor
from core.history import HistoryManager
from core.dependencies import DependencyChecker
from core.models import AppConfig, ProcessingStatus, ProcessingState
from core.prompts import PromptBuilder


class API:
    """
    JavaScript ↔ Python bridge for pywebview.
    
    All methods are called synchronously from JS.
    Long-running operations spawn threads with their own event loops.
    """
    
    def __init__(self):
        self._window: webview.Window | None = None
        self._config_manager = ConfigManager()
        self._history_manager = HistoryManager()
        self._processor: FileProcessor | None = None
        self._processing_thread: threading.Thread | None = None
    
    def set_window(self, window: webview.Window) -> None:
        """Set the pywebview window reference."""
        self._window = window
    
    # ─────────────────────────────────────────────────────────────────────────
    # File Selection
    # ─────────────────────────────────────────────────────────────────────────
    
    def select_files(self) -> str:
        """
        Open native file picker dialog.
        
        Returns:
            JSON string with list of selected file paths
        """
        if not self._window:
            return json.dumps({"error": "Window not initialized"})
        
        file_types = (
            "Image files (*.jpg;*.jpeg;*.png;*.gif;*.webp;*.heic)",
            "Video files (*.mp4;*.mov;*.avi;*.mkv;*.webm)",
            "Documents (*.pdf;*.doc;*.docx;*.ppt;*.pptx;*.xls;*.xlsx;*.rtf;*.odt;*.ods;*.odp;*.txt;*.md;*.csv;*.html;*.xml;*.rss)",
            "All files (*.*)"
        )
        
        result = self._window.create_file_dialog(
            self._dialog_type("open"),
            allow_multiple=True,
            file_types=file_types
        )
        
        if result:
            return json.dumps({"files": list(result)})
        return json.dumps({"files": []})
    
    def select_folder(self) -> str:
        """
        Open native folder picker dialog.
        
        Returns:
            JSON string with selected folder path
        """
        if not self._window:
            return json.dumps({"error": "Window not initialized"})
        
        result = self._window.create_file_dialog(self._dialog_type("folder"))
        
        if result and len(result) > 0:
            return json.dumps({"folder": result[0]})
        return json.dumps({"folder": None})
    
    # ─────────────────────────────────────────────────────────────────────────
    # Configuration
    # ─────────────────────────────────────────────────────────────────────────
    
    def get_config(self) -> str:
        """Get current configuration as JSON."""
        config = self._config_manager.get_sync()
        return config.model_dump_json()
    
    def save_config(self, config_json: str) -> str:
        """
        Save configuration.
        
        Args:
            config_json: JSON string with config values
        """
        try:
            data = json.loads(config_json)
            
            def run():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    config = AppConfig(**data)
                    loop.run_until_complete(self._config_manager.save(config))
                    return json.dumps({"success": True})
                finally:
                    loop.close()
            
            return run()
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_prompt_defaults(self) -> str:
        """Get built-in prompt defaults."""
        return json.dumps({
            "system": {
                "image": PromptBuilder.SYSTEM_PROMPT_IMAGE,
                "video": PromptBuilder.SYSTEM_PROMPT_VIDEO,
                "document": PromptBuilder.SYSTEM_PROMPT_DOCUMENT,
                "generic": PromptBuilder.SYSTEM_PROMPT_BASE
            }
        })
    
    # ─────────────────────────────────────────────────────────────────────────
    # Processing
    # ─────────────────────────────────────────────────────────────────────────
    
    def start_processing(self, file_paths_json: str) -> str:
        """
        Start processing files.
        
        Args:
            file_paths_json: JSON string with list of file paths
        """
        if self._processing_thread and self._processing_thread.is_alive():
            return json.dumps({"error": "Processing already in progress"})
        
        try:
            file_paths = [Path(p) for p in json.loads(file_paths_json)]
        except (json.JSONDecodeError, TypeError) as e:
            return json.dumps({"error": f"Invalid file paths: {e}"})
        
        # Start processing in background thread
        self._processing_thread = threading.Thread(
            target=self._run_processing,
            args=(file_paths,),
            daemon=True
        )
        self._processing_thread.start()
        
        return json.dumps({"status": "started"})
    
    def _run_processing(self, file_paths: list[Path]) -> None:
        """Run processing in a separate thread with its own event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            config = self._config_manager.get_sync()
            self._processor = FileProcessor(config)
            
            def on_status(status: ProcessingStatus):
                self._emit_to_js("onProcessingStatus", status.model_dump_json())
            
            results = loop.run_until_complete(
                self._processor.process_files(file_paths, on_status)
            )
            
            # Send final results
            self._emit_to_js("onProcessingComplete", json.dumps({
                "results": [r.model_dump(mode="json") for r in results]
            }))
        
        except Exception as e:
            self._emit_to_js("onProcessingError", json.dumps({"error": str(e)}))
        
        finally:
            loop.close()
    
    def stop_processing(self) -> str:
        """Request cancellation of current processing."""
        if self._processor:
            self._processor.cancel()
            return json.dumps({"status": "cancelling"})
        return json.dumps({"status": "not_running"})
    
    def pause_processing(self) -> str:
        """Pause current processing."""
        if self._processor:
            self._processor.pause()
            return json.dumps({"status": "paused"})
        return json.dumps({"status": "not_running"})
    
    def resume_processing(self) -> str:
        """Resume paused processing."""
        if self._processor:
            self._processor.resume()
            return json.dumps({"status": "resumed"})
        return json.dumps({"status": "not_running"})
    
    def apply_results(self, results_json: str) -> str:
        """
        Apply approved rename operations.
        
        Args:
            results_json: JSON string with results to apply
        """
        if not self._processor:
            return json.dumps({"error": "No processor available"})
        
        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                from core.models import FileProcessingResult
                
                results_data = json.loads(results_json)
                results = [FileProcessingResult(**r) for r in results_data]
                approved_count = sum(1 for r in results if r.status == "approved")

                if self._processor.config.processing.dry_run:
                    return json.dumps({
                        "success": True,
                        "dry_run": True,
                        "preview_count": approved_count,
                        "applied_count": 0
                    })
                
                batch = loop.run_until_complete(
                    self._processor.apply_results(results)
                )
                
                return json.dumps({
                    "success": True,
                    "batch_id": batch.batch_id,
                    "applied_count": len(batch.operations),
                    "dry_run": False
                })
            except Exception as e:
                return json.dumps({"error": str(e)})
            finally:
                loop.close()
        
        return run()
    
    # ─────────────────────────────────────────────────────────────────────────
    # History
    # ─────────────────────────────────────────────────────────────────────────
    
    def get_history(self) -> str:
        """Get processing history."""
        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                history = loop.run_until_complete(self._history_manager.load_history())
                return json.dumps([h.model_dump(mode="json") for h in history])
            finally:
                loop.close()
        
        return run()
    
    def undo_last_batch(self) -> str:
        """Undo the most recent batch operation."""
        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                batch = loop.run_until_complete(self._history_manager.get_last_batch())
                if not batch:
                    return json.dumps({"error": "No batch to undo"})
                
                success, errors = loop.run_until_complete(
                    self._history_manager.undo_batch(batch.batch_id)
                )
                
                return json.dumps({
                    "success": True,
                    "restored_count": success,
                    "errors": errors
                })
            finally:
                loop.close()
        
        return run()
    
    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────
    
    def check_dependencies(self) -> str:
        """Check external dependencies."""
        checker = DependencyChecker()
        results = checker.check_all()
        return json.dumps({
            name: {
                "available": dep.available,
                "version": dep.version,
                "install_hint": dep.install_hint
            }
            for name, dep in results.items()
        })
    
    def open_folder(self, path: str) -> str:
        """Open a folder in Finder."""
        import subprocess
        try:
            subprocess.run(["open", path], check=True)
            return json.dumps({"success": True})
        except subprocess.CalledProcessError as e:
            return json.dumps({"error": str(e)})
    
    def open_file(self, path: str) -> str:
        """Open a file with the default application."""
        import subprocess
        try:
            subprocess.run(["open", path], check=True)
            return json.dumps({"success": True})
        except subprocess.CalledProcessError as e:
            return json.dumps({"error": str(e)})
    
    def _emit_to_js(self, event_name: str, data: str) -> None:
        """Send an event to the JavaScript frontend."""
        if self._window:
            self._window.evaluate_js(f"window.{event_name}({data})")

    @staticmethod
    def _dialog_type(kind: str):
        """Return the correct dialog enum for the current pywebview version."""
        if hasattr(webview, "FileDialog"):
            return webview.FileDialog.OPEN if kind == "open" else webview.FileDialog.FOLDER
        return webview.OPEN_DIALOG if kind == "open" else webview.FOLDER_DIALOG
