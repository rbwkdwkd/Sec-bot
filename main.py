import os
import time
import requests
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone


# ============================================================
# 환경변수
#
# GitHub Secrets에서 다음 3개를 설정하세요.
#
# GEMINI_API_KEY
# TELEGRAM_BOT_TOKEN
# TELEGRAM_CHAT_ID
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


# ============================================================
# 기본 설정
# ============================================================

MODEL_NAME = "gemini-3.6-flash"

# Gemini의 일시적인 서버 오류만 재시도
# 429 quota 오류는 재시도하지 않습니다.
MAX_RETRIES = 1

# 뉴스 RSS
NEWS_RSS_URL = "https://news.google.com/rss/search"


# ============================================================
# 공통 HTTP 설정
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/130.0 Safari/537.36"
    )
}


# ============================================================
# Telegram 메시지 전송
# ============================================================

def send_telegram_message(message):
    """Telegram Bot으로 메시지를 전송합니다."""

    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN이 없습니다.")
        return False

    if not TELEGRAM_CHAT_ID:
        print("TELEGRAM_CHAT_ID가 없습니다.")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(
            url,
            data=data,
            timeout=30
        )

        response.raise_for_status()

        print("Telegram 메시지 전송 성공")
        return True

    except requests.exceptions.RequestException as e:
        print(f"Telegram 메시지 전송 실패: {e}")
        return False


# ============================================================
# 오류 종류 확인
# ============================================================

def is_quota_error(error):
    """
    Gemini quota / rate limit 오류인지 확인합니다.

    대표적인 오류:
    - 429
    - RESOURCE_EXHAUSTED
    - quota
    - rate limit
    """

    error_text = str(error).lower()

    keywords = [
        "429",
        "resource_exhausted",
        "too many requests",
        "rate limit",
        "quota",
    ]

    return any(keyword in error_text for keyword in keywords)


def is_temporary_error(error):
    """
    일시적인 서버/네트워크 오류인지 확인합니다.
    """

    error_text = str(error).lower()

    keywords = [
        "503",
        "unavailable",
        "timeout",
        "timed out",
        "temporarily unavailable",
        "internal server error",
        "connection reset",
        "connection aborted",
        "connection error",
    ]

    return any(keyword in error_text for keyword in keywords)


# ============================================================
# Google News RSS 검색
# ============================================================

