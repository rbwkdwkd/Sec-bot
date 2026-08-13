import os
import re
import html
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from google import genai
from google.genai import types


# ============================================================
# 환경변수
# GitHub Secrets
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

# 현재 AI Studio에서 사용 가능한 Flash Lite를 기본값으로 사용
# 필요하면 GitHub Variables에서 GEMINI_MODEL을 따로 설정할 수 있음
MODEL_NAME = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite"
)

MAX_OUTPUT_TOKENS = 2500


# ============================================================
# Google News 검색어
# ============================================================

NEWS_QUERIES = [
    "US stock market S&P 500 Nasdaq Dow Jones",
    "Federal Reserve Fed interest rates inflation CPI jobs",
    "US economic data employment payrolls unemployment",
    "US Treasury yields bond market Fed rate cut",
    "oil crude oil WTI Brent US economy",
    "AI artificial intelligence stocks semiconductor Nvidia AMD",
    "Microsoft Google Amazon Meta Apple AI stocks",
    "Tesla SpaceX technology stocks",
    "US stock market earnings guidance",
    "stock market rebound oversold technology semiconductor"
]


# ============================================================
# 관심 종목 풀
#
# Gemini가 최신 뉴스와 연결해서 분석할 후보군
# ============================================================

STOCK_POOL = {
    "NVDA": "NVIDIA",
    "AMD": "AMD",
    "AVGO": "Broadcom",
    "TSM": "TSMC",
    "MU": "Micron",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "META": "Meta Platforms",
    "AAPL": "Apple",
    "TSLA": "Tesla",
    "AMAT": "Applied Materials",
    "QCOM": "Qualcomm",
    "INTC": "Intel",
    "PLTR": "Palantir",
    "NFLX": "Netflix",
}


# ============================================================
# Telegram 메시지 전송
# ============================================================

def send_telegram_message(message):
    """
    Telegram Bot으로 메시지를 전송합니다.
    Telegram의 메시지 길이 제한을 고려하여 자동 분할합니다.
    """

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

    # Telegram 메시지 최대 길이를 고려
    chunks = split_message(message, 3900)

    success = True

    for chunk in chunks:

        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True
        }

        try:

            response = requests.post(
                url,
                data=data,
                timeout=30
            )

            response.raise_for_status()

            print("Telegram 메시지 전송 성공")

        except requests.exceptions.RequestException as e:

            print(
                f"Telegram 메시지 전송 실패: {e}"
            )

            success = False

    return success


# ============================================================
# 긴 Telegram 메시지 분할
# ============================================================

def split_message(text, max_length=3900):

    if len(text) <= max_length:
        return [text]

    chunks = []
    current = ""

    paragraphs = text.split("\n\n")

    for paragraph in paragraphs:

        candidate = (
            current + "\n\n" + paragraph
            if current
            else paragraph
        )

        if len(candidate) <= max_length:

            current = candidate

        else:

            if current:
                chunks.append(current)

            # 한 문단 자체가 너무 긴 경우
            if len(paragraph) > max_length:

                for i in range(
                    0,
                    len(paragraph),
                    max_length
                ):
                    chunks.append(
                        paragraph[
                            i:i + max_length
                        ]
                    )

                current = ""

            else:

                current = paragraph

    if current:
        chunks.append(current)

    return chunks


# ============================================================
# Google News RSS 검색
# ============================================================

