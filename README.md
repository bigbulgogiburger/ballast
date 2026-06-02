# Ballast (W0 스캐폴드)

AI 투자 브리핑 웹서비스. W0 단계는 디렉토리/모듈 스캐폴드만 포함합니다.

## 셋업

```bash
# 1. 가상환경 생성
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경변수 설정 (.env.example 참고)
cp .env.example .env
# .env 편집: 필수 키 입력
```

## 실행

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> 서버는 반드시 127.0.0.1 전용으로만 바인딩하세요. 0.0.0.0 바인딩 금지(외부 노출 방지).

## 테스트

```bash
pytest
```

## 주의

> data/ 디렉토리는 iCloud/Dropbox 등 클라우드 동기화 폴더 밖에 두세요(금융정보 유출 방지).
