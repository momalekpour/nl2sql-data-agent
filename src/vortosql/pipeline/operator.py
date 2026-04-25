from abc import ABC, abstractmethod
from typing import Any


class Operator(ABC):
    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    def execute(self, context: dict[str, Any]) -> None:
        pass
