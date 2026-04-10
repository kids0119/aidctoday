import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# Curated Korean news RSS feeds for daily AI monitoring.
FEEDS = [
    'https://www.hankyung.com/feed/it',
    'https://rss.donga.com/science.xml',
    'https://feeds.feedburner.com/zdkorea',
    'https://www.newstheai.com/rss/clickTop.xml',
]

AI_KEYWORDS = [
    'AI', '인공지능', '머신러닝', '딥러닝', '챗GPT', '생성형', '생성 AI', '데이터', '로봇', '자율주행', '클라우드', '메타버스', '엣지', '빅데이터'
]

MAX_ARTICLES = int(os.getenv('MAX_ARTICLES', '8'))
DATA_DIR = Path('data')
STATE_FILE = DATA_DIR / 'state.json'
MAX_STORED_LINKS = 2000


def load_state():
    if not STATE_FILE.exists():
        return {
            'last_run': datetime.fromtimestamp(0, tz=timezone.utc),
            'seen_links': set(),
        }

    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    last_run = raw.get('last_run')
    if isinstance(last_run, str):
        try:
            last_run = datetime.fromisoformat(last_run)
        except Exception:
            last_run = datetime.fromtimestamp(0, tz=timezone.utc)
    elif not isinstance(last_run, datetime):
        last_run = datetime.fromtimestamp(0, tz=timezone.utc)

    seen_links = set(raw.get('seen_links', []))
    return {'last_run': last_run, 'seen_links': seen_links}


def save_state(last_run, seen_links):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'last_run': last_run.isoformat(),
            'seen_links': list(seen_links)[-MAX_STORED_LINKS:],
        }, f, ensure_ascii=False, indent=2)


def _local_name(tag):
    return tag.rsplit('}', 1)[-1] if '}' in tag else tag


def _find_child_text(element, names):
    for child in element:
        if _local_name(child.tag) in names and child.text:
            return child.text.strip()
    return ''


def _find_link(element):
    for child in element:
        if _local_name(child.tag) == 'link':
            href = child.get('href')
            if href:
                return href.strip()
            if child.text and child.text.strip():
                return child.text.strip()
    return ''


def _find_feed_title(root):
    if _local_name(root.tag) == 'feed':
        return _find_child_text(root, ['title'])
    for child in root:
        if _local_name(child.tag) == 'channel':
            return _find_child_text(child, ['title'])
    return ''