def fetch_google_news(query, max_items=5):

    """
    Google News RSS에서 최신 뉴스 제목을 가져옵니다.

    Gemini의 Google Search 기능을 사용하지 않고
    먼저 뉴스 자체를 수집하여 Gemini에게 전달합니다.
    """

    url = (
        "https://news.google.com/rss/search"
        "?q="
        + requests.utils.quote(query)
        + "&hl=en-US"
        "&gl=US"
        "&ceid=US:en"
    )

    headers = {
        "User-Agent":
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/120 Safari/537.36"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

        root = ET.fromstring(
            response.content
        )

        results = []

        for item in root.findall(".//item")[:max_items]:

            title = item.findtext(
                "title",
                default=""
            ).strip()

            link = item.findtext(
                "link",
                default=""
            ).strip()

            pub_date = item.findtext(
                "pubDate",
                default=""
            ).strip()

            source_node = item.find(
                "source"
            )

            source = ""

            if source_node is not None:
                source = (
                    source_node.text or ""
                ).strip()

            if not title:
                continue

            results.append({
                "title": title,
                "source": source,
                "date": pub_date,
                "link": link
            })

        return results

    except Exception as e:

        print(
            f"Google News 검색 실패: {query}"
        )

        print(str(e))

        return []


# ============================================================
# 전체 최신 뉴스 수집
# ============================================================

def collect_news():

    all_news = []

    seen_titles = set()

    print("========================================")
    print("최신 미국 증시 뉴스 수집 시작")
    print("========================================")

    for query in NEWS_QUERIES:

        print(
            f"뉴스 검색: {query}"
        )

        news_items = fetch_google_news(
            query,
            max_items=5
        )

        for item in news_items:

            title = item["title"]

            # 중복 뉴스 제거
            normalized = re.sub(
                r"\s+",
                " ",
                title.lower()
            )

            if normalized in seen_titles:
                continue

            seen_titles.add(
                normalized
            )

            all_news.append(item)

    print(
        f"총 수집 뉴스: {len(all_news)}개"
    )

    return all_news


# ============================================================
# 뉴스 텍스트 만들기
# ============================================================

def build_news_text(news):

    if not news:

        return (
            "최신 Google News RSS에서 "
            "뉴스를 수집하지 못했습니다."
        )

    lines = []

    for index, item in enumerate(
        news[:45],
        start=1
    ):

        source = (
            item["source"]
            if item["source"]
            else "출처 미상"
        )

        date = item["date"]

        lines.append(
            f"{index}. {item['title']}\n"
            f"   출처: {source}\n"
            f"   시간: {date}"
        )

    return "\n\n".join(lines)


# ============================================================
# 뉴스에서 종목 관련 여부 확인
# ============================================================

def stock_pool_text():

    lines = []

    for ticker, name in STOCK_POOL.items():

        lines.append(
            f"- {ticker}: {name}"
        )

    return "\n".join(lines)


# ============================================================
# Gemini 브리핑 생성
# ============================================================

def generate_market_briefing(news):

    if not GEMINI_API_KEY:

        raise ValueError(
            "GEMINI_API_KEY가 "
            "GitHub Secrets에 없습니다."
        )

    print("Gemini 분석 시작")

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    news_text = build_news_text(
        news
    )

    stocks_text = stock_pool_text()

    # ========================================================
    # 중요
    #
    # Gemini 내부 Google Search를 사용하지 않습니다.
    #
    # 최신 뉴스는 위에서 Google News RSS로 먼저 가져옵니다.
    #
    # 따라서 Gemini API 호출 1회만 수행합니다.
    # ========================================================

    config = types.GenerateContentConfig(

        max_output_tokens=MAX_OUTPUT_TOKENS,

        temperature=0.15
    )

    prompt = f"""
너는 미국 주식시장 개장 전 시장 분석을 담당하는
한국어 금융 뉴스 분석 AI다.

아래에 제공된 최신 뉴스 자료만 근거로 분석하라.

중요한 규칙:

1. 확인되지 않은 사실을 만들지 마라.
2. 뉴스에 없는 숫자나 가격을 임의로 만들지 마라.
3. 오래된 뉴스보다 최신 뉴스의 중요도를 높게 평가하라.
4. 같은 내용의 중복 뉴스는 합쳐라.
5. 시장에 직접 영향을 주는 뉴스와 단순 기업 홍보성 뉴스를 구분하라.
6. 투자자에게 확정적인 수익을 약속하지 마라.
7. 종목 추천이라는 표현보다는
   "반등 관심 후보" 또는 "관심 종목"이라고 표현하라.
8. 종목을 선정할 때 반드시 뉴스의 근거와 연결하라.
9. 단순히 유명한 종목이라는 이유만으로 선정하지 마라.
10. 근거가 부족하면 "자료 부족"이라고 표시하라.

============================================================
오늘의 분석 목적
============================================================

미국 증시 개장 전에 다음 내용을 한 번에 알려주는
실전형 Telegram 브리핑을 만들어라.

특히 이번에는 단순 뉴스 요약이 아니라

"어떤 뉴스가 어떤 업종에 영향을 주고,
그 업종에서 어떤 종목이 반등할 가능성을
관찰할 가치가 있는지"

까지 분석하라.

============================================================
반드시 포함할 내용
============================================================

🚨 [미국 증시 개장 전 브리핑]

📌 1. 오늘의 핵심
- 가장 중요한 뉴스 3개
- 각각 시장에 미치는 영향

📈 2. 미국 증시 영향
- S&P500
- Nasdaq
- Dow Jones
- 상승 요인
- 하락 위험 요인

🏦 3. 금리·연준
- Fed
- 금리 인하/인상 기대
- 국채금리
- CPI/PPI
- 고용
등이 확인되는 경우 설명

🛢 4. 유가·원자재
- WTI
- Brent
- 원유 관련 뉴스
- 인플레이션 영향
- 에너지주 영향

🤖 5. AI·반도체
- AI 관련 뉴스
- 반도체 뉴스
- 데이터센터
- GPU
- 메모리
- 장비주
등을 분석

💼 6. 주요 기업
오늘 시장에 중요한 기업을 골라서
기업명 + 핵심 뉴스 + 증시 영향

============================================================
가장 중요한 부분
============================================================

🔎 7. 관련주 분석

오늘 핵심 뉴스와 직접 연결되는 업종을 찾고

예:

AI 강세
→ GPU
→ 반도체
→ 장비
→ 데이터센터

금리 하락 기대
→ 성장주
→ 기술주
→ 반도체

유가 상승
→ 에너지주
→ 운송주 부담

처럼

"뉴스 → 업종 → 관련 종목"

구조로 분석하라.

가능하면 3~5개 업종을 분석하라.

============================================================
🔥 8. 반등 관심 후보 TOP 5
============================================================

아래 종목 풀에서 오늘 뉴스와 연결성이 높은 종목을
최대 5개 선정하라.

{stocks_text}

각 종목은 다음 형식으로 작성하라.

1️⃣ NVDA NVIDIA
- 관련 뉴스:
- 반등 관심 이유:
- 기대 촉매:
- 확인해야 할 조건:
- 주요 위험:

반드시 "무조건 상승"이라고 표현하지 마라.

반등 가능성을 평가할 때는

① 최근 뉴스의 긍정성
② 업종 모멘텀
③ 금리 환경
④ 실적/가이던스 관련 뉴스
⑤ 시장 심리

등을 종합해서 판단하라.

============================================================
⭐ 9. 오늘 가장 중요한 3개 종목
============================================================

오늘 뉴스 기준으로 가장 주목할 종목 3개를 골라

- 종목
- 이유
- 상승 촉매
- 하락 위험

을 짧게 작성하라.

============================================================
⚠️ 10. 오늘 장 시작 후 체크할 것
============================================================

실제 장 시작 후 투자자가 확인할 포인트를
3~5개 작성하라.

예:

- 미국 10년물 국채금리 방향
- Nasdaq 선물
- 반도체주 강세 지속 여부
- 유가 방향
- 주요 기업 프리마켓 움직임

============================================================
작성 스타일
============================================================

- 한국어
- Telegram에서 보기 쉽게 작성
- 너무 긴 문장은 사용하지 마라
- 핵심 위주
- 이모지를 적절히 사용
- 어려운 경제용어는 간단하게 설명
- 확인되지 않은 정보는 절대 만들어내지 마라
- 뉴스에 근거가 없는 종목은 추천하지 마라
- "반등 예상"은 확정적인 예측이 아니라
  "반등 관심 후보"로 표현하라.

마지막에는 다음 문구를 넣어라.

⚠️ 참고
본 내용은 최신 뉴스와 시장 자료를 바탕으로 한
정보 제공용 분석이며 투자 판단의 최종 책임은
투자자 본인에게 있습니다.

============================================================
최신 뉴스 자료
============================================================

{news_text}
"""

    response = client.models.generate_content(

        model=MODEL_NAME,

        contents=prompt,

        config=config
    )

    text = response.text

    if not text:

        raise ValueError(
            "Gemini가 빈 응답을 반환했습니다."
        )

    print("Gemini 분석 성공")

    return text.strip()


# ============================================================
# Gemini 실패 시 기본 뉴스 브리핑
# ============================================================

def create_fallback_briefing(news, error):

    """
    Gemini가 429 등의 이유로 실패했을 때
    최소한 최신 뉴스 제목을 Telegram으로 보냅니다.

    확인되지 않은 AI 분석이나 종목 추천은 만들지 않습니다.
    """

    lines = []

    lines.append(
        "🚨 [미국 증시 개장 전 브리핑]"
    )

    lines.append("")

    lines.append(
        "⚠️ Gemini AI 분석을 완료하지 못했습니다."
    )

    error_lower = str(error).lower()

    if (
        "429" in error_lower
        or "resource_exhausted" in error_lower
        or "quota" in error_lower
    ):

        lines.append(
            "현재 Gemini API 사용량 제한"
            "(429 RESOURCE_EXHAUSTED)이 "
            "발생했습니다."
        )

    else:

        lines.append(
            "Gemini API 오류가 발생했습니다."
        )

    lines.append("")

    lines.append(
        "📌 확인된 최신 뉴스 제목"
    )

    lines.append("")

    if news:

        for index, item in enumerate(
            news[:15],
            start=1
        ):

            source = (
                item["source"]
                if item["source"]
                else "출처 미상"
            )

            lines.append(
                f"{index}. {item['title']}"
            )

            lines.append(
                f"   └ {source}"
            )

            lines.append("")

    else:

        lines.append(
            "최신 뉴스도 수집하지 못했습니다."
        )

    lines.append(
        "⚠️ AI 분석 없이 확인되지 않은 "
        "종목 추천은 생성하지 않았습니다."
    )

    return "\n".join(lines)


# ============================================================
# 환경변수 검사
# ============================================================

def check_environment():

    missing = []

    if not GEMINI_API_KEY:
        missing.append(
            "GEMINI_API_KEY"
        )

    if not TELEGRAM_BOT_TOKEN:
        missing.append(
            "TELEGRAM_BOT_TOKEN"
        )

    if not TELEGRAM_CHAT_ID:
        missing.append(
            "TELEGRAM_CHAT_ID"
        )

    return missing


# ============================================================
# 메인 프로그램
# ============================================================

def main():

    print("========================================")
    print(
        "미국 증시 개장 전 브리핑 봇 시작"
    )
    print("========================================")

    # --------------------------------------------------------
    # 환경변수 검사
    # --------------------------------------------------------

    missing = check_environment()

    if missing:

        error_message = (
            "🚨 [미국 증시 개장 전 브리핑]\n\n"
            "환경변수가 설정되지 않았습니다.\n\n"
            "누락된 항목:\n"
            + "\n".join(
                f"- {item}"
                for item in missing
            )
        )

        print(error_message)

        # Telegram 설정이 되어 있으면 오류 전송
        send_telegram_message(
            error_message
        )

        return

    # --------------------------------------------------------
    # 최신 뉴스 수집
    # --------------------------------------------------------

    news = collect_news()

    # --------------------------------------------------------
    # Gemini 분석
    # --------------------------------------------------------

    try:

        briefing = generate_market_briefing(
            news
        )

        # ----------------------------------------------------
        # Telegram 전송
        # ----------------------------------------------------

        success = send_telegram_message(
            briefing
        )

        if success:

            print(
                "========================================"
            )

            print(
                "브리핑 전송 완료"
            )

            print(
                "========================================"
            )

        else:

            print(
                "브리핑은 생성됐지만 "
                "Telegram 전송에 실패했습니다."
            )

    except Exception as e:

        print(
            "========================================"
        )

        print(
            "Gemini API 오류"
        )

        print(str(e))

        print(
            "========================================"
        )

        # ----------------------------------------------------
        # Gemini가 실패해도 프로그램 자체는 종료 실패시키지 않음
        # ----------------------------------------------------

        fallback = create_fallback_briefing(
            news,
            e
        )

        send_telegram_message(
            fallback
        )

        print(
            "Gemini 실패 → 기본 뉴스 브리핑 전송 완료"
        )

        # GitHub Actions exit code 1 방지
        return


# ============================================================
# 프로그램 실행
# ============================================================

if __name__ == "__main__":
    main()