def get_google_news(query, max_items=5):
    """
    Google News RSS에서 최신 뉴스 헤드라인을 가져옵니다.
    """

    params = {
        "q": query,
        "hl": "ko",
        "gl": "KR",
        "ceid": "KR:ko",
    }

    try:
        response = requests.get(
            NEWS_RSS_URL,
            params=params,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        root = ET.fromstring(response.content)

        news_items = []

        for item in root.findall(".//item")[:max_items]:

            title_element = item.find("title")
            pubdate_element = item.find("pubDate")
            source_element = item.find("source")

            title = (
                title_element.text.strip()
                if title_element is not None
                and title_element.text
                else ""
            )

            pubdate = (
                pubdate_element.text.strip()
                if pubdate_element is not None
                and pubdate_element.text
                else ""
            )

            source = (
                source_element.text.strip()
                if source_element is not None
                and source_element.text
                else ""
            )

            if not title:
                continue

            news_items.append({
                "title": title,
                "source": source,
                "pubdate": pubdate,
            })

        return news_items

    except Exception as e:

        print("----------------------------------------")
        print("Google News RSS 오류")
        print(str(e))
        print("----------------------------------------")

        return []


# ============================================================
# 여러 분야 뉴스 수집
# ============================================================

def collect_market_news():
    """
    미국 증시 관련 최신 뉴스를 여러 분야에서 수집합니다.
    """

    print("최신 미국 증시 뉴스 수집 중...")

    queries = [
        ("미국 증시 S&P 500 Nasdaq Dow Jones", 5),
        ("미국 연준 금리 Fed inflation CPI jobs", 5),
        ("미국 경제지표 고용 물가 금리", 5),
        ("미국 빅테크 Apple Microsoft Nvidia Amazon Google Meta", 5),
        ("미국 주식시장 주요 뉴스", 5),
    ]

    all_news = []

    for query, max_items in queries:

        print(f"뉴스 검색: {query}")

        news = get_google_news(
            query=query,
            max_items=max_items
        )

        all_news.extend(news)

        # 검색 사이에 아주 짧은 간격
        time.sleep(0.5)

    # 제목 중복 제거
    unique_news = []
    seen_titles = set()

    for item in all_news:

        title = item["title"]

        if title in seen_titles:
            continue

        seen_titles.add(title)
        unique_news.append(item)

    print(
        f"뉴스 수집 완료: "
        f"{len(unique_news)}개"
    )

    return unique_news


# ============================================================
# 뉴스 텍스트 만들기
# ============================================================

def make_news_context(news_items, max_items=20):
    """
    Gemini에게 전달할 뉴스 목록을 만듭니다.
    """

    if not news_items:
        return "최신 뉴스 데이터를 가져오지 못했습니다."

    lines = []

    for index, item in enumerate(
        news_items[:max_items],
        start=1
    ):

        title = item.get("title", "")
        source = item.get("source", "")
        pubdate = item.get("pubdate", "")

        line = (
            f"{index}. {title}"
        )

        if source:
            line += f" | 출처: {source}"

        if pubdate:
            line += f" | 시간: {pubdate}"

        lines.append(line)

    return "\n".join(lines)


# ============================================================
# Gemini 브리핑 생성
# ============================================================

def generate_market_briefing(news_items):
    """
    수집한 최신 뉴스만 Gemini에 전달하여
    미국 증시 개장 전 브리핑을 생성합니다.

    중요:
    Gemini의 Google Search Grounding은 사용하지 않습니다.

    따라서 Gemini가 불필요하게 여러 검색 요청을
    추가로 수행하지 않습니다.
    """

    if not GEMINI_API_KEY:

        raise ValueError(
            "GEMINI_API_KEY가 GitHub Secrets에 "
            "설정되어 있지 않습니다."
        )

    print("Gemini API 요청 준비 중...")

    # --------------------------------------------------------
    # Gemini Client
    # --------------------------------------------------------

    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    # --------------------------------------------------------
    # 뉴스 자료
    # --------------------------------------------------------

    news_context = make_news_context(
        news_items,
        max_items=20
    )

    # --------------------------------------------------------
    # 프롬프트
    # --------------------------------------------------------

    prompt = f"""
오늘 미국 증시 개장 전 브리핑을 작성해줘.

아래에 제공된 최신 뉴스 자료만 근거로 사용해줘.

중요:
- 제공된 뉴스에 없는 사실을 만들어내지 말 것
- 확인되지 않은 숫자를 만들어내지 말 것
- 뉴스에 정보가 없으면 "확인된 정보 없음"이라고 표시할 것
- 한국어로 작성할 것
- 짧고 이해하기 쉽게 작성할 것
- 투자 조언이 아니라 시장 정보 브리핑으로 작성할 것
- 같은 내용을 반복하지 말 것

다음 형식으로 작성해줘.

🚨 [미국 증시 개장 전 브리핑]

📊 미국 증시 핵심
- S&P 500:
- Nasdaq:
- Dow Jones:

💰 금리·연준·경제
- 핵심 내용 2~3개

🏢 빅테크·주요 기업
- 핵심 기업 뉴스 2~3개

🔥 오늘의 핵심 뉴스 TOP 3
1.
2.
3.

📈 오늘 미국 증시 체크포인트
- 상승 요인:
- 하락 요인:
- 주의할 점:

마지막에는 다음 문구를 짧게 넣어줘.

※ 본 내용은 최신 뉴스에 기반한 시장 정보 브리핑이며 투자 조언이 아닙니다.

--------------------------------------------------
최신 뉴스 자료
--------------------------------------------------

{news_context}

--------------------------------------------------
끝
--------------------------------------------------
"""

    # --------------------------------------------------------
    # Gemini API 호출
    # --------------------------------------------------------

    for attempt in range(MAX_RETRIES + 1):

        try:

            print(
                "Gemini API 요청 중... "
                f"(시도 {attempt + 1}/{MAX_RETRIES + 1})"
            )

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=1000
                )
            )

            text = response.text

            if not text:

                raise ValueError(
                    "Gemini가 빈 응답을 반환했습니다."
                )

            print("Gemini API 요청 성공")

            return text.strip()

        except Exception as e:

            print("----------------------------------------")
            print("Gemini API 오류 발생")
            print(str(e))
            print("----------------------------------------")

            # ------------------------------------------------
            # 429 quota 오류
            #
            # 중요:
            # 429는 반복 요청하지 않습니다.
            # ------------------------------------------------

            if is_quota_error(e):

                print(
                    "Gemini quota 오류입니다."
                )

                raise

            # ------------------------------------------------
            # 일시적인 서버 오류
            # ------------------------------------------------

            if is_temporary_error(e):

                if attempt < MAX_RETRIES:

                    print(
                        "일시적인 오류입니다."
                    )

                    print(
                        "20초 후 한 번만 재시도합니다."
                    )

                    time.sleep(20)

                    continue

            # ------------------------------------------------
            # 그 외 오류
            # ------------------------------------------------

            raise

    raise RuntimeError(
        "Gemini API 호출에 실패했습니다."
    )


