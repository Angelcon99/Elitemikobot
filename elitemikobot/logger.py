import inspect
import logging
from datetime import date
from pathlib import Path


class Logger:
    LOG_PATH = Path(__file__).parent.parent / "logs"


    def __init__(self, name: str) -> None:
        self.LOG_PATH.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(name=name)
        self.logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            '| %(asctime)s | %(name)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        file_handler = logging.FileHandler(filename=str(self.LOG_PATH / f"{date.today()}.log"))
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        self.logger.addHandler(stream_handler)


    # 로그 메세지 포맷
    def _format_message(self, action: str, user: str, data: dict, message: str) -> str:
        caller = inspect.stack()[2]
        module = Path(caller.filename).name
        func = caller.function
        line_no = caller.lineno

        if data:
            data_str = f"{{{', '.join(f'{key}={value}' for key, value in data.items())}}}"
        else:
            data_str = ""
            
        return (
            f"[{module}:{func}:{line_no}] "
            f"Action: {action}, User: {user}, Data: {data_str} | {message}"
        )


    def debug(self, action: str, user: int, data: dict, message: str) -> None:
        self.logger.debug(self._format_message(action, user, data, message))


    def info(self, action: str, user: int, data: dict, message: str) -> None:
        self.logger.info(self._format_message(action, user, data, message))


    def warning(self, action: str, user: int, data: dict, message: str) -> None:
        self.logger.warning(self._format_message(action, user, data, message))


    def error(self, action: str, user: int, data: dict, message: str) -> None:
        self.logger.error(self._format_message(action, user, data, message))


    def critical(self, action: str, user: int, data: dict, message: str) -> None:
        self.logger.critical(self._format_message(action, user, data, message))