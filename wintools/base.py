from __future__ import annotations

from abc import ABC, abstractmethod
from tkinter import ttk
from typing import Callable

StatusCallback = Callable[[str], None]


class BaseModule(ABC):
    """Base contract for all WinTools modules."""

    name: str
    description: str = ""

    @abstractmethod
    def mount(self, parent: ttk.Frame, set_status: StatusCallback) -> None:
        """Render module UI under the parent frame."""

    @abstractmethod
    def unmount(self) -> None:
        """Release module resources when switching module."""