import logging
from enum import Enum
from functools import wraps
from typing import TYPE_CHECKING, Callable, ParamSpec, TypeVar

if TYPE_CHECKING:
    from logging import _Level


class Level(str, Enum):
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"
    ERROR = "FATAL"
    WARN = "WARN"
    INFO = "INFO"
    DEBUG = "DEBUG"
    NOTSET = "NOTSET"


P = ParamSpec("P")
R = TypeVar("R")


class _Logger(logging.Logger):
    FMT = "%(asctime)s %(filename)s:%(lineno)d %(levelname)s %(message)s"  # noqa: E501
    UVICORN_LOGGER_NAMES = ("uvicorn", "uvicorn.error", "uvicorn.access")
    UVICORN_LOGGERS = list(map(logging.getLogger, UVICORN_LOGGER_NAMES))

    def __init__(self, level: int | str = logging.DEBUG) -> None:
        """Instantiates custom logger.

        Args:
            level: Verbosity of the logger
        """
        import coloredlogs

        assert __package__
        super().__init__(name=__package__)
        coloredlogs.install(logger=self, level=level, fmt=self.FMT)

        for logger in self.UVICORN_LOGGERS:
            logger.handlers = self.handlers
            logger.propagate = False

    def setLevel(self, level: "_Level") -> None:
        for logger in self.UVICORN_LOGGERS:
            logger.setLevel(level)
            logger.handlers = self.handlers
        super().setLevel(level)

    @staticmethod
    def func(
        level: Level = Level.DEBUG,
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        def _outer(
            func: Callable[P, R],
        ) -> Callable[P, R]:
            @wraps(func)
            def _wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                method = getattr(Logger, level.value.lower(), None)

                msg = f"There is no {method} method in class Logger"
                assert method, msg

                name = func.__qualname__
                msg = f"Function {name} used with [{args}] and {{{kwargs}}}"
                method(msg)

                return func(*args, **kwargs)

            return _wrapper

        return _outer


Logger = _Logger()
