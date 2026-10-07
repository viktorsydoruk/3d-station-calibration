"""Class related to printing debugging data if needed"""

from typing import Any

class DebugInfo:
    """Class related to printing debugging data if needed"""
    def __init__(self, debug: bool = False):
        self.debug = debug

    def __call__(self, *text: Any, end: str ='\n', sep: str = ' ', print_anyway: bool = False) -> None:
        if self.debug or print_anyway:
            print(*text, end=end, sep=sep)
