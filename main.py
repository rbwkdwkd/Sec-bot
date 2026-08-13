import os
import time
import json
import requests
from datetime import datetime, timezone, timedelta

# =========================================================
# 환경변수
# =========================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# Gemini 모델은 GitHub Secrets에서 변경 가능
# 예:
# GEMINI_MODEL = gemini-2.5-flash
# GEMINI_MODEL = gemini-3-flash-preview
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
).strip()

# =========================================================
# 기본 설정
# =========================================================

KST = timezone(timedelta(hours=9))

REQUEST_TIMEOUT = 20

# Gemini 재시도
MAX_GEMINI_RETRIES = 3

# 주식 후보
TOP_N = 10


# =========================================================
# 시간
# =========================================================

def now_kst():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")


# =========================================================
# 숫자 처리
# =========================================================

def safe_float(value, default=0.0):
    try:
        return float(value)
    except:
        return default


# =========================================================
# Yahoo Finance 데이터
# =========================================================

def get_yahoo_quote(symbol):

    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + symbol
        + "?range=5d&interval=1d"
    )

    try:

        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        if response.status_code != 200:
            return None

        data = response.json()

        result = data.get("chart", {}).get("result")

        if not result:
            return None

        result = result[0]

        meta = result.get("meta", {})

        price = safe_float(
            meta.get("regularMarketPrice")
        )

        previous = safe_float(
            meta.get("previousClose")
        )

        if price <= 0:
            return None

        change = 0

        if previous > 0:
            change = ((price - previous) / previous) * 100

        indicators = result.get(
            "indicators",
            {}
        )

        quote = indicators.get(
            "quote",
            [{}]
        )[0]

        volumes = quote.get("volume", [])

        volumes = [
            v for v in volumes
            if isinstance(v, (int, float))
        ]

        current_volume = (
            volumes[-1]
            if volumes
            else 0
        )

        avg_volume = (
            sum(volumes[:-1]) /
            len(volumes[:-1])
            if len(volumes) > 1
            else current_volume
        )

        volume_ratio = (
            current_volume / avg_volume
            if avg_volume > 0
            else 1
        )

        return {
            "symbol": symbol,
            "price": price,
            "change": change,
            "volume_ratio": volume_ratio
        }

    except Exception as e:

        print(
            f"[Yahoo 오류] {symbol}: {e}"
        )

        return None


# =========================================================
# 후보 종목
#
# 대형주만 나오지 않도록
# 대형 / 중형 / 소형 / 성장주를 혼합
# =========================================================

WATCHLIST = [

    # AI / 반도체
    "NVDA",
    "AMD",
    "AVGO",
    "INTC",
    "MU",
    "LRCX",
    "AMAT",
    "ASML",
    "ANET",

    # AI 데이터센터
    "CRWV",
    "NBIS",
    "IREN",
    "SMCI",
    "VRT",

    # 우주
    "LUNR",
    "RKLB",

    # 성장주
    "TEM",
    "SOUN",
    "PLTR",
    "PATH",

    # 전기차 / 로봇
    "TSLA",
    "RIVN",
    "ACHR",
    "JOBY",

    # 바이오 / 헬스케어
    "RXRX",
    "CRSP",
    "DNA",

    # 핀테크 / 결제
    "SOFI",
    "NU",

    # 기타 고변동 성장주
    "HOOD",
    "MARA",
    "CLSK",
    "RIOT"
]


# =========================================================
# 데이터 기반 점수
# =========================================================

def calculate_score(data):

    if not data:
        return 0

    score = 50.0

    change = data["change"]
    volume_ratio = data["volume_ratio"]

    # 상승 모멘텀
    if change >= 20:
        score += 25

    elif change >= 10:
        score += 18

    elif change >= 5:
        score += 10

    elif change >= 2:
        score += 5

    # 거래량
    if volume_ratio >= 3:
        score += 20

    elif volume_ratio >= 2:
        score += 15

    elif volume_ratio >= 1.5:
        score += 10

    elif volume_ratio >= 1.2:
        score += 5

    # 지나친 급등은 위험점수 차감
    if change >= 30:
        score -= 10

    if change >= 50:
        score -= 15

    # 지나친 거래량도 과열 가능성
    if volume_ratio >= 5:
        score -= 5

    return max(
        0,
        min(100, score)
    )


# =========================================================
# 전체 후보 분석
# =========================================================

def collect_candidates():

    print("📊 시장 데이터 수집 시작")

    results = []

    for symbol in WATCHLIST:

        data = get_yahoo_quote(symbol)

        if not data:
            continue

        data["score"] = calculate_score(data)

        results.append(data)

        print(
            f"{symbol}: "
            f"${data['price']:.2f} "
            f"{data['change']:+.2f}% "
            f"거래량 {data['volume_ratio']:.1f}배 "
            f"점수 {data['score']:.1f}"
        )

        # API에 과도한 요청 방지
        time.sleep(0.15)

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return results[:TOP_N]


