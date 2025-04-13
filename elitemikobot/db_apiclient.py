from enum import Enum
import json
import aiohttp
from typing import Any, Dict, Optional

from yarl import URL
from elitemikobot.logger import Logger
from elitemikobot.sticker_data import StickerData


class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"
    HEAD = "HEAD"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    

class DbApiClient:    
    def __init__(self, base_url: str, sticker: StickerData) -> None:
        self.base_url = base_url        
        self.sticker = sticker
        self._session: Optional[aiohttp.ClientSession] = None
        self.logger = Logger(name="DbApiClient_Log")


    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self


    async def __aexit__(self, exc_type, exc_value, traceback):       
        if self._session:
            await self._session.close()
            self._session = None


    def _get_url(self, endpoint: str, is_use_option_flag: bool = True) -> str:        
        if is_use_option_flag:
            return f"{self.base_url}/stickers/{self.sticker.id}/{self.sticker.option_flag}/{endpoint}"       
        
        return f"{self.base_url}/stickers/{endpoint}"


    # API 요청
    async def _request(self, method: HttpMethod, url: str, **kwargs) -> Optional[Dict[str, Any]]:        
        for attempt in range(3):  # 최대 3번 재시도
            try:
                async with self._session.request(method.value, url, **kwargs) as response:
                    if method is HttpMethod.HEAD:
                        if response.status in {200, 201}:
                            return True
                        elif response.status == 404:
                            return False
                        else:
                            response.raise_for_status()
                    else:    
                        if response.status in {200, 201}:
                            return await response.json()
                        elif response.status == 404:
                            return None
                        else:
                            response.raise_for_status()

            except aiohttp.ClientError as e:
                self.logger.error(
                    action="ClientError DbApiClient",
                    user=" ",
                    data={"method": f"{method}", "url": f"{url}", "kwargs": f"{kwargs}"},
                    message=f"재시도 {attempt + 1}/3 - {e}"
                )
                last_exception = e
            except Exception as e:
                self.logger.error(
                    action="Exception DbApiClient",
                    user=" ",
                    data={"method": f"{method}", "url": f"{url}", "kwargs": f"{kwargs}"},
                    message=f"재시도 {attempt + 1}/3 - {e}"
                )
                last_exception = e

        if last_exception is not None:
            raise last_exception
        
        return None


    # 스티커 존재 여부 확인
    async def check_sticker_exists(self) -> bool:        
        url = self._get_url("exists")
        response = await self._request(HttpMethod.GET, url)
        return response.get("exists", True) if response else False
                

    # 스티커 URL 존재 여부 확인
    async def check_url_exists(self) -> bool:        
        url = str(URL(self._get_url("checkurl", is_use_option_flag=False)).with_query({"url": self.sticker.url}))
        response = await self._request(HttpMethod.GET, url)
        return response.get("exists", False) if response else False
                

    # 스티커 URL 가져오기
    async def get_sticker_url(self) -> Optional[str]:        
        url = self._get_url("url")
        response = await self._request(HttpMethod.GET, url)
        return response.get("url") if response else None   


    # 스티커 등록
    async def register_sticker(self) -> Dict[str, Any]:        
        url = self._get_url("", is_use_option_flag=False)
        json_payload = self.sticker.to_csharp_dto()
        return await self._request(HttpMethod.POST, url, json=json_payload)      