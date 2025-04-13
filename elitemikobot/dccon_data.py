from dataclasses import dataclass

@dataclass
class DcconData:                
    id: int = 0   # dccon_id
    title: str = ""
    path: str = ""
    count: int = 0
    ext: dict[int, str] = None   # [img_num, img_ext]
    err: str = None