def _parse_published(date_text):
    if not date_text:
        return datetime.now(timezone.utc)
    try:
        if 'T' in date_text:
            return datetime.fromisoformat(date_text.replace('Z', '+00:00')).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(date_text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _parse_feed(feed_url):
    response = requests.get(feed_url, timeout=15)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    source_name = _find_feed_title(root) or feed_url
    items = []

    for elem in root.iter():
        tag = _local_name(elem.tag)
        if tag not in {'item', 'entry'}:
            continue

        title = _find_child_text(elem, ['title'])
        link = _find_link(elem) or _find_child_text(elem, ['link'])
        summary = _find_child_text(elem, ['summary', 'description', 'content', 'encoded'])
        published = _find_child_text(elem, ['updated', 'published', 'pubDate'])

        if not link:
            continue

        items.append({
            'title': title or 'No title',
            'link': link,
            'source': source_name,
            'summary': summary.strip(),
            'published': _parse_published(published).isoformat(),
        })

    return items


def _is_ai_related(item):
    text = f"{item['title']} {item['summary']}".lower()
    return any(keyword.lower() in text for keyword in AI_KEYWORDS)


def fetch_feeds():
    state = load_state()
    last_run = state['last_run']
    seen_links = state['seen_links']

    news_items = []

    for feed_url in FEEDS:
        try:
            items = _parse_feed(feed_url)
        except Exception as exc:
            print(f'피드 파싱 오류: {feed_url} -> {exc}')
            continue

        for item in items:
            if item['link'] in seen_links:
                continue

            if _parse_published(item['published']) <= last_run:
                continue

            seen_links.add(item['link'])
            news_items.append(item)

    ai_items = [item for item in news_items if _is_ai_related(item)]
    if ai_items:
        news_items = ai_items
    else:
        print('AI 관련 키워드가 포함된 뉴스 기사가 발견되지 않아 전체 기사 중 최신 항목을 사용합니다.')

    news_items.sort(key=lambda item: item['published'], reverse=True)
    return news_items[:MAX_ARTICLES], state


def build_claude_prompt(news_items):
    article_lines = []
    for idx, item in enumerate(news_items, start=1):
        article_lines.append(
            f"{idx}. {item['title']}\n"
            f"   출처: {item['source']}\n"
            f"   링크: {item['link']}\n"
            f"   요약: {item['summary']}\n"
        )

    return (
        '다음은 한국 AI 관련 뉴스 기사입니다. LG유플러스 관점에서 핵심 인사이트, 전략적 시사점, 추천 행동을 한국어로 정리해 주세요. '
        '팀즈 채널에 공유하기에 적합한 간결한 형태로 작성해 주세요.\n\n'
        '기사 목록:\n' + '\n'.join(article_lines) +
        '\n응답은 아래 형식으로 작성하세요:\n'
        '1) 전체 요약\n'
        '2) LG유플러스 관점 시사점\n'
        '3) 추천 액션\n'
        '4) 주의할 점 / 리스크\n'
    )


def analyze_news_items(news_items):
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError('ANTHROPIC_API_KEY 환경 변수가 필요합니다.')

    prompt = build_claude_prompt(news_items)
    payload = {
        'model': 'claude-3.5',
        'prompt': f'Human: {prompt}\n\nAssistant:',
        'max_tokens_to_sample': 1000,
        'temperature': 0.2,
    }
    headers = {'x-api-key': api_key}
    response = requests.post('https://api.anthropic.com/v1/complete', headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()
    completion = result.get('completion') or result.get('text') or ''
    return completion.strip()


def send_to_teams(message):
    webhook_url = os.getenv('TEAMS_WEBHOOK_URL')
    if not webhook_url:
        print('TEAMS_WEBHOOK_URL이 설정되지 않았습니다. Teams 알림 전송을 생략합니다.')
        return

    payload = {'text': message}
    response = requests.post(webhook_url, json=payload, timeout=10)
    response.raise_for_status()
    print('Teams로 알림을 전송했습니다.')


def save_results(news_items, analysis_text):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d')
    file_path = DATA_DIR / f'news_{timestamp}.json'
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump({'generated_at': datetime.now(timezone.utc).isoformat(), 'articles': news_items, 'analysis': analysis_text}, f, ensure_ascii=False, indent=2)
    print(f'뉴스 데이터를 {file_path}에 저장했습니다.')


def main():
    news_items, state = fetch_feeds()
    if not news_items:
        print('수집된 뉴스 항목이 없습니다.')
        return

    analysis_text = None
    try:
        analysis_text = analyze_news_items(news_items)
    except ValueError as exc:
        print(exc)
        print('분석을 건너뛰고 수집된 기사만 저장합니다.')
        analysis_text = 'ANTHROPIC_API_KEY가 설정되지 않아 분석을 수행하지 않았습니다.'

    save_results(news_items, analysis_text)

    latest_time = max(_parse_published(item['published']) for item in news_items)
    save_state(latest_time, state['seen_links'])

    today_str = datetime.now().strftime('%Y-%m-%d')
    teams_message = (
        f'[AI 뉴스 요약] {today_str} KST\n\n'
        f'{analysis_text}\n\n'
        '원문 기사 목록:\n' + '\n'.join([
            f"- {item['title']} ({item['source']})\n  {item['link']}" for item in news_items
        ])
    )
    send_to_teams(teams_message)


if __name__ == '__main__':
    main()
