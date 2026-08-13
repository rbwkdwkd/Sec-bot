import os
import time
import requests
from datetime import datetime, timezone, timedelta

# ============================================================
# 환경변수
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# ============================================================
# 기본 설정
# ============================================================

KST = timezone(timedelta(hours=9))

# Gemini 모델
# 현재 Google 공식 문서 기준 GA 모델
GEMINI_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
]

# ------------------------------------------------------------
# 분석 대상
#
# 대형주 / 중형주 / 소형주를 섞어서 구성
# ------------------------------------------------------------

STOCKS = [
    # AI / 반도체
    ("NVDA", "NVIDIA", "대형주"),
    ("AMD", "AMD", "대형주"),
    ("INTC", "Intel", "대형주"),
    ("AMAT", "Applied Materials", "대형주"),
    ("LRCX", "Lam Research", "대형주"),
    ("ANET", "Arista Networks", "대형주"),

    # AI 데이터센터 / 성장주
    ("CRWV", "CoreWeave", "중형주"),
    ("NBIS", "Nebius", "중형주"),
    ("IREN", "IREN", "중형주"),
    ("SMCI", "Super Micro Computer", "중형주"),

    # 우주 / 신성장
    ("LUNR", "Intuitive Machines", "소형주"),
    ("ASTS", "AST SpaceMobile", "중형주"),
    ("RKLB", "Rocket Lab", "중형주"),

    # 양자
    ("IONQ", "IonQ", "중형주"),

    # 기타 성장주
    ("TEM", "Tempus AI", "중형주"),
    ("SOUN", "SoundHound AI", "소형주"),
    ("BBAI", "BigBear.ai", "소형주"),
    ("PLTR", "Palantir", "대형주"),
    ("HOOD", "Robinhood", "중형주"),
    ("SOFI", "SoFi", "중형주"),
]


# ============================================================
# Telegram
# ============================================================

def send_telegram_message(message):

    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN 없음")
        return False

    if not TELEGRAM_CHAT_ID:
        print("TELEGRAM_CHAT_ID 없음")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=20
        )

        if response.status_code == 200:
            print("Telegram 전송 성공")
            return True

        print(
            "Telegram 오류:",
            response.status_code,
            response.text[:500]
        )

        return False

    except Exception as e:

        print("Telegram 전송 실패:", e)

        return False


# ============================================================
# Yahoo Finance
#
# API key 없이 사용
# GitHub Actions에서도 사용 가능
# ============================================================

