import abc
from typing import Any


class BaseAdapter(abc.ABC):
    """
    Abstract base class for database adapters.
    Each adapter must implement connect, run_query, and close_connection.
    """

    @abc.abstractmethod
    def connect(self) -> None:
        """Establish the database connection."""
        pass

    @abc.abstractmethod
    def run_query(
        self, query: str, return_cursor: bool = False
    ) -> tuple[list[str], list[Any]] | Any:
        """
        Execute a query and optionally return a cursor or the raw results.
        """
        pass

    @abc.abstractmethod
    def close_connection(self) -> None:
        """Close the database connection."""
        pass
