from typing import List
from PIL import Image, ImageSequence, ImageChops, ImageStat
import os
from waifu2x_ncnn_py import Waifu2x
import cv2
import numpy as np
import asyncio
from pathlib import Path
from elitemikobot.dccon_data import DcconData
from elitemikobot.logger import Logger
from elitemikobot.converter import Converter


class Upscaler():
    MAX_IMG_SIZE_KB = 512     
    IMG_SIZE_X = 512
    IMG_SIZE_Y = 512

    def __init__(self, dccon_data: DcconData, sticker_path: str, merge_nums: List[int]):
        self.logger = Logger(name="Upscaler_Log")
        self.dccon_data = dccon_data
        self.dccon_id = dccon_data.id    
        self.dccon_count = dccon_data.count
        self.dccon_ext = dccon_data.ext
        self.dccon_path = dccon_data.path   
        self.sticker_path = sticker_path   
        self.merge_nums = merge_nums
        self.waifu2x = Waifu2x(gpuid=0, scale=2, noise=3)           

    
    async def upscaler(self) -> bool:        
        try:
            Path(self.sticker_path).mkdir(parents=True, exist_ok=True)

            # merge_nums가 None이면 빈 리스트로 처리
            merge_nums = self.merge_nums if self.merge_nums is not None else []
                       
            i = 1
            while i <= self.dccon_count:                                               
                is_merge = i in merge_nums and i + 1 <= self.dccon_count                                     
                
                nums = [i, i + 1] if is_merge else [i]
                file_paths = []

                for num in nums:                        
                    await self._check_and_rename_image(Path(self.dccon_path) / f"{num}.{self.dccon_ext[num]}", num)
                    file_path = Path(self.dccon_path) / f"{num}.{self.dccon_ext[num]}"
                    file_paths.append(file_path)

                ext = self.dccon_ext[i]
                
                if is_merge:
                    # i + (i + 1) 이미지 병합 
                    process_method = (
                        self._process_img_with_merge if ext == "png" else self._process_gif_with_merge
                    )
                    await process_method(file_paths[0], file_paths[1], i)
                    i += 2
                else:
                    process_method = self._process_img if ext == "png" else self._process_gif
                    await process_method(file_paths[0], i)
                    i += 1                                  
                                                                                                     
            return True
        
        except Exception as e:
            self.logger.error(
                action="Exception Upscaler",
                user=" ",
                data={"dccon_id": self.dccon_id, "status": "except"},
                message=f"{e}"
            ) 
            return False         

    
    # 이미지의 실제 확장자와 파일 확장자가 다른 경우 파일명 변경
    async def _check_and_rename_image(self, file_path: Path, num: int) -> None:        
        loop = asyncio.get_running_loop()                                           
        
        actual_format = await loop.run_in_executor(None, self.get_actual_format, str(file_path))

        if file_path.suffix.lower() != f".{actual_format}":
            new_file_path = file_path.with_suffix(f".{actual_format}")
            await loop.run_in_executor(None, os.rename, str(file_path), str(new_file_path))
            self.dccon_ext[num] = actual_format                                               
    

    @staticmethod
    def get_actual_format( path: str) -> str:
        with Image.open(path) as img:
            fmt = img.format.lower()
        return fmt


    # Waifu2x 모델을 사용해서 업스케일링
    async def _waifu2x_process(self, image: np.ndarray) -> np.ndarray:        
        loop = asyncio.get_running_loop()
        
        # 이미지에 알파채널이 있는 경우
        if len(image.shape) == 3 and image.shape[2] == 4:                     
            alpha_channel = image[:, :, 3]
            
            image = await loop.run_in_executor(None, self.waifu2x.process_cv2, image)                    
            
            # 업스케일링한 이미지 크기와 맞게 알파채널 리사이즈
            resize_alpha_channel = await loop.run_in_executor(
                None, cv2.resize, alpha_channel, (image.shape[1], image.shape[0]), cv2.INTER_LINEAR
            )
            
            image = await loop.run_in_executor(None, cv2.cvtColor, image, cv2.COLOR_BGR2BGRA)
            image[:, :, 3] = resize_alpha_channel  
        else:            
            image = await loop.run_in_executor(None, self.waifu2x.process_cv2, image)
        
        return image


    # 이미지 파일 처리
    async def _process_img(self, file_path: Path, num: int) -> None:        
        image = cv2.imdecode(np.fromfile(str(file_path), dtype=np.uint8), cv2.IMREAD_UNCHANGED)        
        image = await self._waifu2x_process(image)            
        image = cv2.resize(image, (self.IMG_SIZE_X, self.IMG_SIZE_Y))

        out_path = Path(self.sticker_path) / f"{num}.png"
        cv2.imencode(".png", image)[1].tofile(str(out_path))               
        
        await self._compress_img(out_path, num)      
        

    # 이미지 파일 병합 처리
    async def _process_img_with_merge(self, file_path1: Path, file_path2: Path, num: int) -> None:        
        image1 = cv2.imdecode(np.fromfile(str(file_path1), dtype=np.uint8), cv2.IMREAD_UNCHANGED)        
        image2 = cv2.imdecode(np.fromfile(str(file_path2), dtype=np.uint8), cv2.IMREAD_UNCHANGED)        

        image1 = await self._waifu2x_process(image1)            
        image2 = await self._waifu2x_process(image2)      

        image1 = cv2.resize(image1, (self.IMG_SIZE_X // 2, self.IMG_SIZE_Y // 2))
        image2 = cv2.resize(image2, (self.IMG_SIZE_X // 2, self.IMG_SIZE_Y // 2))

        merge_image = await self._merge_images(image1, image2)

        out_path = Path(self.sticker_path) / f"{num}.png"
        cv2.imencode(".png", merge_image)[1].tofile(str(out_path))
        
        await self._compress_img(out_path, num)         


    # 이미지 병합
    async def _merge_images(self, image1: np.ndarray, image2: np.ndarray) -> np.ndarray:               
        pil_image1 = Image.fromarray(image1).convert("RGBA")
        pil_image2 = Image.fromarray(image2).convert("RGBA")
        
        combined = Image.new("RGBA", (512, 256), (0, 0, 0, 0))
        combined.paste(pil_image1, (0, 0))
        combined.paste(pil_image2, (256, 0))
        
        final = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        final.paste(combined, (0, 128), combined)

        return np.array(final)        


    # 이미지 크기 압축
    async def _compress_img(self, img_path: Path, num: int) -> None:    
        quality = 98

        while img_path.stat().st_size / 1024 > self.MAX_IMG_SIZE_KB:                        
            img = Image.open(str(img_path))
            img.save(str(img_path), quality=quality)
            quality -= 2        

    
    # GIF 파일 처리, 프레임별로 분리 → 업스케일링 → webm 생성
    async def _process_gif(self, file_path: Path, num: int) -> None:              
        frame_path = Path(self.sticker_path) / f"{self.dccon_id}_{num}"
        frame_path.mkdir(parents=True, exist_ok=True)
                
        # fallback 여부 판단 (픽셀 비교 기반)
        if await self._needs_independent_rendering(file_path):
            frames, durations = await self._extract_frames_independent(file_path)
        else:
            frames, durations = await self._extract_frames_composited(file_path)

        tasks = []
        sema = asyncio.Semaphore(4)                

        for frame_num, frame in enumerate(frames):
            tasks.append(self._process_gif_frame(frame, frame_num, frame_path, sema))

        await asyncio.gather(*tasks)
        await self._generate_webm(frame_path, num, durations)


    # GIF 프레임 업스케일링
    async def _process_gif_frame(self, frame: Image, frame_num: int, frame_path: Path, sema: asyncio.Semaphore) -> None:        
        async with sema:            
            loop = asyncio.get_running_loop()

            np_array = await self._waifu2x_process(np.array(frame.convert("RGBA")))
            frame_file = frame_path / f"{frame_num:03d}.png"                        
            
            await loop.run_in_executor(None, lambda: Image.fromarray(np_array).save(str(frame_file)))

    # GIF 파일 병합 처리, 프레임별로 분리 → 업스케일링 → webm 생성
    async def _process_gif_with_merge(self, file_path1: Path, file_path2: Path, num: int) -> None:                 
        frame_path = Path(self.sticker_path) / f"{self.dccon_id}_{num}"
        frame_path.mkdir(parents=True, exist_ok=True)                            
                
        if await self._needs_independent_rendering(file_path1):
            frames1, durations1 = await self._extract_frames_independent(file_path1)
        else:
            frames1, durations1 = await self._extract_frames_composited(file_path1)

        if await self._needs_independent_rendering(file_path2):
            frames2, durations2 = await self._extract_frames_independent(file_path2)
        else:
            frames2, durations2 = await self._extract_frames_composited(file_path2)
            
        max_len = min(len(frames1), len(frames2))        
        tasks = []
        sema = asyncio.Semaphore(1)        

        for i in range(max_len):            
            tasks.append(self._merge_and_save_frame(frames1[i], frames2[i], i, frame_path, sema))

        await asyncio.gather(*tasks)        
        
        avg_durations = [(durations1[i] + durations2[i]) / 2 for i in range(max_len)]
        await self._generate_webm(frame_path, num, avg_durations)


    # GIF 프레임 업스케일링 → 병합
    async def _merge_and_save_frame(self, frame1: Image.Image, frame2: Image.Image, frame_num: int, frame_path: Path, sema: asyncio.Semaphore) -> None:
        async with sema:
            loop = asyncio.get_running_loop()

            np1 = await self._waifu2x_process(np.array(frame1).copy())
            np1 = cv2.resize(np1, (256, 256), interpolation=cv2.INTER_LINEAR)

            np2 = await self._waifu2x_process(np.array(frame2).copy())
            np2 = cv2.resize(np2, (256, 256), interpolation=cv2.INTER_LINEAR)

            combined = Image.new("RGBA", (512, 256), (0, 0, 0, 0))
            combined.paste(Image.fromarray(np1), (0, 0))
            combined.paste(Image.fromarray(np2), (256, 0))

            final = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            final.paste(combined, (0, 128), combined)

            out_path = frame_path / f"{frame_num:03d}.png"
            await loop.run_in_executor(None, lambda: final.save(str(out_path)))        


    # composition 방식이 깨지는 GIF인지 판단하여 independent 방식으로 처리할지 여부를 리턴
    async def _needs_independent_rendering(self, file_path: Path, pixel_diff_threshold: float = 0.05, sample_limit: int = 5) -> bool:        
        gif = Image.open(str(file_path))
        original_frames = []
        composited_frames = []

        # 원본 독립 프레임 추출
        for frame in ImageSequence.Iterator(gif):
            original_frames.append(frame.convert("RGBA"))
        check_count = min(sample_limit, len(original_frames))

        # composition 방식 프레임 생성
        gif.seek(0)
        last_frame = gif.convert("RGBA")
        for frame in ImageSequence.Iterator(gif):
            new_frame = Image.new("RGBA", gif.size)
            new_frame.paste(last_frame)
            current = frame.convert("RGBA")
            new_frame.paste(current, (0, 0), current)
            composited_frames.append(new_frame.copy())
            last_frame = new_frame

        # 픽셀 단위 비교
        for i in range(check_count):
            orig = np.array(original_frames[i])
            comp = np.array(composited_frames[i])
            diff = np.abs(orig - comp)
            changed_pixels = np.sum(np.any(diff > 5, axis=-1))
            total_pixels = diff.shape[0] * diff.shape[1]
            ratio = changed_pixels / total_pixels
            
            if ratio > pixel_diff_threshold:
                return True

        return False
    

    async def _extract_frames_independent(self, gif_path: Path) -> tuple[list[Image.Image], list[int]]:
        gif = Image.open(str(gif_path))
        frames = []
        durations = []

        for frame_index in range(gif.n_frames):
            gif.seek(frame_index)
            duration = gif.info.get("duration", 0)
            durations.append(duration)
            frame = gif.copy().convert("RGBA")
            frames.append(frame)

        return frames, durations
    

    async def _extract_frames_composited(self, gif_path: Path) -> tuple[list[Image.Image], list[int]]:
        gif = Image.open(str(gif_path))        
        last_frame = gif.convert("RGBA")

        frames = []
        durations = []

        for frame in ImageSequence.Iterator(gif):
            new_frame = Image.new("RGBA", gif.size)
            
            new_frame.paste(last_frame)
            
            current = frame.convert("RGBA")
            new_frame.paste(current, (0, 0), current)

            frames.append(new_frame.copy())
            durations.append(frame.info.get("duration", 0))

            last_frame = new_frame

        return frames, durations        


    # webm 생성
    async def _generate_webm(self, frame_path: Path, num: int, frame_duration: list) -> None:                                              
        converter = Converter(
            dccon_id=self.dccon_id,
            num=num,
            input_folder=str(frame_path), 
            out_path=str(Path(self.sticker_path) / f"{num}.webm"),
            frame_durations=frame_duration,                
        )
        await converter.convert_video()