# aidctoday

LG유플러스 관점의 한국 AI 뉴스 자동 수집 및 요약 서비스

## 구성

- `scripts/fetch_news.py` : 한국 AI RSS 피드에서 기사를 수집하고 Claude API로 LG유플러스 관점의 인사이트를 생성합니다.
- `.github/workflows/daily-ai-news.yml` : GitHub Actions에서 매일 오전 7시 KST에 자동 실행하도록 스케줄링합니다.
- `requirements.txt` : 필수 Python 패키지 목록입니다.

## 실행 방법

1. GitHub Secrets에 다음 값을 설정하세요.
   - `ANTHROPIC_API_KEY` : Claude API 키
   - `TEAMS_WEBHOOK_URL` : Teams 채널의 Incoming Webhook URL (선택, 나중에 추가 가능)

2. 로컬에서 테스트 실행:

```bash
python -m pip install -r requirements.txt
python scripts/fetch_news.py
```

3. Teams 알림을 사용하려면 `TEAMS_WEBHOOK_URL`를 설정하면 됩니다.

## 시간

- GitHub Actions는 `0 22 * * *` cron으로 설정되어 있습니다.
- 이는 한국 시간(KST) 기준 매일 오전 7시에 실행됩니다.

## RSS 피드

기본으로 설정된 한국 AI 관련 RSS 피드들:

- aitimes.kr
- venturelab.co.kr
- etnews.com
- donga.com
- hankyung.com
- zdnet.co.kr
- hankookilbo.com
- chosun.com

필요 시 `scripts/fetch_news.py`의 `FEEDS` 목록을 확장할 수 있습니다.
