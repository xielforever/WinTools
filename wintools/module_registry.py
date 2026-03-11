from __future__ import annotations

from typing import Dict, Type

from wintools.base import BaseModule
from modules.dir_size.ui import DirSizeModule


def get_module_registry() -> Dict[str, Type[BaseModule]]:
    """Register modules here for left-side navigation."""
    return {
        DirSizeModule.name: DirSizeModule,
    }