# ============================================================
# Gemini 실패 시 사용할 뉴스 기반 브리핑
# ============================================================

def make_fallback_briefing(news_items):
    """
    Gemini API가 quota 초과 등의 이유로 실패했을 때
    수집된 뉴스 헤드라인만 이용해서 Telegram으로
    보낼 수 있는 간단한 브리핑을 만듭니다.
    """

    message = (
        "🚨 [미국 증시 개장 전 브리핑]\n\n"
        "⚠️ Gemini API를 현재 사용할 수 없어 "
        "뉴스 헤드라인 기반으로 전달합니다.\n\n"
        "🔥 최신 주요 뉴스\n"
    )

    if not news_items:

        message += (
            "\n현재 뉴스 데이터를 가져오지 못했습니다."
        )

        return message

    for index, item in enumerate(
        news_items[:10],
        start=1
    ):

        title = item.get(
            "title",
            "제목 없음"
        )

        source = item.get(
            "source",
            ""
        )

        message += f"\n{index}. {title}"

        if source:
            message += f"\n   └ {source}"

    message += (
        "\n\n"
        "⚠️ Gemini API quota가 회복되면 "
        "AI 요약 브리핑이 정상적으로 제공됩니다.\n\n"
        "※ 본 내용은 뉴스 헤드라인 기반의 "
        "정보 제공용이며 투자 조언이 아닙니다."
    )

    return message


# ============================================================
# Gemini quota 오류 메시지
# ============================================================

def make_quota_error_message():

    return (
        "🚨 [미국 증시 개장 전 브리핑]\n\n"
        "⚠️ Gemini API 사용량 제한에 도달했습니다.\n\n"
        "현재 Gemini API가 "
        "429 RESOURCE_EXHAUSTED를 반환했습니다.\n\n"
        "이번 실행에서는 불필요한 재시도를 하지 않고 "
        "뉴스 헤드라인 기반 브리핑으로 대체합니다.\n\n"
        "확인할 사항:\n"
        "1. Gemini API 사용량\n"
        "2. RPM / TPM / RPD quota\n"
        "3. Google AI Studio 사용량\n"
        "4. 프로젝트의 결제 및 요금제 상태\n\n"
        "※ 같은 프로젝트의 API 키를 여러 개 만들어도 "
        "quota가 공유될 수 있습니다."
    )


# ============================================================
# 환경변수 오류 메시지
# ============================================================

def make_missing_env_message(missing):

    return (
        "🚨 [미국 증시 개장 전 브리핑]\n\n"
        "환경변수가 설정되지 않았습니다.\n\n"
        "누락된 항목:\n"
        + "\n".join(
            f"- {item}"
            for item in missing
        )
    )


