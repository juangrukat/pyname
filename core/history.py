import json
import aiofiles
from pathlib import Path
from datetime import datetime
from typing import Optional

from .models import HistoryBatch, RenameOperation


class HistoryManager:
    """Manage rename history for undo capability."""
    
    def __init__(self, history_file: Path | None = None):
        self.history_file = history_file or Path("data/history.json")
        self._ensure_data_dir()
    
    def _ensure_data_dir(self) -> None:
        """Ensure the data directory exists."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
    
    async def save_batch(self, batch: HistoryBatch) -> None:
        """Save a batch of operations to history."""
        history = await self.load_history()
        history.append(batch)
        
        # Keep only last 100 batches
        if len(history) > 100:
            history = history[-100:]
        
        await self._write_history(history)
    
    async def load_history(self) -> list[HistoryBatch]:
        """Load all history batches."""
        if not self.history_file.exists():
            return []
        
        try:
            async with aiofiles.open(self.history_file, "r") as f:
                content = await f.read()
                data = json.loads(content)
                return [HistoryBatch(**batch) for batch in data]
        except (json.JSONDecodeError, ValueError):
            return []
    
    async def _write_history(self, history: list[HistoryBatch]) -> None:
        """Write history to file."""
        async with aiofiles.open(self.history_file, "w") as f:
            data = [batch.model_dump(mode="json") for batch in history]
            await f.write(json.dumps(data, indent=2, default=str))
    
    async def get_last_batch(self) -> Optional[HistoryBatch]:
        """Get the most recent undoable batch."""
        history = await self.load_history()
        
        # Find last batch that hasn't been undone
        for batch in reversed(history):
            if not batch.undone:
                return batch
        
        return None
    
    async def undo_batch(self, batch_id: str) -> tuple[int, list[str]]:
        """
        Undo a batch of rename operations.
        
        Returns:
            Tuple of (success_count, error_messages)
        """
        history = await self.load_history()
        batch = next((b for b in history if b.batch_id == batch_id), None)
        
        if not batch:
            return 0, [f"Batch not found: {batch_id}"]
        
        if batch.undone:
            return 0, ["Batch has already been undone"]
        
        success_count = 0
        errors: list[str] = []
        
        # Undo in reverse order
        for op in reversed(batch.operations):
            try:
                new_path = Path(op.new_path)
                original_path = Path(op.original_path)
                
                if new_path.exists():
                    new_path.rename(original_path)
                    success_count += 1
                else:
                    errors.append(f"File not found: {new_path}")
            
            except OSError as e:
                errors.append(f"Failed to restore {op.original_name}: {e}")
        
        # Mark batch as undone
        batch.undone = True
        batch.undone_at = datetime.now()
        await self._write_history(history)
        
        return success_count, errors
    
    async def get_statistics(self) -> dict:
        """Get history statistics."""
        history = await self.load_history()
        
        total_operations = sum(len(b.operations) for b in history)
        undone_batches = sum(1 for b in history if b.undone)
        
        return {
            "total_batches": len(history),
            "total_operations": total_operations,
            "undone_batches": undone_batches,
            "active_batches": len(history) - undone_batches
        }