# =========================================================
# Gemini API
# =========================================================

def ask_gemini(candidates):

    if not GEMINI_API_KEY:

        return {
            "success": False,
            "error": "GEMINI_API_KEY가 없습니다."
        }

    if not candidates:

        return {
            "success": False,
            "error": "분석할 종목이 없습니다."
        }

    stocks_text = ""

    for i, stock in enumerate(
        candidates,
        start=1
    ):

        stocks_text += (
            f"{i}. {stock['symbol']} | "
            f"현재가 ${stock['price']:.2f} | "
            f"일간 {stock['change']:+.2f}% | "
            f"거래량 {stock['volume_ratio']:.1f}배 | "
            f"데이터점수 {stock['score']:.1f}/100\n"
        )

    prompt = f"""
당신은 미국 주식 시장의 시니어 전략 분석가입니다.

현재 시각:
{now_kst()}

아래는 자동 수집된 실제 시장 데이터입니다.

{stocks_text}

중요한 분석 원칙:

1. 제공된 가격과 거래량을 임의로 수정하지 마세요.
2. 확인되지 않은 뉴스나 실적을 사실처럼 만들지 마세요.
3. 최신 뉴스가 확인되지 않는 경우 반드시
   "최신 뉴스 검증 필요"라고 표시하세요.
4. 급등 가능성을 확정적으로 표현하지 마세요.
5. 투자 성공을 보장하는 표현을 사용하지 마세요.
6. 데이터가 부족하면 "판단 보류"라고 하세요.
7. 대형주만 고르지 말고 소형/중형/대형주를 균형 있게 평가하세요.
8. 단순히 많이 오른 종목을 추천하지 말고
   거래량, 모멘텀, 과열 여부, 반등 가능성을 함께 평가하세요.

다음 형식으로 작성하세요.

[미국 주식 전략 레이더]

1. 오늘의 시장 핵심 3개

2. TOP 10

각 종목:

순위:
티커:
종목명:
현재가:
데이터 점수:
AI 검증 점수:
상승 시나리오:
반등 가능성:
급락 위험:
주요 촉매:
주요 위험:
매수 후보 조건:
관찰 포인트:

3. 오늘의 최우선 관심종목 TOP 3

4. 소형/중형 성장주 중 주목할 종목

5. 급등 추격을 피해야 할 종목

6. 전체 시장 위험도

7. 최종 의견

중요:
AI 검증 점수와 확률은 실제 확인 가능한 자료가 있을 때만 제시하세요.
확인할 수 없는 경우 N/A라고 표시하세요.
"""

    # =====================================================
    # Gemini REST API
    # =====================================================

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
        f"?key={GEMINI_API_KEY}"
    )

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
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 5000
        }
    }

    for attempt in range(
        1,
        MAX_GEMINI_RETRIES + 1
    ):

        try:

            print(
                f"🤖 Gemini 요청 "
                f"{attempt}/{MAX_GEMINI_RETRIES}"
            )

            response = requests.post(
                url,
                json=payload,
                headers={
                    "Content-Type":
                    "application/json"
                },
                timeout=45
            )

            try:
                data = response.json()
            except:
                data = {}

            if response.status_code == 200:

                candidates_response = (
                    data.get("candidates", [])
                )

                if candidates_response:

                    parts = (
                        candidates_response[0]
                        .get("content", {})
                        .get("parts", [])
                    )

                    if parts:

                        text = parts[0].get(
                            "text",
                            ""
                        ).strip()

                        if text:

                            return {
                                "success": True,
                                "text": text
                            }

            # ---------------------------------------------
            # 429
            # ---------------------------------------------

            if response.status_code == 429:

                print(
                    "⚠️ Gemini 429 "
                    "RESOURCE_EXHAUSTED"
                )

                if attempt < MAX_GEMINI_RETRIES:

                    wait_time = (
                        10 * attempt
                    )

                    print(
                        f"{wait_time}초 후 재시도"
                    )

                    time.sleep(
                        wait_time
                    )

                    continue

                return {
                    "success": False,
                    "error":
                    "Gemini API 사용량 제한(429)"
                }

            # ---------------------------------------------
            # 404
            # ---------------------------------------------

            if response.status_code == 404:

                message = (
                    data.get("error", {})
                    .get(
                        "message",
                        "모델을 찾을 수 없습니다."
                    )
                )

                return {
                    "success": False,
                    "error":
                    f"Gemini 모델 오류(404): {message}"
                }

            # ---------------------------------------------
            # 기타 오류
            # ---------------------------------------------

            message = (
                data.get("error", {})
                .get(
                    "message",
                    f"HTTP {response.status_code}"
                )
            )

            print(
                f"Gemini 오류: {message}"
            )

            if attempt < MAX_GEMINI_RETRIES:

                time.sleep(5)

                continue

            return {
                "success": False,
                "error":
                f"Gemini API 오류: {message}"
            }

        except Exception as e:

            print(
                f"Gemini 요청 예외: {e}"
            )

            if attempt < MAX_GEMINI_RETRIES:

                time.sleep(5)

                continue

            return {
                "success": False,
                "error":
                f"Gemini 요청 오류: {e}"
            }

    return {
        "success": False,
        "error": "Gemini 분석 실패"
    }


