from collections import defaultdict
from pathlib import Path
import random
import string
from typing import Dict, List, Optional, Union
import aiohttp
from telegram import Update, Bot, InputSticker, User
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,    
    ConversationHandler,
    MessageHandler,
    filters
)
import shutil
import asyncio
import datetime as dt
from enum import Enum
from dotenv import load_dotenv
import sys
import os

sys.path.append(Path(__file__).resolve().parent.parent.as_posix())
from elitemikobot.db_apiclient import DbApiClient
from elitemikobot.sticker_data import StickerData
from elitemikobot.dccon import Dccon
from elitemikobot.upscaler import Upscaler
from elitemikobot.logger import Logger
from elitemikobot.deleter import Deleter
from elitemikobot.option_flag import OptionFlag
from elitemikobot.dccon_data import DcconData


class BotConfig:    
    BASE_DIR = Path(__file__).resolve().parent.parent
    
    ENV_FILE = Path(os.getenv("ENV_FILE", BASE_DIR / "config.env"))
    IMG_PATH = Path(os.getenv("IMG_PATH", BASE_DIR / "img"))
    STICKER_IMG_PATH = Path(os.getenv("STICKER_IMG_PATH", BASE_DIR / "sticker"))
      
    IMG_PROCESSING_TIMEOUT = 1800   # 30분
    STICKER_PROCESSING_TIMEOUT = 900   # 15분

    @classmethod
    def init(cls):
        cls.load_config()
        cls.init_dir()         

    @classmethod
    def init_dir(cls):        
        for path in [cls.IMG_PATH, cls.STICKER_IMG_PATH]:
            if path.exists():
                shutil.rmtree(path)
            path.mkdir(parents=True, exist_ok=True)          
    
    @classmethod
    def load_config(cls):        
        load_dotenv(cls.ENV_FILE)
        cls.BOT_TOKEN = os.getenv("BOT_TOKEN")
        cls.DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", 0))
        cls.DEVELOPER_NAME = os.getenv("DEVELOPER_NAME", "None")
        cls.GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", 0))
        cls.BASE_URL = os.getenv("BASE_URL")            
        sticker_tag = os.getenv("STICKER_TAG")        
        cls.STICKER_TITLE_TAG = f"@{sticker_tag}"
        cls.STICKER_URL_TAG = f"_by_{sticker_tag}"

    # 스티커 생성 동시 작업 수 제한
    task_semaphore = asyncio.Semaphore(3)
    # 사용자별로 세마포어와 작업중인 디시콘 아이디 관리
    user_semaphore: Dict[int, Dict[str, asyncio.Semaphore | None]] = defaultdict(
        lambda: {'semaphore': asyncio.Semaphore(1), 'request_id': None}
    )
    # 현재 작업중인 목록
    sticker_tasks = {}
    
    # 일일 요청 제한
    MAX_REQUESTS_PER_DAY = 10
    request_counter: dict[int, tuple[dt.date, int]] = defaultdict(lambda: (dt.date.today(), 0))    


class HandlerState(Enum):
    ASK_CONFIRMATION = 0    
    PROCESSING = 1
    WAIT_STICKER = 2
    ASK_MERGE_NUMS = 3