def yahoo_chart(symbol, range_value="1mo", interval="1d"):

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}"
    )

    params = {
        "range": range_value,
        "interval": interval,
        "events": "history"
    }

    headers = {
        "User-Agent":
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/120 Safari/537.36"
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    result = data.get("chart", {}).get("result")

    if not result:
        raise ValueError(
            f"{symbol}: Yahoo 데이터 없음"
        )

    return result[0]


# ============================================================
# 주가 데이터 분석
# ============================================================

def get_stock_data(symbol):

    try:

        data = yahoo_chart(
            symbol,
            "3mo",
            "1d"
        )

        meta = data.get("meta", {})

        timestamps = data.get(
            "timestamp",
            []
        )

        indicators = data.get(
            "indicators",
            {}
        )

        quote = indicators.get(
            "quote",
            [{}]
        )[0]

        closes = quote.get(
            "close",
            []
        )

        volumes = quote.get(
            "volume",
            []
        )

        clean_closes = [
            x for x in closes
            if x is not None
        ]

        clean_volumes = [
            x for x in volumes
            if x is not None
        ]

        if not clean_closes:

            raise ValueError(
                f"{symbol}: 종가 데이터 없음"
            )

        current = clean_closes[-1]

        # ----------------------------------------------------
        # 일간 수익률
        # ----------------------------------------------------

        if len(clean_closes) >= 2:

            previous = clean_closes[-2]

            daily_change = (
                (current - previous)
                / previous
            ) * 100

        else:

            daily_change = 0

        # ----------------------------------------------------
        # 주간 수익률
        # ----------------------------------------------------

        if len(clean_closes) >= 6:

            week_price = clean_closes[-6]

            weekly_change = (
                (current - week_price)
                / week_price
            ) * 100

        else:

            weekly_change = 0

        # ----------------------------------------------------
        # 월간 수익률
        # ----------------------------------------------------

        if len(clean_closes) >= 22:

            month_price = clean_closes[-22]

            monthly_change = (
                (current - month_price)
                / month_price
            ) * 100

        else:

            monthly_change = 0

        # ----------------------------------------------------
        # 거래량 배수
        # 최근 거래량 / 최근 20일 평균
        # ----------------------------------------------------

        if len(clean_volumes) >= 21:

            recent_volume = clean_volumes[-1]

            average_volume = (
                sum(clean_volumes[-21:-1])
                / len(clean_volumes[-21:-1])
            )

            if average_volume > 0:

                volume_ratio = (
                    recent_volume
                    / average_volume
                )

            else:

                volume_ratio = 1

        else:

            volume_ratio = 1

        # ----------------------------------------------------
        # 최근 고점 대비 위치
        # ----------------------------------------------------

        recent_high = max(
            clean_closes[-20:]
        )

        distance_from_high = (
            (current - recent_high)
            / recent_high
        ) * 100

        # ----------------------------------------------------
        # 최근 저점 대비 반등
        # ----------------------------------------------------

        recent_low = min(
            clean_closes[-20:]
        )

        rebound_from_low = (
            (current - recent_low)
            / recent_low
        ) * 100

        # ----------------------------------------------------
        # 시가총액
        # ----------------------------------------------------

        market_cap = meta.get(
            "marketCap"
        )

        return {
            "symbol": symbol,
            "price": current,
            "daily": daily_change,
            "weekly": weekly_change,
            "monthly": monthly_change,
            "volume_ratio": volume_ratio,
            "distance_high": distance_from_high,
            "rebound": rebound_from_low,
            "market_cap": market_cap,
            "currency": meta.get(
                "currency",
                "USD"
            )
        }

    except Exception as e:

        print(
            f"{symbol} 데이터 오류:",
            e
        )

        return None


# ============================================================
# 자동 데이터 점수
#
# AI가 아니라 실제 가격/거래량 기반
# ============================================================

def calculate_score(data):

    score = 0

    daily = data["daily"]
    weekly = data["weekly"]
    volume = data["volume_ratio"]
    rebound = data["rebound"]
    distance_high = data["distance_high"]

    # --------------------------------------------------------
    # 거래량
    # --------------------------------------------------------

    if volume >= 3:
        score += 30

    elif volume >= 2:
        score += 25

    elif volume >= 1.5:
        score += 20

    elif volume >= 1.2:
        score += 15

    elif volume >= 1:
        score += 10

    # --------------------------------------------------------
    # 일간 모멘텀
    # --------------------------------------------------------

    if 3 <= daily <= 15:
        score += 20

    elif 0 < daily < 3:
        score += 12

    elif daily > 15:
        # 이미 너무 급등한 경우
        score += 8

    elif -5 < daily <= 0:
        score += 5

    # --------------------------------------------------------
    # 주간 모멘텀
    # --------------------------------------------------------

    if 5 <= weekly <= 20:
        score += 20

    elif weekly > 20:
        score += 12

    elif 0 < weekly < 5:
        score += 10

    # --------------------------------------------------------
    # 최근 저점 대비 반등
    # --------------------------------------------------------

    if 10 <= rebound <= 40:
        score += 15

    elif 5 <= rebound < 10:
        score += 10

    elif rebound > 40:
        score += 5

    # --------------------------------------------------------
    # 고점과의 거리
    #
    # 고점에서 너무 멀면 반등 후보
    # --------------------------------------------------------

    if -20 <= distance_high <= -5:
        score += 15

    elif -5 < distance_high <= 0:
        score += 8

    # --------------------------------------------------------
    # 점수 제한
    # --------------------------------------------------------

    score = max(
        0,
        min(score, 100)
    )

    return score


# ============================================================
# 상태 판정
# ============================================================

def get_status(data, score):

    daily = data["daily"]
    volume = data["volume_ratio"]

    # 너무 급등한 종목
    if daily >= 20:

        return "⚠️ 과열주의"

    if score >= 80 and volume >= 2:

        return "🔥 강한 관심"

    if score >= 70:

        return "🚀 급등 관심"

    if score >= 60:

        return "🔄 반등 관심"

    if score >= 50:

        return "🔎 관찰"

    return "⏸ 대기"


# ============================================================
# 시장 데이터 수집
#
# 하나가 실패해도 전체 중단하지 않음
# ============================================================

def collect_market_data():

    results = []

    failed = []

    print("시장 데이터 수집 시작")

    for symbol, name, category in STOCKS:

        data = get_stock_data(symbol)

        if data is None:

            failed.append(symbol)

            continue

        data["name"] = name
        data["category"] = category

        data["score"] = calculate_score(
            data
        )

        data["status"] = get_status(
            data,
            data["score"]
        )

        results.append(data)

        print(
            symbol,
            data["price"],
            data["score"]
        )

        # Yahoo 요청 간격
        time.sleep(0.3)

    print(
        f"수집 성공: {len(results)}개"
    )

    print(
        f"수집 실패: {len(failed)}개"
    )

    if failed:

        print(
            "실패 종목:",
            ", ".join(failed)
        )

    return results


# ============================================================
# 종목 선정
#
# 대형/중형/소형주를 어느 정도 균형 있게 포함
# ============================================================

def select_top_stocks(results):

    if not results:

        return []

    # 점수 순으로 정렬
    sorted_results = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )

    selected = []

    large = [
        x for x in sorted_results
        if x["category"] == "대형주"
    ]

    mid = [
        x for x in sorted_results
        if x["category"] == "중형주"
    ]

    small = [
        x for x in sorted_results
        if x["category"] == "소형주"
    ]

    # --------------------------------------------------------
    # 최소한 대형/중형/소형을 섞음
    # --------------------------------------------------------

    for group, limit in [
        (large, 3),
        (mid, 4),
        (small, 2)
    ]:

        for item in group[:limit]:

            if item not in selected:

                selected.append(item)

    # 남은 자리 최고점
    for item in sorted_results:

        if len(selected) >= 10:
            break

        if item not in selected:

            selected.append(item)

    # 최종 점수순
    selected = sorted(
        selected,
        key=lambda x: x["score"],
        reverse=True
    )

    return selected[:10]


