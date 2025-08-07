# Elitemikobot 🌸

디시콘 번호를 입력하면 AI 업스케일링을 거쳐 텔레그램 스티커를 자동 생성하는 Telegram Bot <br/> <br/>
<img src="https://github.com/user-attachments/assets/de81256f-7ba2-4f22-abe9-eb4011e1d1b1" alt="Image" width="300"/>
<br/>

## 주요 기능

- ✅ 텔레그램 봇 명령어를 통한 자동 스티커 생성
- ✅ 사용자가 요청한 디시 데이터 수집
- ✅ Waifu2x를 이용한 이미지 업스케일링
- ✅ FFmpeg를 이용해 GIF ➜ WebM 변환
- ✅ 중복 요청 방지, 사용량 제한 등 안전성 높 구조
- ✅ FastAPI 기반 API 서버를 통해 스티커 DB 관리
<br/>

## 🚀 프로젝트 실행 방법

### 1. 의존 환경

- Python 3.10+
- FFmpeg (환경 변수 등록 필요)
- API 서버 (스티커 정보 조회/등록 등에 사용되며, 별도 프로세스로 실행되어야 함)

### 2. 의존성 설치

```
pip install -r requirements.txt
```

### 3. 텔레그램 봇 설정

`elitemikobot/` 경로에 `.env` 파일을 생성하고 다음 값이 필요합니다.

```env
BOT_TOKEN=텔레그램_봇_토큰
DEVELOPER_ID=본인_텔레그램_ID
DEVELOPER_NAME=본인_이름
GROUP_CHAT_ID=스티커 공유할 그룹 ID
BASE_URL=http://localhost:1135/api  # API 서버 주소
```

### 4. 봇 실행

```
python -m elitemikobot.elitemikobot
```

### 🔗 API 서버
Elitemikobot은 별도의 API 서버와 통신하여 동작합니다.<br/>
스티커 데이터의 조회, 등록, 중복 확인 등은 모두 해당 서버를 통해 이루어지며, 봇과는 별개의 프로세스로 실행되어야 합니다.<br/>
<br/>
현재 FastAPI 기반의 예시 API 서버는 아래 저장소를 참고해주세요.<br/>
👉 [Elitemikobot-FastAPI](https://github.com/Angelcon99/Elitemikobot-FastAPI)<br/>
> API 서버는 .env에 등록한 BASE_URL 주소를 통해 연결됩니다.