class EliteMikoBot:
    def __init__(self, token) -> None:
        self.logger = Logger(name="EliteMikoBot_Log")              
        self._validate_config()
        self.bot = Bot(token=token)
        self.application = Application.builder().token(token).build()                        
        self._setup_handlers()                                        

    
    def _validate_config(self) -> None:              
        missing_configs = [
            config for config in ["BOT_TOKEN", "DEVELOPER_ID", "DEVELOPER_NAME"]
            if getattr(BotConfig, config) is None
        ]

        if missing_configs:
            print(f"Missing configuration: {missing_configs}")
            exit(1)


    def _setup_handlers(self) -> None:        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('cancel', self._cancel)],
            states={
                HandlerState.ASK_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._confirm_cancel)]                
                },
            fallbacks=[],
            conversation_timeout=15
        )

        conv_handler_remove = ConversationHandler(
            entry_points=[CommandHandler("remove_sticker_set", self._remove_sticker_set)],
            states={
                HandlerState.WAIT_STICKER: [MessageHandler(filters.Sticker.ALL, self._process_remove_sticker)]
            },
            fallbacks=[],
            conversation_timeout=30
        )

        conv_handler_create = ConversationHandler(
            entry_points=[CommandHandler("create", self._create)],
            states={
                HandlerState.ASK_MERGE_NUMS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._receive_merge_nums)
                ]
            },
            fallbacks=[],
            conversation_timeout=60
        )
    
        self.application.add_handler(conv_handler)         
        self.application.add_handler(conv_handler_remove)
        self.application.add_handler(conv_handler_create)
        self.application.add_handler(CommandHandler("start", self._start))
        # self.application.add_handler(CommandHandler("create", self._create))
        self.application.add_handler(CommandHandler("help", self._help))
        self.application.add_handler(CommandHandler("cancel", self._cancel))
        self.application.add_handler(CommandHandler("stop", self._stop))
        self.application.add_handler(CommandHandler("remove_sticker_set", self._remove_sticker_set))                           


    def run(self) -> None:        
        self.logger.info(
            action="start bot",
            user=f"{BotConfig.DEVELOPER_NAME}({BotConfig.DEVELOPER_ID})",
            data=None,
            message="Start EliteMikoBot"
        )
        self.application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


    # 시작
    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:        
        await update.message.reply_text(
            " - Elite Miko Bot -\n\n"            
            "디시콘으로 텔레그램 스티커를 만들어주는 봇입니다.\n"
            "디시콘의 해상도를 인공지능 모델로 2배 높여서 스티커를 생성합니다. \n"
            "디시콘의 해상도, 프레임이 높을수록 스티커 해상도, 프레임이 높아집니다. \n\n"
            " - 움짤이 많을수록 오랜 시간(최대 45분)이 소요됩니다. \n"
            " - 움짤 최대 재생 시간은 3초이며 재생 속도가 조금 달라질 수 있습니다. \n"
            " - 2D 사진 인공지능 모델을 사용하기 때문에 3D 사진은 이상하게 나올 수 있습니다. \n"
            " - 스티커 등록 방법은 /help 를 통해 확인할 수 있습니다. \n\n"
            "⚠️ 저작권자의 요청이 있을 경우 스티커가 삭제될 수 있습니다.\n\n"
            "스티커 목록 - https://t.me/elitemiko_bot_stickers \n"
            "니에.."
        )   


    # 도움말
    async def _help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:       
        await update.message.reply_text(
            "- 스티커 등록 방법 - \n\n"
            "/create [dccon id] 를 통해 스티커를 생성할 수 있습니다. \n"
            " ex) /create 138771 \n\n"
            "디시콘 링크의 # 뒤의 숫자가 dccon id 입니다. \n"
            " ex) dccon.dcinside.com/#138771 \n\n"
            "스티커는 동시에 1개만 요청할 수 있으며, 봇이 동시에 만들 수 있는 스티커 수는 제한되어 있습니다. \n"            
            "/cancel [dccon id] 를 통해 작업중인 스티커를 취소할 수 있습니다. \n\n"
            "등록되어 있는 스티커가 이상할 경우 -o 옵션을 통해 다시 만들 수 있습니다. \n"
            " ex) /create -o 138771 \n\n"
            "작업을 거절당하면 잠시 후에 다시 시도해주세요."
        )

    async def _create(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.message.from_user                            
        
        try:
            if self._is_request_limited(user.id):
                await update.message.reply_text("하루 요청 제한을 초과했다니에...")
                return ConversationHandler.END

            command = self._parse_command(update.message.text)
            if command is None:
                await update.message.reply_text("/create [dccon id] 형태로 입력해줘")
                return ConversationHandler.END
            
            dccon_id, option_flag = command
            sticker_data = StickerData(id=dccon_id, option_flag=option_flag)                
            
            # 이미 존재하는 스티커인지 확인
            exist_url = await self._get_sticker_url(sticker_data)
            has_overwrite = OptionFlag.has_flag(option=OptionFlag.OVERWRITE, flag=option_flag)            
            
            if exist_url is None:
                await update.message.reply_text("작업 중 오류가 발생했다 니에... 오류가 계속되면 관리자에게 문의해줘")
                self.logger.error(
                    action="DB Error _get_sticker_url",
                    user=f"{user.name}({user.id})",
                    data={"dccon_id": sticker_data.id, "status": "Error"},
                    message="Failed to connect to DB"
                )
                return
            elif exist_url is False:
                if has_overwrite:
                    await update.message.reply_text(
                    "등록된 스티커가 없니에...  -o 옵션을 제거하고 다시 요청해줘"                    
                )
                return
            elif exist_url and not has_overwrite:                                     
                await update.message.reply_text(
                    "이미 스티커가 존재한다 니에 \n\n"
                    f"{exist_url}"
                )
                return                        

            # 세마포어 확인
            if not await self._is_request_permitted(update, context, user, sticker_data):
                return
            
            # 작업 요청자 정보
            sticker_data.user_id = user.id
            sticker_data.user_name = f"{user.first_name}({user.name})"            
            context.user_data['sticker_data'] = sticker_data

            if OptionFlag.has_flag(option_flag, OptionFlag.MERGE):
                # -m 옵션이 있으면 추가 번호 입력을 요청
                await update.message.reply_text("합칠 디시콘 번호를 입력해줘 (예: 1 3 5 7)")
                return HandlerState.ASK_MERGE_NUMS
            else:            
                await update.message.reply_text("작업을 시작한다 니에")
                task = asyncio.create_task(
                    self._process_sticker_request(update, context, sticker_data)
                )
                BotConfig.sticker_tasks[sticker_data.id] = task
                return ConversationHandler.END
            
        except asyncio.TimeoutError:
            await update.message.reply_text("작업이 시간 초과로 실패했다 니에...")           
            self.logger.error(
                action="TimeoutError _create",
                user=f"{user.name}({user.id})",
                data={"dccon_id": sticker_data.id, "status": "timeout"},
                message="The task timed out"
            )
        except ValueError as e:
            await update.message.reply_text(f"입력 오류가 발생했다 니에")           

        except aiohttp.ClientError as e:
            await update.message.reply_text("작업 중 오류가 발생했다 니에... 오류가 계속되면 관리자에게 문의해줘")  
            self.logger.error(
                action="aiohttp.ClientError _create",
                user=f"{user.name}({user.id})",
                data={"dccon_id": sticker_data.id, "status": "ClientError"},
                message=f"{e}"
            )
        except Exception as e:
            await update.message.reply_text("작업 중 오류가 발생했다 니에... 오류가 계속되면 관리자에게 문의해줘")                
            self.logger.error(
                action="Exception _create",
                user=f"{user.name}({user.id})",
                data={"dccon_id": sticker_data.id, "status": "Exception"},
                message=f"{e}"
            )


    def _is_request_limited(self, user_id: int) -> bool:
        today = dt.date.today()
        last_date, count = BotConfig.request_counter[user_id]

        if last_date != today:
            BotConfig.request_counter[user_id] = (today, 1)
            return False
        elif count >= BotConfig.MAX_REQUESTS_PER_DAY:            
            return True
        else:
            BotConfig.request_counter[user_id] = (today, count + 1)
            return False


    def _parse_command(self, user_text: str) -> Optional[tuple[int, OptionFlag]]:        
        # ex) /create 138771 or /create -m 138771
        parts = user_text.split()
        if not parts:
            return None
                
        dccon_id = parts[-1].strip()
        if not dccon_id.isdigit():
            return None

        option_flag = OptionFlag(0) 

        if "-o" in parts:
            option_flag = OptionFlag.set_flag(option_flag, OptionFlag.OVERWRITE)
        if "-m" in parts:
            option_flag = OptionFlag.set_flag(option_flag, OptionFlag.MERGE)  
                    
        return int(dccon_id), option_flag
    

    async def _get_sticker_url(self, sticker_data: StickerData) -> Union[str, None, bool]:
        try:
            async with DbApiClient(BotConfig.BASE_URL, sticker_data) as db:
                if await db.check_sticker_exists():
                    return await db.get_sticker_url()
                else:
                    return False
        except Exception as e:            
            return None


    # -m 옵션 활성화 시: 병합할 디시콘 프레임 번호 수동 입력 받음 (개발중)
    async def _receive_merge_nums(self, update: Update, context: ContextTypes.DEFAULT_TYPE):            
        user = update.message.from_user
        if user.id != BotConfig.DEVELOPER_ID or user.name != BotConfig.DEVELOPER_NAME:
            await update.message.reply_text("*개발중인 기능*")
            return ConversationHandler.END
        
        user_input = update.message.text

        try:
            merge_nums = [int(x) for x in user_input.split() if x.isdigit()]            
        except ValueError:
            await update.message.reply_text("입력값이 올바르지 않아. 다시 시도해줘.")
            return HandlerState.END

        sticker_data: StickerData = context.user_data.get('sticker_data')
        if sticker_data is None:
            await update.message.reply_text("오류가 발생했다니에.")
            return ConversationHandler.END
        
        sticker_data.merge_nums = merge_nums

        await update.message.reply_text(f"작업을 시작한다 니에")
        task = asyncio.create_task(
            self._process_sticker_request(update, context, sticker_data)
        )
        BotConfig.sticker_tasks[sticker_data.id] = task
        return ConversationHandler.END
    
                      
    async def _is_request_permitted(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, sticker_data: StickerData) -> bool:    
        if BotConfig.task_semaphore.locked():
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"{user.id}번 디씨콘 작업을 거절당했다 니에... (동시 작업 수 초과)"
            )
            self.logger.info(
                action="request denied",
                user=f"{user.name}({user.id})",
                data={"dccon_id":sticker_data.id, "status":"denied"},
                message="Request denied due to exceeding the concurrent task limit"
            )
            return False
        
        if BotConfig.user_semaphore[user.id]['request_id'] is not None:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"이미 {BotConfig.user_semaphore[user.id]['request_id']}번 디씨콘을 작업중이니에..."
            )
            return False

        if sticker_data.id in BotConfig.sticker_tasks:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"{sticker_data.id}번 디씨콘은 이미 작업중이니에~ 조금만 기다려줘"
            )
            return False

        BotConfig.user_semaphore[user.id]['request_id'] = sticker_data.id
        return True
        

    # 이미지 처리 → 업스케일 → 스티커 세트 생성
    async def _process_sticker_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE, sticker_data: StickerData) -> None:        
        try:            
            user = update.message.from_user
            user_semaphore = BotConfig.user_semaphore[user.id]['semaphore']                                                                        

            # task_semaphore, user_semaphore 세마포어 획득
            async with BotConfig.task_semaphore, user_semaphore:
                # 이미지 처리(timeout 제한)
                img_processing_result = await asyncio.wait_for(
                    self._img_processing(update=update, user=user, sticker_data=sticker_data),
                    timeout=BotConfig.IMG_PROCESSING_TIMEOUT
                )

                # 스티커 처리(timeout 제한)
                if img_processing_result:
                    sticker_processing_result = await asyncio.wait_for(
                    self._sticker_processing(user=user, sticker_data=sticker_data),
                    timeout=BotConfig.STICKER_PROCESSING_TIMEOUT
                )
                else:
                    sticker_processing_result = False

                # 처리 결과 확인                
                if sticker_processing_result:
                    sticker_data.url = f"https://t.me/addstickers/{sticker_data.url}"

                    await self._send_sticker_url(update, context, sticker_data)          

                    self.logger.info(
                        action="Send sticker url",
                        user=f"{user.name}({user.id})",
                        data={"dccon_id":sticker_data.id, "status":"complete"},
                        message="Send sticker url Success"
                    )     
                    
                    # 스티커 DB에 저장
                    async with DbApiClient(BotConfig.BASE_URL, sticker_data) as db:
                        sticker_data.date_time = dt.datetime.now()                        
                        await db.register_sticker()
                else:                    
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id, 
                        text=f"{sticker_data.id}번 디씨콘 작업을 실패했다니에..."
                    )   
                    self.logger.warning(
                        action="Fail send sticker url",
                        user=f"{user.name}({user.id})",
                        data={"dccon_id":sticker_data.id, "status":"fail"},
                        message="_img_processing is fail"
                    )           

        except aiohttp.ClientError as e:
            self.logger.error(
                action="aiohttp.ClientError _process_sticker_request",
                user=f"{user.name}({user.id})",
                data={"dccon_id":sticker_data.id, "status":"aiohttp.ClientError"},
                message=f"{e}"
            ) 
            raise
        except asyncio.TimeoutError as e:
            self.logger.error(
                action="TimeoutError _process_sticker_request",
                user=f"{user.name}({user.id})",
                data={"dccon_id": sticker_data.id, "status": "timeout"},
                message="The task timed out"
            )
            raise
        except FileNotFoundError as e:
            self.logger.error(
                action="Exception _process_sticker_request",
                user=f"{user.name}({user.id})",
                data={"dccon_id":sticker_data.id, "status":"FileNotFoundError"},
                message=f"{e}"
            )
            raise
        except Exception as e:
            self.logger.error(
                action="Exception _process_sticker_request",
                user=f"{user.name}({user.id})",
                data={"dccon_id":sticker_data.id, "status":"except"},
                message=f"{e}"
            )   
            raise
        finally:                        
            await self._cleanup_sticker_task(user_id=user.id, dccon_id=sticker_data.id)
                        

    # 이미지 처리
    async def _img_processing(self, update: Update, user: User, sticker_data: StickerData) -> int:
        try:
            dccon_data = await self._process_dccon(sticker_data)
            if not dccon_data:            
                return False
            
            sticker_data.update_from_dccon_data(dccon_data)

            upscale_result = await self._process_upscaler(dccon_data, sticker_data)
            if not upscale_result:                
                return False

            return True
        
        except Exception as e: 
            self.logger.error(
                action="Exception _img_processing",
                user=f"{user.name}({user.id})",
                data={"dccon_id":sticker_data.id, "status":"except"},
                message=f"{e}"           
            )
            return False
            

    async def _process_dccon(self, sticker_data: StickerData) -> Optional[DcconData]:
        dccon = Dccon()        
        save_path = Path(BotConfig.IMG_PATH) / str(sticker_data.id)
        dccon_data = await dccon.process_dccon(
            dccon_id=sticker_data.id, 
            save_path=str(save_path)
        )

        if dccon_data.err:
            self.logger.warning(
                action="dccon_data fail",
                user=f"{sticker_data.user_name}({sticker_data.user_id})",
                data={"dccon_id":sticker_data.id, "status":"fail"},
                message=f"{dccon_data.err}"
            )
            return None
                
        self.logger.info(
            action="fetch dccon data",
            user=f"{sticker_data.user_name}({sticker_data.user_id})",
            data={"dccon_id":sticker_data.id, "status":"complete"},
            message="Fetch dccon data completed successfully"
        )   
        return dccon_data


    async def _process_upscaler(self, dccon_data: DcconData, sticker_data: StickerData) -> bool:        
        upscaler = Upscaler(
            dccon_data=dccon_data,
            sticker_path=str(Path(BotConfig.STICKER_IMG_PATH) / str(sticker_data.id)),
            merge_nums=sticker_data.merge_nums
        )
        result = await upscaler.upscaler()

        if not result:
            return False

        self.logger.info(
            action="upscaler upscale",
            user=f"{sticker_data.user_name}({sticker_data.user_id})",
            data={"dccon_id": sticker_data.id, "status": "complete"},
            message="Upscaler upscale completed successfully"
        )
        return True
    
    # 스티커 처리
    async def _sticker_processing(self, user: User, sticker_data: StickerData) -> bool:                     
        try:            
            sticker_set, sticker_set2 = await self._prepare_stickers(sticker_data)
            
            await self._generate_unique_sticker_url(sticker_data)            
            
            await self._create_new_sticker_set(sticker_data, sticker_set)
            
            if sticker_set2:
                await self._add_stickers_to_set(sticker_data, sticker_set2)
                         
            return True        
        
        except Exception as e:             
            self.logger.error(
                action="Exception _sticker_processing",
                user=f"{user.name}({user.id})",
                data={"dccon_id":sticker_data.id, "status":"except"},
                message=f"{e}"           
            )
            return False


    async def _prepare_stickers(self, sticker_data: StickerData) -> tuple[List[InputSticker], Optional[List[InputSticker]]]:                      
        path = Path(BotConfig.STICKER_IMG_PATH) / str(sticker_data.id)    
        sticker_set = []
        sticker_set2 = []
        merge_nums = sticker_data.merge_nums if sticker_data.merge_nums is not None else []

        i = 1
        while i <= sticker_data.count:         
            ext = "png" if sticker_data.ext[i] == "png" else "webm"
            fmt = "static" if ext == "png" else "video"   
            file_path = path / f"{i}.{ext}"
            
            sticker = InputSticker(
                    sticker=open(file_path, "rb"),
                    emoji_list=["\U0001F338"],
                    format=fmt
            )            
            # 스티커 세트는 최대 50개까지만 추가 가능하므로, 50개 초과 시 분리해서 저장
            (sticker_set if len(sticker_set) < 50 else sticker_set2).append(sticker)

            i += (2 if i in merge_nums else 1)
            
        return sticker_set, sticker_set2
    
    
    async def _generate_unique_sticker_url(self, sticker_data: StickerData) -> None:        
        async with DbApiClient(BotConfig.BASE_URL, sticker_data) as db:
            for _ in range(10):
                # 텔레그램 스티커 세트 이름은 유니크해야 하므로 랜덤 + dccon_id + suffix 조합으로 생성
                sticker_data.url = (                    
                    f"{''.join(random.sample(string.ascii_lowercase + string.ascii_uppercase, 5))}{sticker_data.id}{BotConfig.STICKER_URL_TAG}"
                )
                
                # URL의 유효성 검사
                if not await db.check_url_exists():
                    return
            else:
                raise RuntimeError("generate_unique_sticker_url fail")


    async def _create_new_sticker_set(self, sticker_data: StickerData, stickers: list) -> None:                  
        try:
            await self.bot.create_new_sticker_set(
                user_id=BotConfig.DEVELOPER_ID,
                name=sticker_data.url,
                title=f"{sticker_data.title} {BotConfig.STICKER_TITLE_TAG}",
                stickers=stickers,
                read_timeout=60,
                write_timeout=60
            )        
        except Exception as e:
            self.logger.error(
                action="Exception _create_new_sticker_set",
                user=" ",
                data={"dccon_id":sticker_data.id, "status":"except"},
                message=f"{e}"
            )             
            raise e


    async def _add_stickers_to_set(self, sticker_data: StickerData, stickers: list):  
        try:      
            for sticker in stickers:
                await self.bot.add_sticker_to_set(
                    user_id=BotConfig.DEVELOPER_ID,
                    name=sticker_data.url,
                    sticker=sticker,
                    read_timeout=60,
                    write_timeout=60
                )        
        except Exception as e:
            self.logger.error(
                action="Exception _add_stickers_to_set",
                user=" ",
                data={"dccon_id":sticker_data.id, "status":"except"},
                message=f"{e}"
            ) 
            raise e
        

    async def _send_sticker_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE, sticker_data: StickerData) -> None:        
        if sticker_data: 
            # 요청한 사용자               
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=sticker_data.url, 
                read_timeout=30, 
                write_timeout=30
            )
            # 그룹 채팅방
            if BotConfig.GROUP_CHAT_ID != 0:
                await context.bot.send_message(
                    chat_id=BotConfig.GROUP_CHAT_ID, 
                    text=(self._generate_group_message(sticker_data)), 
                    read_timeout=30, 
                    write_timeout=30
                )
               

    def _generate_group_message(self, sticker_data: StickerData) -> str:
        message = f"{sticker_data.title}({sticker_data.id})"

        if OptionFlag.has_flag(sticker_data.option_flag, OptionFlag.MERGE):
            message += " -m"
        elif OptionFlag.has_flag(sticker_data.option_flag, OptionFlag.OVERWRITE):
            message += " -o"

        message += f"\n{sticker_data.url}"

        return message


    # 작업 취소
    async def _cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user = update.message.from_user

        try:
            command = self._parse_command(update.message.text)
            user_request_id = BotConfig.user_semaphore[user.id]['request_id']

            if command is None:
                await update.message.reply_text(f"/cancel 번호 형태로 입력해줘")
                return ConversationHandler.END
            
            dccon_id, _ = command
            
            if dccon_id != user_request_id:
                await update.message.reply_text(f"{dccon_id}번 작업이 존재하지 않아")
                return ConversationHandler.END            

            await update.message.reply_text(f"{dccon_id}번 작업을 정말 취소할꺼야? [y/n]")
            return HandlerState.ASK_CONFIRMATION   
                 
        except Exception as e:
            self.logger.error(
                action="Exception _cancel",
                user=f"{user.name}({user.id})",
                data=None,
                message=f"{e}"
            )


    async def _confirm_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:                        
        user_answer = update.message.text.lower()
        if user_answer == 'y':            
            await self._cancel_sticker_request(update, context)
        return ConversationHandler.END


    # 유저가 요청한 작업 취소
    async def _cancel_sticker_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:                
        user = update.message.from_user
        user_request_id = BotConfig.user_semaphore[user.id]['request_id']        
        
        await self._cleanup_sticker_task(user_id=user.id, dccon_id=user_request_id)

        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"{user_request_id}번 디씨콘 작업을 취소했다니에..."
        )
        self.logger.info(
            action="cancel sticker request",
            user=f"{user.name}({user.id})",
            data={"dccon_id":user_request_id, "status":"cancel"},
            message="Cancel sticker request"
        )

    # 작업 종료 및 정리
    async def _cleanup_sticker_task(self, user_id: int, dccon_id: int) -> None:       
        user_semaphore = BotConfig.user_semaphore.get(user_id)

        try:        
            if user_semaphore:
                user_semaphore['request_id'] = None
                if user_semaphore['semaphore'].locked():
                    user_semaphore['semaphore'].release()                

            task = BotConfig.sticker_tasks.pop(dccon_id, None)            
            if task:
                if not task.done():
                    task.cancel()                                        
                    try:
                        await task                        
                    except asyncio.CancelledError:
                        pass
            
            await Deleter.delete_all(
                img_path=Path(BotConfig.IMG_PATH) / str(dccon_id),
                sticker_path=Path(BotConfig.STICKER_IMG_PATH) / str(dccon_id)
            )
        
        except Exception as e:
            self.logger.error(
                action="Exception _cleanup_sticker_task",
                user="EliteMikoBot",
                data=None,
                message=f"{e}"
            )


    # 봇 종료 (개발자 전용)
    async def _stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.message.from_user
        if user.id == BotConfig.DEVELOPER_ID and user.name == BotConfig.DEVELOPER_NAME:            
            for user_id, user_task in BotConfig.user_semaphore.items():
                request_id = user_task['request_id']

                if request_id is not None:
                    await self._cleanup_sticker_task(user_id=user_id, dccon_id=request_id)
                    
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id, 
                        text=f"{user_id} 유저의 {request_id} 작업이 취소 되었습니다."
                    )
                
            await update.message.reply_text("봇을 종료한다 니에")                                  
            self.logger.info(
                action="stop bot",
                user=f"{BotConfig.DEVELOPER_NAME}({BotConfig.DEVELOPER_ID})",
                data=None,
                message="Stop EliteMikoBot"
            )                                 
            asyncio.get_event_loop().stop()                                            


    # 스티커 세트 삭제 (개발자 전용)
    async def _remove_sticker_set(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user = update.message.from_user

        if user.id != BotConfig.DEVELOPER_ID or user.name != BotConfig.DEVELOPER_NAME:
            return ConversationHandler.END

        await update.message.reply_text("제거할 스티커를 보내주세요.")
        return HandlerState.WAIT_STICKER

    async def _process_remove_sticker(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:        
        user = update.message.from_user

        if not update.message.sticker:
            await update.message.reply_text("스티커가 아닙니다.")
            return

        sticker_set_name = update.message.sticker.set_name

        try:
            response = await self.bot.delete_sticker_set(sticker_set_name)

            if response:
                await update.message.reply_text(f"✅ {sticker_set_name} 삭제 성공")
            else:
                await update.message.reply_text(f"⚠️ {sticker_set_name} 삭제 실패")

        except Exception as e:
            await update.message.reply_text(f"오류 발생: {e}")
            self.logger.error(
                action="_remove_sticker",
                user=f"{user.name}({user.id})",
                data={"status": "Exception"},
                message=f"{e}"
            )

        return ConversationHandler.END


# python -m elitemikobot.elitemikobot
if __name__ == "__main__":
    BotConfig.init()
    bot = EliteMikoBot(BotConfig.BOT_TOKEN)
    bot.run()