# ============================================================
# Gemini 최신 뉴스 분석
# ============================================================

def generate_ai_analysis(stocks):

    if not GEMINI_API_KEY:

        print("Gemini API KEY 없음")

        return None

    stock_text = ""

    for i, stock in enumerate(stocks, 1):

        stock_text += (
            f"{i}. {stock['symbol']} "
            f"({stock['name']})\n"
            f"가격: ${stock['price']:.2f}\n"
            f"일간: {stock['daily']:+.2f}%\n"
            f"주간: {stock['weekly']:+.2f}%\n"
            f"거래량배수: {stock['volume_ratio']:.2f}배\n"
            f"데이터점수: {stock['score']:.1f}\n"
            f"유형: {stock['category']}\n\n"
        )

    prompt = f"""
당신은 미국 주식 시장의 시니어 전략 분석가입니다.

현재 시점의 최신 웹 정보를 반드시 검색해서 확인하세요.

중요:
- 확인되지 않은 뉴스는 절대 만들지 마세요.
- 주가나 거래량을 임의로 만들지 마세요.
- 종목의 성공확률을 근거 없이 숫자로 만들지 마세요.
- 확인 가능한 최신 뉴스와 실제 시장 데이터만 사용하세요.
- 오래된 뉴스를 오늘 뉴스처럼 표현하지 마세요.
- 투자 판단을 단정하지 마세요.

아래는 실제 시장 데이터에서 수집한 후보입니다.

{stock_text}

다음 기준으로 분석하세요.

==================================================
1. 최신 시장 환경
==================================================

S&P500
NASDAQ
Dow Jones
미국 10년물 국채금리
달러
WTI 유가
금리/연준

최근 24시간 이내 중요한 변화가 있는지 확인하세요.

==================================================
2. 종목별 최신 뉴스 검증
==================================================

각 후보에 대해 최신 뉴스가 실제로 존재하는지 확인하세요.

가능하면 다음을 확인하세요.

- 실적
- 가이던스
- 신규 계약
- 정부 계약
- AI 데이터센터
- 반도체
- 우주
- 양자컴퓨팅
- 기관 매수
- 증자
- 전환사채
- 내부자 매도
- 소송
- 규제
- 악재

==================================================
3. 급등 가능성
==================================================

다음 조건을 중요하게 평가하세요.

- 거래량 증가
- 가격 모멘텀
- 최근 조정 후 반등
- 뉴스 촉매
- 시장 테마
- 기관 수급
- 공매도/숏스퀴즈 가능성
- 실적 촉매

==================================================
4. 급락 위험
==================================================

다음을 확인하세요.

- 이미 단기간 과도한 상승
- 실적 악화
- 증자
- 희석
- 부채
- 내부자 매도
- 악재 뉴스
- 밸류에이션 부담
- 시장 금리 상승

==================================================
5. GitHub / 개발활동
==================================================

GitHub가 중요한 기술 기업인 경우에만 확인하세요.

다음 신호를 참고하세요.

- 최근 커밋 증가
- 주요 릴리즈
- 개발자 활동 증가
- 보안 취약점
- 긴급 패치
- 개발자 이탈
- 주요 프로젝트 업데이트

GitHub 자료가 충분하지 않으면
"확인 불충분"이라고 표시하세요.

==================================================
6. Google 검색 관심도
==================================================

가능하면 검색 관심도와 뉴스 노출 증가 여부를 확인하세요.

다만 정확한 Google Trends 수치가 확인되지 않는다면
임의의 숫자를 만들지 마세요.

==================================================
7. 최종 TOP 10
==================================================

각 종목마다 다음 형식으로 작성하세요.

순위
티커
최신 촉매
상승 근거
급락 위험
현재 판단

판단은 다음 중 하나:

🔥 강한 관심
🚀 급등 관심
🔄 반등 관심
🔎 관찰
⚠️ 과열주의
⛔ 위험

==================================================
8. 가장 중요한 3종목
==================================================

오늘 가장 중요한 종목 3개를 선정하고

왜 중요한지 설명하세요.

==================================================
9. 반등 후보
==================================================

이미 많이 오른 종목만 선정하지 말고

"최근 조정 + 거래량 증가 + 실제 촉매"

가 동시에 나타나는 종목을 우선하세요.

==================================================
10. 소형주
==================================================

소형주도 최소 2개 이상 검토하세요.

단,

소형주는 변동성과 실패 위험이 매우 크므로

"급등 가능성"과 함께
"급락 위험"도 반드시 표시하세요.

==================================================

답변은 Telegram에서 읽기 좋게 짧고 명확하게 작성하세요.
"""

    # --------------------------------------------------------
    # Gemini REST API
    #
    # SDK 버전 문제를 줄이기 위해 직접 호출
    # --------------------------------------------------------

    for model in GEMINI_MODELS:

        print(
            f"Gemini 요청: {model}"
        )

        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{model}:generateContent"
        )

        headers = {
            "Content-Type":
                "application/json",
            "x-goog-api-key":
                GEMINI_API_KEY
        }

        payload = {

            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],

            "tools": [
                {
                    "google_search": {}
                }
            ],

            "generationConfig": {
                "maxOutputTokens": 3500
            }
        }

        try:

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=90
            )

            print(
                "Gemini 상태:",
                response.status_code
            )

            # ------------------------------------------------
            # 성공
            # ------------------------------------------------

            if response.status_code == 200:

                data = response.json()

                candidates = data.get(
                    "candidates",
                    []
                )

                if not candidates:

                    continue

                parts = (
                    candidates[0]
                    .get("content", {})
                    .get("parts", [])
                )

                texts = []

                for part in parts:

                    text = part.get("text")

                    if text:

                        texts.append(text)

                if texts:

                    return "\n".join(
                        texts
                    ).strip()

            # ------------------------------------------------
            # 404
            #
            # 다음 모델로 넘어감
            # ------------------------------------------------

            elif response.status_code == 404:

                print(
                    f"{model} 사용 불가."
                )

                continue

            # ------------------------------------------------
            # 429
            #
            # 다른 모델로 무작정 반복 호출하지 않음
            # ------------------------------------------------

            elif response.status_code == 429:

                print(
                    "Gemini quota/rate limit"
                )

                return None

            else:

                print(
                    response.text[:1000]
                )

                continue

        except Exception as e:

            print(
                "Gemini 요청 오류:",
                e
            )

            continue

    return None


