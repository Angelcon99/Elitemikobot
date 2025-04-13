from __future__ import annotations
from enum import IntFlag

class OptionFlag(IntFlag):
    EMP = 1             # 0000 0000 0000 0000 0000 0000 0000 0001
    OVERWRITE = 2       # 0000 0000 0000 0000 0000 0000 0000 0010 덮어쓰기
    MERGE = 4           # 0000 0000 0000 0000 0000 0000 0000 0100 디시콘 합치기

    @staticmethod
    def has_flag(option: int | OptionFlag, flag: OptionFlag) -> bool:
        return (option & flag) != 0

    @staticmethod
    def set_flag(option: int | OptionFlag, flag: OptionFlag) -> OptionFlag:
        return OptionFlag(option | flag)