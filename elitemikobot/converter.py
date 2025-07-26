import os
import asyncio
import aiofiles
from pathlib import Path
from elitemikobot.logger import Logger


class Converter:
    MAX_DURATION_MS = 3000 - 1
    MAX_SIZE_KB = 256        
    TOLERANCE_KB = 25
    MAX_ATTEMPTS = 5
    DEFAULT_FRAME_DURATION_MS = 60

    FORMAT = "yuva420p"
    PIX_FMT = "yuva420p"

    def __init__(self,dccon_id: int, num: int, input_folder: str, out_path: str, frame_durations: list[int], x_size: int = 512, y_size: int = 512):        
        self.dccon_id = dccon_id
        self.num = num
        self.logger = Logger(name="Converter_Log")
        self.input_folder = Path(input_folder)
        self.output_path = Path(out_path)
        self.frame_durations = frame_durations        
        self.frame_info = self.input_folder / "frame_info.txt"
        self.x_size = x_size
        self.y_size = y_size


    # GIF → webm
    async def convert_video(self) -> None:        
        try:
            await self._adjust_durations()
            total_duration = await self._generate_frame_info()
            bitrate_kbps = self._calculate_bitrate(self.MAX_SIZE_KB, total_duration)
            await self._optimize_bitrate(bitrate_kbps, total_duration)

        except FileNotFoundError as e:
            self.logger.error(
                action="FileNotFoundError Converter",
                user=" ",
                data={"dccon_id": f"{self.dccon_id}", "num": f"{self.num}"},
                message=f"{e}"
            )
        except RuntimeError as e:
            self.logger.error(
                action="RuntimeError Converter",
                user=" ",
                data={"dccon_id": f"{self.dccon_id}", "num": f"{self.num}"},
                message=f"{e}"
            )
        except Exception as e:
            self.logger.error(
                action="Exception Converter",
                user=" ",
                data={"dccon_id": f"{self.dccon_id}", "num": f"{self.num}"},
                message=f"{e}"
            )


    # 듀레이션 조절
    async def _adjust_durations(self) -> None:        
        total_duration = sum(self.frame_durations)

        # 듀레이션 정보가 없는 경우 임의의 듀레이션 부여
        if total_duration == 0:        
            self.frame_durations = [self.DEFAULT_FRAME_DURATION_MS for _ in self.frame_durations]

        if total_duration > self.MAX_DURATION_MS:
            scale_factor = self.MAX_DURATION_MS / total_duration
            self.frame_durations = [int(duration * scale_factor) for duration in self.frame_durations]


    # FFmpeg concat 파일 포맷에 맞는 frame_info.txt 생성
    # 각 프레임 이미지 파일과 재생 시간(duration) 정보를 작성
    async def _generate_frame_info(self) -> float:        
        total_duration = 0.0

        async with aiofiles.open(str(self.frame_info), 'w') as f:
            for i, duration in enumerate(self.frame_durations):
                filename = f"{i:03}.png"
                await f.write(f"file '{filename}'\n")

                duration_seconds = float(duration) / 1000  # ms -> s
                total_duration += duration_seconds                          
                await f.write(f"duration {duration_seconds}\n")                
            
            # 마지막 프레임 파일
            await f.write(f"file '{filename}'\n")

        return round(total_duration, 2)


    def _calculate_bitrate(self, file_size_kb: int, duration_sec: float) -> int:       
        return int((file_size_kb * 8) / duration_sec)

    
    # 비트레이트 조정
    async def _optimize_bitrate(self, initial_bitrate: int, total_duration: float) -> None:       
        bitrate = initial_bitrate

        # 비트레이트 최적화
        for _ in range(self.MAX_ATTEMPTS):
            await self._encode_video(bitrate, total_duration)
            file_size_kb = await self._get_file_size()
            adjustment = self._adjust_bitrate(file_size_kb)
            if adjustment == 0:
                break
            bitrate = max(bitrate + adjustment, 1)
        else:            
            # 최대 시도 횟수 초과 시, 강제로 비트레이트를 줄이면서 크기 조절
            while await self._get_file_size() > self.MAX_SIZE_KB:
                bitrate = max(bitrate - 25, 1)
                await self._encode_video(bitrate, total_duration)


    # 비트레이트 조정값 결정
    def _adjust_bitrate(self, file_size_kb: float) -> int:        
        diff_kb = file_size_kb - self.MAX_SIZE_KB
        if diff_kb <= 0 and abs(diff_kb) <= self.TOLERANCE_KB:
            return 0

        step = 150 if abs(diff_kb) > 100 else 100 if abs(diff_kb) > 50 else 50 if abs(diff_kb) > 25 else 25
        return -step if diff_kb > 0 else step

    # FFmpeg 비디오 인코딩
    async def _encode_video(self, bitrate_kbps: int, total_duration: float) -> None:        
        command = (
            f'ffmpeg -f concat -safe 0 -i "{str(self.frame_info)}" '
            f'-vf scale={self.x_size}:{self.y_size},format={self.FORMAT} '
            f'-c:v libvpx-vp9 -b:v {bitrate_kbps}k -pix_fmt {self.PIX_FMT} '
            f'-an -sn -y -loglevel warning -hide_banner -stats '
            f'-t {total_duration} '
            f'"{str(self.output_path)}"'
        )
        
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {stderr.decode()}")


    async def _get_file_size(self) -> float:        
        loop = asyncio.get_event_loop()        

        size = await loop.run_in_executor(None, os.path.getsize, str(self.output_path))
        return size / 1024
