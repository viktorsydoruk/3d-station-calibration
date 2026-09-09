"""Class related to printing debugging data if needed"""

from typing import Any

class DebugInfo:
    """Class related to printing debugging data if needed"""
    def __init__(self, debug: bool = False):
        self.debug = debug

    def __call__(self, *text: Any, end: str ='\n'):
        if self.debug:
            print(*text, end=end)