# ============================================================
# 데이터 레이더 메시지
# ============================================================

def build_market_message(stocks):

    now = datetime.now(
        KST
    ).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    lines = []

    lines.append(
        "🚨 미국 주식 전략 레이더"
    )

    lines.append("")

    lines.append(
        f"⏰ {now} KST"
    )

    lines.append("")

    lines.append(
        "📊 실제 시장 가격/거래량 기반 자동 레이더"
    )

    lines.append(
        "※ 아래 데이터 점수는 AI가 임의 생성한 값이 아닙니다."
    )

    lines.append(
        "※ Gemini 최신 뉴스 검증은 별도로 표시합니다."
    )

    lines.append("")

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    for i, stock in enumerate(
        stocks,
        1
    ):

        lines.append(
            f"{i}️⃣ {stock['symbol']} "
            f"({stock['name']})"
        )

        lines.append(
            f"현재가: ${stock['price']:.2f}"
        )

        lines.append(
            f"일간: {stock['daily']:+.2f}%"
        )

        lines.append(
            f"주간: {stock['weekly']:+.2f}%"
        )

        lines.append(
            f"거래량: {stock['volume_ratio']:.2f}배"
        )

        lines.append(
            f"데이터 점수: "
            f"{stock['score']:.1f}/100"
        )

        lines.append(
            f"상태: {stock['status']}"
        )

        lines.append(
            f"유형: {stock['category']}"
        )

        lines.append("")

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    return "\n".join(lines)


