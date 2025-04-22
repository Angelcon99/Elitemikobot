# Elitemikobot 🌸

Elitemikobot은 디시콘 번호를 입력 받으면 AI 업스케일링을 거쳐 텔레그램 스티커를 생성해주는 텔레그램 봇입니다. <br/> <br/>
<img src="https://github.com/user-attachments/assets/de81256f-7ba2-4f22-abe9-eb4011e1d1b1" alt="Image" width="300"/>
<br/>

## 주요 기능

- ✅ 텔레그램 봇 명령어를 통한 자동 스티커 생성
- ✅ 디시콘 ID를 통해 디시콘 데이터 수집
- ✅ Waifu2x를 이용한 이미지 업스케일링
- ✅ FFmpeg를 이용해 GIF ➜ WebM 변환
- ✅ DB를 통한 스티커 중복 생성 방지
- ✅ 작업 중복 방지를 위한 사용자 단위 세마포어 처리
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
