import logging
from enum import Enum
from functools import wraps
from typing import Callable, ParamSpec, TypeVar


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

    def __init__(self, level: int | str = logging.DEBUG) -> None:
        """Instantiates custom logger.

        Args:
            level: Verbosity of the logger
        """
        import coloredlogs

        assert __package__
        super().__init__(name=__package__)
        coloredlogs.install(logger=self, level=level, fmt=self.FMT)

        uvicorn_loggers = ["uvicorn", "uvicorn.error", "uvicorn.access"]
        for logger_name in uvicorn_loggers:
            logger = logging.getLogger(logger_name)
            logger.handlers = self.handlers
            logger.propagate = False

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
