import json
import webview
from pathlib import Path
from webview.dom import DOMEventHandler

from api import API
from core.config import ConfigManager

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".tiff", ".bmp",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v",
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    ".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".rtf", ".odt", ".ods", ".odp",
    ".html", ".htm", ".xml", ".rss"
}


# Threshold for streaming vs batch file delivery
STREAM_THRESHOLD = 200
STREAM_CHUNK_SIZE = 100


def main():
    # Initialize API
    api = API()
    
    # Load config for window settings
    config_manager = ConfigManager()
    config = config_manager.get_sync()
    
    # Create window
    window = webview.create_window(
        title="Pynamer",
        url=str(Path(__file__).parent / "assets" / "index.html"),
        js_api=api,
        width=config.window_width,
        height=config.window_height,
        min_size=(600, 400),
        easy_drag=False,
        text_select=True
    )
    
    # Pass window reference to API
    api.set_window(window)
    
    def attach_drop_handler():
        window.events.loaded.wait()

        def get_drop_depth() -> int:
            config = ConfigManager().get_sync()
            return config.processing.drop_folder_depth if config else 1

        def collect_files_generator(folder: Path, depth: int):
            """Generator that yields files one at a time to avoid blocking."""
            if depth < 0:
                return
            try:
                for entry in folder.iterdir():
                    if entry.is_file():
                        if entry.suffix.lower() in SUPPORTED_EXTENSIONS:
                            yield str(entry)
                    elif entry.is_dir() and depth > 0:
                        yield from collect_files_generator(entry, depth - 1)
            except PermissionError:
                return

        def expand_paths_streamed(paths: list[str], on_chunk, on_complete):
            """
            Expand paths and stream results in chunks.
            Runs in a separate thread to avoid blocking the UI.
            """
            import threading
            
            def worker():
                depth = get_drop_depth()
                seen: set[str] = set()
                chunk: list[str] = []
                total_sent = 0
                
                for raw in paths:
                    candidate = Path(raw)
                    if candidate.is_dir():
                        for file_path in collect_files_generator(candidate, depth):
                            if file_path not in seen:
                                seen.add(file_path)
                                chunk.append(file_path)
                                
                                # Send chunk when it reaches threshold
                                if len(chunk) >= STREAM_CHUNK_SIZE:
                                    on_chunk(chunk)
                                    total_sent += len(chunk)
                                    chunk = []
                    elif candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
                        file_str = str(candidate)
                        if file_str not in seen:
                            seen.add(file_str)
                            chunk.append(file_str)
                
                # Send remaining files
                if chunk:
                    on_chunk(chunk)
                    total_sent += len(chunk)
                
                on_complete(total_sent)
            
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()

        def expand_paths_batch(paths: list[str]) -> list[str]:
            """Original batch expansion for small drops."""
            depth = get_drop_depth()
            results: list[str] = []
            for raw in paths:
                candidate = Path(raw)
                if candidate.is_dir():
                    for file_path in collect_files_generator(candidate, depth):
                        results.append(file_path)
                elif candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
                    results.append(str(candidate))
            return sorted(set(results))

        def handle_drop(event):
            files = event.get("dataTransfer", {}).get("files", [])
            paths: list[str] = []
            for file_info in files:
                path = file_info.get("pywebviewFullPath") or file_info.get("path")
                if path:
                    paths.append(path)
            
            if not paths:
                return
            
            # Check if any path is a directory (potential large scan)
            has_directories = any(Path(p).is_dir() for p in paths)
            
            if has_directories:
                # Use streamed approach for directories
                window.evaluate_js("setStatus('Scanning folders...')")
                
                def on_chunk(chunk: list[str]):
                    window.evaluate_js(f"window.onFilesDropped({json.dumps(chunk)})")
                
                def on_complete(total: int):
                    if total > 0:
                        window.evaluate_js(f"setStatus('Found {total} files')")
                    else:
                        window.evaluate_js("setStatus('No supported files found')")
                
                expand_paths_streamed(paths, on_chunk, on_complete)
            else:
                # Use simple batch approach for direct file drops
                expanded = expand_paths_batch(paths)
                if expanded:
                    window.evaluate_js(f"window.onFilesDropped({json.dumps(expanded)})")

        def swallow_event(_event):
            return None

        window.dom.document.events.dragenter += DOMEventHandler(swallow_event, True, False)
        window.dom.document.events.dragover += DOMEventHandler(swallow_event, True, False)
        window.dom.document.events.drop += DOMEventHandler(handle_drop, True, False)

    # Start the application
    webview.start(attach_drop_handler, debug=False)


if __name__ == "__main__":
    main()