# ============================================================
# Gemini 결과 추가
# ============================================================

def append_ai_analysis(
    market_message,
    ai_analysis
):

    if ai_analysis:

        return (
            market_message
            + "\n\n"
            + "🤖 Gemini 최신정보 교차검증\n\n"
            + ai_analysis
            + "\n\n"
            + "━━━━━━━━━━━━━━\n"
            + "⚠️ 참고\n"
            + "본 레이더는 투자 판단을 위한 "
              "정보 분석 시스템이며 "
              "수익을 보장하지 않습니다."
        )

    else:

        return (
            market_message
            + "\n\n"
            + "━━━━━━━━━━━━━━\n"
            + "⚠️ Gemini 최신정보 검증 상태\n"
            + "현재 Gemini 최신 뉴스 검증을 "
              "완료하지 못했습니다.\n\n"
            + "따라서 확인되지 않은 뉴스나 "
              "급등확률을 임의로 생성하지 않았습니다.\n\n"
            + "📌 실제 가격/거래량 기반 데이터 "
              "레이더는 정상 작동했습니다."
        )


# ============================================================
# 환경변수 확인
# ============================================================

def check_environment():

    missing = []

    if not TELEGRAM_BOT_TOKEN:

        missing.append(
            "TELEGRAM_BOT_TOKEN"
        )

    if not TELEGRAM_CHAT_ID:

        missing.append(
            "TELEGRAM_CHAT_ID"
        )

    if missing:

        print(
            "필수 Telegram 환경변수 없음:",
            missing
        )

        return False

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "======================================"
    )

    print(
        "미국 주식 전략 레이더 시작"
    )

    print(
        "======================================"
    )

    # --------------------------------------------------------
    # 환경변수
    # --------------------------------------------------------

    if not check_environment():

        return

    # --------------------------------------------------------
    # 시장 데이터 수집
    # --------------------------------------------------------

    stocks = collect_market_data()

    # --------------------------------------------------------
    # 데이터 자체가 하나도 없을 때
    # --------------------------------------------------------

    if not stocks:

        error_message = (
            "🚨 미국 주식 전략 레이더\n\n"
            "시장 데이터를 수집하지 못했습니다.\n\n"
            "Yahoo Finance 데이터 서버 또는 "
            "네트워크 상태를 확인합니다.\n\n"
            "⚠️ 이번 실행에서는 "
            "가짜 주가/거래량/종목을 "
            "생성하지 않았습니다."
        )

        send_telegram_message(
            error_message
        )

        return

    # --------------------------------------------------------
    # TOP 10
    # --------------------------------------------------------

    top10 = select_top_stocks(
        stocks
    )

    # --------------------------------------------------------
    # 시장 데이터 메시지
    # --------------------------------------------------------

    market_message = build_market_message(
        top10
    )

    # --------------------------------------------------------
    # Telegram 먼저 전송
    #
    # Gemini가 죽어도 데이터 레이더는 전달
    # --------------------------------------------------------

    print(
        "시장 데이터 레이더 전송"
    )

    # --------------------------------------------------------
    # Gemini 분석
    # --------------------------------------------------------

    ai_analysis = generate_ai_analysis(
        top10
    )

    # --------------------------------------------------------
    # 최종 메시지
    # --------------------------------------------------------

    final_message = append_ai_analysis(
        market_message,
        ai_analysis
    )

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    send_telegram_message(
        final_message
    )

    print(
        "======================================"
    )

    print(
        "레이더 실행 완료"
    )

    print(
        "======================================"
    )


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":

    main()
