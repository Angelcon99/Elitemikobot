from __future__ import annotations
from enum import IntFlag

class OptionFlag(IntFlag):    
    OVERWRITE = 1       # 0000 0000 0000 0000 0000 0000 0000 0001 덮어쓰기
    MERGE = 2           # 0000 0000 0000 0000 0000 0000 0000 0010 디시콘 합치기

    @staticmethod
    def has_flag(option: int | OptionFlag, flag: OptionFlag) -> bool:
        return (option & flag) != 0

    @staticmethod
    def set_flag(option: int | OptionFlag, flag: OptionFlag) -> OptionFlag:
        return OptionFlag(option | flag)