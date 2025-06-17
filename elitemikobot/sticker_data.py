from dataclasses import asdict, dataclass, field
import datetime as dt
from typing import List
from elitemikobot.dccon_data import DcconData
from elitemikobot.option_flag import OptionFlag


@dataclass
class StickerData:                
    id: int = 0
    option_flag: OptionFlag = OptionFlag(0) 
    title: str = ""
    date_time: dt.datetime = dt.datetime.min
    url: str = ""
    user_id: int = 0
    user_name: str = ""
    
    merge_nums: List[int] = field(default_factory=list)
    count: int = 0
    ext: dict[int, str] = field(default_factory=dict)


    def __post_init__(self):
        # option_flag : int -> OptionFlag 변환
        if isinstance(self.option_flag, int):
            self.option_flag = OptionFlag(self.option_flag)


    def to_csharp_dto(self) -> dict: 
        return {
            "stickerId": self.id,
            "stickerOptionFlag": int(self.option_flag),   # OptionFlag -> int 변환
            "stickerTitle": self.title,
            "registedDateTime": self.date_time.isoformat(),   # ex) 2024-01-01T12:00:00
            "url": self.url,
            "userId": self.user_id,
            "userName": self.user_name            
        }            


    def update_from_dccon_data(self, dccon_data: DcconData) -> None:
        self.title = dccon_data.title
        self.count = dccon_data.count
        self.ext = dccon_data.ext
    
    
    @classmethod
    def from_csharp_dto(cls, data: dict):
        return cls(
            id=data["stickerId"],
            option_flag=OptionFlag(data["stickerOptionFlag"]),
            title=data["stickerTitle"],
            date_time=dt.datetime.fromisoformat(data["registedDateTime"]),
            url=data["url"],
            user_id=data["userId"],
            user_name=data["userName"]
        )