import asyncio
from pathlib import Path
from typing import Any, Dict
import aiohttp
import os
from PIL import Image
from aiofiles import open as aio_open
from elitemikobot.logger import Logger
from elitemikobot.dccon_data import DcconData
from elitemikobot.deleter import Deleter


class Dccon:
    def __init__(self):        
        self.logger = Logger(name="Dccon_Log")


    async def process_dccon(self, dccon_id: int, save_path: str) -> DcconData:            
        try:
            dccon_meta = await self._fetch_dccon(dccon_id)
            if dccon_meta is None:
                return None                    

            max_try = 3
            for _ in range(1, max_try + 1):
                data_dict = await self._save_dccon_data(dccon_meta, dccon_id, save_path)                      
                
                if data_dict["count"] == 0:
                    await Deleter.delete_dccon(img_path=Path(save_path))
                    return None

                is_success, err = await self._validate_dccon(save_path)
                if is_success:                
                    break
                else:
                    data_dict['err'] = err 
                    await Deleter.delete_dccon(img_path=Path(save_path))
                            
            return DcconData(**data_dict)
            
        except ValueError as e:            
            self.logger.error(
                action="ValueError Dccon",
                user=" ",
                data={"dccon_id": dccon_id, "status": "value_error"},
                message=f"{e}"
            )
            return None

        except Exception as e:
            self.logger.error(
                action="Exception Dccon",
                user="",
                data={"dccon_id": dccon_id, "status": "except"},
                message=f"{e}"
            ) 
            return None


    # 디시콘 메타데이터 요청
    async def _fetch_dccon(self, dccon_id: int) -> Dict[str, Any]:        
        url = "https://dccon.dcinside.com/index/package_detail"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest"
        }
        data = {"package_idx": dccon_id}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=data) as response:
                    return await response.json(content_type="text/html")
                
        except Exception as e:
            self.logger.error(
                action="Invalid JSON Response _fetch_dccon",
                user=" ",
                data={"dccon_id": dccon_id, "status": "json_error"},
                message=f"{e}"
            )
            return None  # JSON 파싱 실패                      


    # 디시콘 이미지 저장, 스티커 데이터 생성
    async def _save_dccon_data(self, metadata: Dict[str, Any], dccon_id: int, path: str) -> Dict[str, Any]:        
        save_dir = Path(path)
        save_dir.mkdir(parents=True, exist_ok=True)
            
        dccon_data = {
            "title": metadata["info"]["title"],
            "path": str(save_dir),
            "id": dccon_id,
            "count": 0,
            "ext": {}
        }
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i, detail in enumerate(metadata['detail'], start=1):                
                img_url = f"https://dcimg5.dcinside.com/dccon.php?no={detail['path']}"
                dccon_data['ext'][i] = detail['ext']                                
                tasks.append(self._download_dccon(session, img_url, save_dir, i, detail['ext']))

            dccon_data['count'] = len(tasks)
            
            await asyncio.gather(*tasks)
            
            await self._convert_single_frame_gif_to_png(save_dir, dccon_id, dccon_data)

        return dccon_data        


    # GIF 파일 중 프레임이 1개인 파일을 PNG로 변환
    async def _convert_single_frame_gif_to_png(self, save_dir: Path, dccon_id: int, dccon_data: Dict[str, Any]) -> None:               
        for file_path in save_dir.glob("*.gif"):
            try:                
                with Image.open(file_path) as img:
                    # n_frames 속성이 없으면 1프레임으로 간주
                    frame_count = getattr(img, "n_frames", 1)

                    if frame_count == 1:                        
                        num = int(file_path.stem)
                        png_path = file_path.with_suffix(".png")
                        img.save(png_path, "PNG")                              
                        dccon_data["ext"][num] = "png"
                        
            except Exception as e:
                raise e


    async def _download_dccon(self, session: aiohttp.ClientSession, url: str, save_dir: Path, num: int, ext: str) -> None:        
        headers = {"referer": "https://dccon.dcinside.com/"}
        file_path = save_dir / f"{num}.{ext}"

        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                async with aio_open(file_path, "wb") as f:
                    await f.write(await response.read())
                    

    # 다운로드한 디시콘 이미지 유효성 검사
    async def _validate_dccon(self, path: str) -> tuple[bool, str]:        
        p = Path(path)
        imgs = list(p.glob('*'))
        
        if not imgs:            
            return (False, "No images downloaded")

        for img in imgs:                        
            if img.stat().st_size <= 1024:
                return (False, "dccon download failed")
            
        return (True, None)
