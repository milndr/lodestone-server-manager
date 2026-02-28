import logging
from collections.abc import Callable
from typing import Any


class FLogger:
    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _log(
        self,
        level: int,
        msg: str | Callable[[], str],
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        if self._logger.isEnabledFor(level):
            actual_msg = msg() if callable(msg) else msg
            self._logger.log(level, actual_msg, *args, **kwargs)

    def debug(
        self,
        msg: str | Callable[[], str],
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(
        self,
        msg: str | Callable[[], str],
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(
        self,
        msg: str | Callable[[], str],
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(
        self,
        msg: str | Callable[[], str],
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        self._log(logging.ERROR, msg, *args, **kwargs)

    def critical(
        self,
        msg: str | Callable[[], str],
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        self._log(logging.CRITICAL, msg, *args, **kwargs)

    def exception(
        self,
        msg: str | Callable[[], str],
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        kwargs.setdefault("exc_info", True)
        self.error(msg, *args, **kwargs)

    def is_enabled_for(self, level: int) -> bool:
        return self._logger.isEnabledFor(level)

    @property
    def level(self) -> int:
        return self._logger.level

    @level.setter
    def level(self, value: int) -> None:
        self._logger.setLevel(value)


def get_logger(name: str) -> FLogger:
    return FLogger(name)
