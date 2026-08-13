import os
import re
import html
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

# ============================================================
# SEC Daily Rebound & Crash Signal Bot
# 미국 증시 개장 전 브리핑
#
# 구조
# 1. Gemini API 사용 가능 -> Gemini 브리핑
# 2. Gemini 429/quota 오류 -> Google News RSS 자동 fallback
# 3. 어떤 경우에도 Telegram 전송을 최대한 수행
# ============================================================


# ============================================================
# 환경변수
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# 현재 안정적으로 사용할 Gemini 모델
GEMINI_MODEL = "gemini-3.6-flash"


# 한국시간
KST = timezone(timedelta(hours=9))


# ============================================================
# 기본 설정
# ============================================================

TELEGRAM_MAX_LENGTH = 4000

REQUEST_TIMEOUT = 20

NEWS_LIMIT = 12


# ============================================================
# 로그
# ============================================================

def log(message):
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    print(f"[{now}] {message}")


# ============================================================
# Telegram 메시지 전송
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:
        log("ERROR: TELEGRAM_BOT_TOKEN이 없습니다.")
        return False

    if not TELEGRAM_CHAT_ID:
        log("ERROR: TELEGRAM_CHAT_ID가 없습니다.")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    # Telegram은 메시지가 너무 길면 오류가 날 수 있으므로 분할
    chunks = split_message(message, TELEGRAM_MAX_LENGTH)

    success = True

    for chunk in chunks:

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True
        }

        try:

            response = requests.post(
                url,
                json=payload,
                timeout=REQUEST_TIMEOUT
            )

            if response.ok:
                log("Telegram 메시지 전송 성공")
            else:
                success = False
                log(
                    f"Telegram 전송 실패: "
                    f"{response.status_code} "
                    f"{response.text[:500]}"
                )

        except Exception as e:

            success = False
            log(f"Telegram 전송 오류: {e}")

    return success


# ============================================================
# 긴 메시지 안전하게 분할
# ============================================================

def split_message(text, max_length=4000):

    if len(text) <= max_length:
        return [text]

    chunks = []

    current = ""

    # 줄 단위 우선 분할
    lines = text.split("\n")

    for line in lines:

        if len(current) + len(line) + 1 <= max_length:

            current += line + "\n"

        else:

            if current:
                chunks.append(current.strip())

            # 한 줄 자체가 너무 긴 경우
            while len(line) > max_length:

                chunks.append(line[:max_length])

                line = line[max_length:]

            current = line + "\n"

    if current:
        chunks.append(current.strip())

    return chunks


# ============================================================
# Google News RSS
# ============================================================

NEWS_FEEDS = [

    (
        "미국 증시",
        "https://news.google.com/rss/search"
        "?q=미국+증시+S%26P500+나스닥"
        "&hl=ko&gl=KR&ceid=KR:ko"
    ),

    (
        "연준 금리",
        "https://news.google.com/rss/search"
        "?q=미국+연준+금리+FOMC"
        "&hl=ko&gl=KR&ceid=KR:ko"
    ),

    (
        "미국 고용",
        "https://news.google.com/rss/search"
        "?q=미국+고용+고용지표+실업률"
        "&hl=ko&gl=KR&ceid=KR:ko"
    ),

    (
        "미국 물가",
        "https://news.google.com/rss/search"
        "?q=미국+CPI+물가+인플레이션"
        "&hl=ko&gl=KR&ceid=KR:ko"
    ),

    (
        "유가",
        "https://news.google.com/rss/search"
        "?q=국제유가+WTI+브렌트유"
        "&hl=ko&gl=KR&ceid=KR:ko"
    ),

    (
        "빅테크",
        "https://news.google.com/rss/search"
        "?q=미국+빅테크+애플+엔비디아+마이크로소프트+아마존"
        "&hl=ko&gl=KR&ceid=KR:ko"
    )
]


# ============================================================
# RSS 뉴스 가져오기
# ============================================================

