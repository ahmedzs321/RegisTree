# ui/undo_manager.py

from typing import Callable, List, Tuple


class UndoManager:
    """
    Simple in-memory undo/redo manager.

    Each entry is a tuple:
        (undo_func, redo_func, description)

    - undo() calls the last undo_func and pushes it onto the redo stack.
    - redo() calls the last redo_func and pushes it back onto the undo stack.
    - Everything lives only in memory → cleared automatically on app restart.
    """

    def __init__(self) -> None:
        self._undo_stack: List[Tuple[Callable[[], None], Callable[[], None], str]] = []
        self._redo_stack: List[Tuple[Callable[[], None], Callable[[], None], str]] = []

    # --------------------------------------------------------------
    # Public API
    # --------------------------------------------------------------
    def push(self, undo_func: Callable[[], None],
             redo_func: Callable[[], None],
             description: str = "") -> None:
        """
        Register a new action. You call this AFTER you've already
        performed the 'redo' operation once.

        Any existing redo history is cleared when you push a new action.
        """
        self._undo_stack.append((undo_func, redo_func, description))
        self._redo_stack.clear()

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> bool:
        """Undo the most recent action. Returns True if something was undone."""
        if not self._undo_stack:
            return False

        undo_func, redo_func, desc = self._undo_stack.pop()
        undo_func()
        self._redo_stack.append((undo_func, redo_func, desc))
        return True

    def redo(self) -> bool:
        """Redo the most recently undone action. Returns True if something was redone."""
        if not self._redo_stack:
            return False

        undo_func, redo_func, desc = self._redo_stack.pop()
        redo_func()
        self._undo_stack.append((undo_func, redo_func, desc))
        return True

    def clear(self) -> None:
        """Completely clear history (not strictly required by your spec)."""
        self._undo_stack.clear()
        self._redo_stack.clear()