# ============================================================
# 메인 프로그램
# ============================================================

def main():

    print("========================================")
    print("미국 증시 개장 전 브리핑 봇 시작")
    print("========================================")

    # --------------------------------------------------------
    # 환경변수 확인
    # --------------------------------------------------------

    missing = []

    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:

        error_message = make_missing_env_message(
            missing
        )

        print(error_message)

        # Telegram 설정이 있는 경우 오류 전송
        send_telegram_message(
            error_message
        )

        # GitHub Actions 실패 방지
        return

    # --------------------------------------------------------
    # 1단계
    # 최신 뉴스 수집
    # --------------------------------------------------------

    print("----------------------------------------")
    print("1단계: 최신 뉴스 수집")
    print("----------------------------------------")

    news_items = collect_market_news()

    # --------------------------------------------------------
    # 뉴스가 하나도 없는 경우
    # --------------------------------------------------------

    if not news_items:

        print(
            "뉴스 데이터를 가져오지 못했습니다."
        )

        fallback_message = (
            "🚨 [미국 증시 개장 전 브리핑]\n\n"
            "현재 최신 뉴스 데이터를 가져오지 "
            "못했습니다.\n\n"
            "잠시 후 다시 실행해주세요."
        )

        send_telegram_message(
            fallback_message
        )

        return

    # --------------------------------------------------------
    # 2단계
    # Gemini 요약
    # --------------------------------------------------------

    print("----------------------------------------")
    print("2단계: Gemini AI 브리핑 생성")
    print("----------------------------------------")

    try:

        briefing = generate_market_briefing(
            news_items
        )

    except Exception as e:

        error_text = str(e)

        print("----------------------------------------")
        print("Gemini 최종 실패")
        print(error_text)
        print("----------------------------------------")

        # ----------------------------------------------------
        # 429 quota 오류
        # ----------------------------------------------------

        if is_quota_error(e):

            print(
                "Gemini quota 초과입니다."
            )

            # Gemini quota가 막혀도
            # 뉴스 기반 브리핑을 Telegram에 보냅니다.

            fallback_message = (
                make_fallback_briefing(
                    news_items
                )
            )

            send_telegram_message(
                fallback_message
            )

            print(
                "Gemini quota 오류 → "
                "뉴스 기반 브리핑 전송 완료"
            )

            # GitHub Actions 정상 종료
            return

        # ----------------------------------------------------
        # 그 외 Gemini 오류
        # ----------------------------------------------------

        telegram_message = (
            "🚨 [미국 증시 개장 전 브리핑]\n\n"
            "Gemini API 요청 중 오류가 발생했습니다.\n\n"
            f"오류 내용:\n{error_text}\n\n"
            "Gemini 대신 최신 뉴스 헤드라인을 "
            "전달합니다."
        )

        # 오류 내용을 먼저 알림
        send_telegram_message(
            telegram_message
        )

        # 뉴스 기반 브리핑 추가 전송
        fallback_message = make_fallback_briefing(
            news_items
        )

        send_telegram_message(
            fallback_message
        )

        print(
            "Gemini 오류 → "
            "뉴스 기반 브리핑 전송 완료"
        )

        # GitHub Actions 실패 방지
        return

    # --------------------------------------------------------
    # 3단계
    # Telegram 전송
    # --------------------------------------------------------

    print("----------------------------------------")
    print("3단계: Telegram 전송")
    print("----------------------------------------")

    success = send_telegram_message(
        briefing
    )

    if success:

        print("========================================")
        print("브리핑 전송 완료")
        print("========================================")

    else:

        print(
            "Gemini 브리핑 생성은 성공했지만 "
            "Telegram 전송에 실패했습니다."
        )

    # --------------------------------------------------------
    # 프로그램 정상 종료
    # --------------------------------------------------------

    print(
        "GitHub Actions 작업을 정상 종료합니다."
    )


# ============================================================
# 프로그램 실행
# ============================================================

if __name__ == "__main__":
    main()