def get_news_from_rss():

    all_news = []

    for category, url in NEWS_FEEDS:

        try:

            response = requests.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={
                    "User-Agent":
                    "Mozilla/5.0 "
                    "SEC-Daily-Rebound-Crash-Bot"
                }
            )

            response.raise_for_status()

            root = ET.fromstring(response.content)

            for item in root.findall(".//item"):

                title = item.findtext("title", default="").strip()

                description = item.findtext(
                    "description",
                    default=""
                ).strip()

                pub_date = item.findtext(
                    "pubDate",
                    default=""
                ).strip()

                link = item.findtext(
                    "link",
                    default=""
                ).strip()

                if not title:
                    continue

                # HTML 제거
                clean_description = re.sub(
                    r"<[^>]+>",
                    "",
                    description
                )

                clean_description = html.unescape(
                    clean_description
                )

                all_news.append({
                    "category": category,
                    "title": title,
                    "description": clean_description,
                    "pub_date": pub_date,
                    "link": link
                })

        except Exception as e:

            log(
                f"RSS 수집 실패 "
                f"({category}): {e}"
            )

    # 중복 제거
    unique = []

    seen = set()

    for news in all_news:

        key = re.sub(
            r"\s+",
            " ",
            news["title"]
        ).strip()

        if key in seen:
            continue

        seen.add(key)
        unique.append(news)

    return unique[:NEWS_LIMIT]


# ============================================================
# 뉴스 텍스트 만들기
# ============================================================

def make_news_context(news_list):

    if not news_list:
        return "현재 RSS에서 수집된 뉴스가 없습니다."

    lines = []

    for i, news in enumerate(news_list, start=1):

        title = news["title"]

        description = news["description"]

        if len(description) > 250:
            description = description[:250] + "..."

        lines.append(
            f"{i}. [{news['category']}] {title}\n"
            f"   내용: {description}"
        )

    return "\n\n".join(lines)


# ============================================================
# Gemini API 호출
# ============================================================

def generate_with_gemini(news_context):

    if not GEMINI_API_KEY:

        log("GEMINI_API_KEY 없음 -> RSS fallback")

        return None

    try:

        from google import genai

        log(
            f"Gemini API 요청 시작 "
            f"({GEMINI_MODEL})"
        )

        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        prompt = f"""
당신은 미국 증시 개장 전 시장 브리핑을 작성하는 금융 뉴스 분석가입니다.

아래 최신 뉴스 자료만 참고하여 한국어로 짧고 정확한
미국 증시 개장 전 브리핑을 작성하세요.

중요 규칙:

1. 확인되지 않은 숫자나 사실을 절대 만들지 마세요.
2. 뉴스에 없는 내용을 추측하지 마세요.
3. 숫자가 뉴스에 명확히 나오지 않으면 숫자를 쓰지 마세요.
4. 투자 권유를 하지 마세요.
5. 지나치게 긴 설명을 하지 마세요.
6. 한 문장이 중간에 잘리지 않도록 완결된 문장으로 작성하세요.
7. 전체 길이는 약 700~1200자 이내로 작성하세요.

반드시 다음 형식을 사용하세요.

🚨 [미국 증시 개장 전 브리핑]

📌 오늘의 핵심
- 핵심 뉴스 1
- 핵심 뉴스 2
- 핵심 뉴스 3

📈 미국 증시 영향
- S&P500 / 나스닥에 영향을 줄 수 있는 요인
- 금리 및 연준 관련 요인
- 유가 및 경기 관련 요인

🏦 금리·연준
- 확인된 최신 내용을 짧게 설명

🛢 유가·원자재
- 확인된 최신 내용을 짧게 설명

💼 주요 기업·빅테크
- 중요한 기업 뉴스가 있을 경우 설명

⚠️ 체크포인트
- 오늘 미국 증시에서 확인할 사항

아래는 뉴스 자료입니다.

{news_context}
"""

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        text = getattr(response, "text", None)

        if not text:
            log("Gemini 응답 내용 없음")
            return None

        text = text.strip()

        if len(text) < 100:
            log("Gemini 응답이 너무 짧음")
            return None

        log("Gemini 브리핑 생성 성공")

        return text

    except Exception as e:

        error_text = str(e)

        log(
            f"Gemini API 오류: "
            f"{error_text[:1000]}"
        )

        # 429 quota 오류
        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
            or "quota" in error_text.lower()
            or "rate limit" in error_text.lower()
        ):

            log(
                "Gemini quota/rate limit 감지 -> "
                "RSS fallback으로 전환"
            )

        return None


# ============================================================
# Gemini 실패용 자동 브리핑
# ============================================================