# =========================================================
# Gemini 실패 시에도 보내는 데이터 분석
# =========================================================

def make_fallback_report(candidates):

    if not candidates:

        return """
⚠️ 시장 데이터를 가져오지 못했습니다.

이번 실행에서는
확인되지 않은 종목을 추천하지 않습니다.
"""

    text = ""

    text += (
        "⚠️ Gemini AI 검증은 현재 사용할 수 없습니다.\n\n"
    )

    text += (
        "아래 내용은 실제 수집된 가격/거래량을 "
        "기반으로 한 자동 데이터 점수입니다.\n"
    )

    text += (
        "※ AI 검증 완료 추천이 아닙니다.\n\n"
    )

    for i, stock in enumerate(
        candidates,
        start=1
    ):

        symbol = stock["symbol"]
        price = stock["price"]
        change = stock["change"]
        volume = stock["volume_ratio"]
        score = stock["score"]

        if change >= 20:
            status = "🔥 강한 상승 모멘텀 / 추격주의"

        elif change >= 10:
            status = "📈 상승 모멘텀"

        elif change >= 5:
            status = "👀 관심"

        elif change < -5:
            status = "⚠️ 약세"

        else:
            status = "🔎 관찰"

        text += (
            f"{i}️⃣ {symbol}\n"
            f"현재가: ${price:.2f}\n"
            f"일간: {change:+.2f}%\n"
            f"거래량: {volume:.1f}배\n"
            f"데이터 점수: {score:.1f}/100\n"
            f"상태: {status}\n\n"
        )

    text += (
        "━━━━━━━━━━━━━━\n"
        "Gemini 상태\n"
        "━━━━━━━━━━━━━━\n"
        "현재 AI 최신정보 검증을 완료하지 못했습니다.\n\n"
        "따라서 위 데이터만으로\n"
        "급등 확률/성공 확률을 임의로 생성하지 않았습니다.\n"
    )

    return text


# =========================================================
# Telegram
# =========================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:

        print(
            "❌ TELEGRAM_BOT_TOKEN 없음"
        )

        return False

    if not TELEGRAM_CHAT_ID:

        print(
            "❌ TELEGRAM_CHAT_ID 없음"
        )

        return False

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}"
        "/sendMessage"
    )

    # Telegram 메시지 길이 제한 대응
    max_length = 3900

    chunks = []

    while len(message) > max_length:

        cut = message.rfind(
            "\n",
            0,
            max_length
        )

        if cut <= 0:
            cut = max_length

        chunks.append(
            message[:cut]
        )

        message = message[cut:]

    chunks.append(message)

    success = True

    for chunk in chunks:

        payload = {
            "chat_id":
            TELEGRAM_CHAT_ID,
            "text": chunk
        }

        try:

            response = requests.post(
                url,
                json=payload,
                timeout=15
            )

            print(
                "Telegram:",
                response.status_code
            )

            if response.status_code != 200:

                print(
                    response.text
                )

                success = False

        except Exception as e:

            print(
                f"Telegram 오류: {e}"
            )

            success = False

    return success


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "===================================="
    )

    print(
        "🇺🇸 미국 주식 전략 레이더"
    )

    print(
        now_kst()
    )

    print(
        "===================================="
    )

    # ---------------------------------------------
    # 1. 시장 데이터
    # ---------------------------------------------

    candidates = collect_candidates()

    # ---------------------------------------------
    # 2. Gemini 분석
    # ---------------------------------------------

    gemini_result = ask_gemini(
        candidates
    )

    # ---------------------------------------------
    # 3. Telegram 내용
    # ---------------------------------------------

    header = (
        "🚨 미국 주식 전략 레이더\n\n"
        f"⏰ {now_kst()}\n\n"
    )

    if gemini_result["success"]:

        print(
            "✅ Gemini 분석 성공"
        )

        report = (
            header +
            gemini_result["text"]
        )

        report += (
            "\n\n━━━━━━━━━━━━━━\n"
            "🤖 Gemini 상태\n"
            "━━━━━━━━━━━━━━\n"
            "✅ 최신 AI 분석 완료\n"
        )

    else:

        print(
            "⚠️ Gemini 실패:"
        )

        print(
            gemini_result["error"]
        )

        fallback = (
            make_fallback_report(
                candidates
            )
        )

        report = (
            header +
            fallback
        )

        report += (
            "\n\n⚠️ Gemini 오류\n"
            f"{gemini_result['error']}\n"
        )

    # ---------------------------------------------
    # 4. Telegram
    # ---------------------------------------------

    print(
        "📨 Telegram 전송"
    )

    send_telegram(
        report
    )

    print(
        "===================================="
    )

    print(
        "✅ 실행 종료"
    )


if __name__ == "__main__":
    main()
