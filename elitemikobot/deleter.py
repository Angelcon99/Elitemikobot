import asyncio
import shutil
import logging
from pathlib import Path
from typing import Union

class Deleter:
    _lock = asyncio.Lock()
    

    @staticmethod
    async def _delete_path(path: Path) -> None:
        try:
            if path.exists():
                await asyncio.to_thread(shutil.rmtree, path)
        except Exception as e:
            pass
    

    @staticmethod
    async def delete_all(img_path: Union[str, Path], sticker_path: Union[str, Path]) -> None:
        # 문자열 입력이면 Path 객체로 변환
        img_path = Path(img_path) if not isinstance(img_path, Path) else img_path
        sticker_path = Path(sticker_path) if not isinstance(sticker_path, Path) else sticker_path

        async with Deleter._lock: 
            try:
                await asyncio.gather(
                    Deleter._delete_path(img_path),
                    Deleter._delete_path(sticker_path)
                )
            except Exception as e:
                pass
        
        
    @staticmethod
    async def delete_dccon(img_path: Union[str, Path]) -> None:
        img_path = Path(img_path) if not isinstance(img_path, Path) else img_path
        async with Deleter._lock:
            try:
                await Deleter._delete_path(img_path)
            except Exception as e:
                pass