def generate_fallback_briefing(news_list):

    now = datetime.now(KST)

    date_text = now.strftime(
        "%Y-%m-%d %H:%M KST"
    )

    if not news_list:

        return f"""🚨 [미국 증시 개장 전 브리핑]

📅 {date_text}

현재 Gemini API 사용량 제한으로 AI 분석을 이용할 수 없습니다.

또한 현재 뉴스 RSS에서도 확인 가능한 최신 뉴스가 충분하지 않아 시장 방향을 임의로 판단하지 않았습니다.

⚠️ 확인 필요
- 미국 주요 지수
- 연준 및 금리 관련 뉴스
- 고용·물가 지표
- 국제유가
- 주요 빅테크 기업 뉴스

※ 확인되지 않은 시장 정보는 임의로 생성하지 않았습니다.
"""

    # 카테고리별로 최대 2개씩 선택
    grouped = {}

    for news in news_list:

        category = news["category"]

        if category not in grouped:
            grouped[category] = []

        if len(grouped[category]) < 2:
            grouped[category].append(news)

    lines = []

    lines.append(
        "🚨 [미국 증시 개장 전 브리핑]"
    )

    lines.append("")
    lines.append(
        f"📅 {date_text}"
    )

    lines.append("")
    lines.append(
        "⚠️ Gemini API quota 초과로 "
        "AI 분석 대신 최신 뉴스 기반 자동 브리핑을 제공합니다."
    )

    # --------------------------------------------------------
    # 핵심 뉴스
    # --------------------------------------------------------

    lines.append("")
    lines.append("📌 오늘의 핵심 뉴스")

    count = 0

    for news in news_list:

        if count >= 5:
            break

        title = news["title"]

        lines.append(
            f"- {title}"
        )

        count += 1

    # --------------------------------------------------------
    # 카테고리별
    # --------------------------------------------------------

    category_order = [
        "미국 증시",
        "연준 금리",
        "미국 고용",
        "미국 물가",
        "유가",
        "빅테크"
    ]

    for category in category_order:

        items = grouped.get(category, [])

        if not items:
            continue

        lines.append("")
        lines.append(
            f"📍 {category}"
        )

        for news in items:

            title = news["title"]

            # 제목이 지나치게 길면 안전하게 자름
            if len(title) > 180:
                title = title[:180] + "..."

            lines.append(
                f"- {title}"
            )

    # --------------------------------------------------------
    # 체크포인트
    # --------------------------------------------------------

    lines.append("")
    lines.append("⚠️ 오늘의 체크포인트")

    lines.append(
        "- 미국 주요 지수의 선물 흐름"
    )

    lines.append(
        "- 미국 국채금리와 연준 관련 발언"
    )

    lines.append(
        "- 고용 및 물가 관련 지표"
    )

    lines.append(
        "- 국제유가 움직임"
    )

    lines.append(
        "- 엔비디아 등 주요 빅테크 뉴스"
    )

    lines.append("")
    lines.append(
        "※ 본 메시지는 Gemini API 오류 시 사용하는 "
        "뉴스 기반 자동 fallback입니다."
    )

    lines.append(
        "※ 확인되지 않은 수치나 시장 전망은 임의로 생성하지 않았습니다."
    )

    return "\n".join(lines)


# ============================================================
# 메인
# ============================================================

def main():

    log("=" * 60)

    log("SEC Daily Rebound & Crash Signal Bot 시작")

    log("=" * 60)

    # --------------------------------------------------------
    # 1. 뉴스 수집
    # --------------------------------------------------------

    log("최신 뉴스 RSS 수집 시작")

    news_list = get_news_from_rss()

    log(
        f"수집된 뉴스 수: {len(news_list)}"
    )

    news_context = make_news_context(
        news_list
    )

    # --------------------------------------------------------
    # 2. Gemini 시도
    # --------------------------------------------------------

    briefing = generate_with_gemini(
        news_context
    )

    # --------------------------------------------------------
    # 3. Gemini 실패 -> fallback
    # --------------------------------------------------------

    if not briefing:

        log(
            "Gemini 브리핑 생성 실패 -> "
            "뉴스 기반 fallback 사용"
        )

        briefing = generate_fallback_briefing(
            news_list
        )

    # --------------------------------------------------------
    # 4. 마지막 안전장치
    # --------------------------------------------------------

    if not briefing:

        briefing = """🚨 [미국 증시 개장 전 브리핑]

현재 브리핑 생성 과정에서 문제가 발생했습니다.

Gemini API 및 최신 뉴스 데이터를 확인할 수 없어
확인되지 않은 시장 정보를 임의로 생성하지 않았습니다.
"""

    # --------------------------------------------------------
    # 5. Telegram 전송
    # --------------------------------------------------------

    log("Telegram 메시지 전송 시작")

    result = send_telegram(
        briefing
    )

    if result:

        log(
            "브리핑 전송 완료"
        )

    else:

        log(
            "브리핑 전송 실패"
        )

    log("=" * 60)

    log("프로그램 종료")

    log("=" * 60)


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    main()
