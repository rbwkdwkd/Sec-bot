import os
import time
import requests
from datetime import datetime, timezone, timedelta

# ============================================================
# 선택 라이브러리
# GitHub Actions requirements.txt에 설치 필요
# yfinance
# google-genai
# ============================================================

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


# ============================================================
# 환경변수
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


# ============================================================
# 설정
# ============================================================

# Gemini 모델은 환경변수로 바꿀 수 있게 함.
# 모델 오류가 나면 Gemini 없이도 레이더는 계속 작동한다.
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)

MAX_GEMINI_RETRIES = 2


# ============================================================
# 분석 대상
#
# 대형주 + 중형주 + 소형주를 섞음
# ============================================================

WATCHLIST = {
    # AI / 반도체
    "NVDA": "NVIDIA",
    "AMD": "AMD",
    "AVGO": "Broadcom",
    "ANET": "Arista Networks",
    "LRCX": "Lam Research",
    "AMAT": "Applied Materials",
    "INTC": "Intel",
    "MU": "Micron",

    # AI 데이터센터
    "CRWV": "CoreWeave",
    "NBIS": "Nebius",
    "IREN": "IREN",
    "SMCI": "Super Micro Computer",

    # 우주 / 고변동성
    "LUNR": "Intuitive Machines",
    "ASTS": "AST SpaceMobile",

    # 양자
    "IONQ": "IonQ",

    # AI 소형주
    "SOUN": "SoundHound AI",
    "BBAI": "BigBear.ai",
    "TEM": "Tempus AI",
}


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):
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
            response.text
        )

    except Exception as e:
        print("Telegram 전송 실패:", e)

    return False


# ============================================================
# 숫자 안전 처리
# ============================================================

def safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        value = float(value)

        if value != value:
            return default

        return value

    except Exception:
        return default


# ============================================================
# 시장 데이터 수집
# ============================================================

def get_market_data(ticker):
    """
    Yahoo Finance 데이터를 이용해
    가격 / 일간 / 주간 / 거래량 / 변동성을 계산
    """

    if yf is None:
        return None

    try:
        stock = yf.Ticker(ticker)

        hist = stock.history(
            period="1mo",
            interval="1d",
            auto_adjust=False
        )

        if hist is None or hist.empty:
            return None

        hist = hist.dropna()

        if len(hist) < 5:
            return None

        close = hist["Close"]
        volume = hist["Volume"]

        current_price = safe_float(close.iloc[-1])

        if current_price <= 0:
            return None

        # 전일 대비
        if len(close) >= 2:
            daily_change = (
                current_price / safe_float(close.iloc[-2], current_price)
                - 1
            ) * 100
        else:
            daily_change = 0

        # 5거래일 대비
        if len(close) >= 6:
            weekly_change = (
                current_price / safe_float(close.iloc[-6], current_price)
                - 1
            ) * 100
        else:
            weekly_change = daily_change

        # 최근 20일 평균 거래량
        avg_volume = safe_float(
            volume.iloc[:-1].tail(20).mean()
        )

        current_volume = safe_float(
            volume.iloc[-1]
        )

        if avg_volume > 0:
            volume_ratio = current_volume / avg_volume
        else:
            volume_ratio = 1.0

        # 최근 20일 변동성
        returns = close.pct_change().dropna()

        if len(returns) > 2:
            volatility = safe_float(
                returns.tail(20).std() * 100
            )
        else:
            volatility = 0

        # 최근 고점 대비 하락률
        recent_high = safe_float(
            close.tail(20).max(),
            current_price
        )

        if recent_high > 0:
            drawdown = (
                current_price / recent_high - 1
            ) * 100
        else:
            drawdown = 0

        return {
            "ticker": ticker,
            "price": current_price,
            "daily": daily_change,
            "weekly": weekly_change,
            "volume_ratio": volume_ratio,
            "volatility": volatility,
            "drawdown": drawdown
        }

    except Exception as e:
        print(f"{ticker} 데이터 오류:", e)
        return None


# ============================================================
# 종목 유형
# ============================================================

def classify_stock(ticker):
    large = {
        "NVDA", "AMD", "AVGO",
        "ANET", "LRCX", "AMAT",
        "INTC", "MU"
    }

    small = {
        "SOUN", "BBAI", "LUNR",
        "ASTS", "IONQ"
    }

    if ticker in large:
        return "대형주"

    if ticker in small:
        return "소형/고변동"

    return "중형주"


# ============================================================
# 시장 데이터 점수
# ============================================================

def calculate_score(data):
    """
    실제 가격/거래량 데이터만 이용.
    AI가 만든 가짜 확률은 사용하지 않는다.
    """

    daily = data["daily"]
    weekly = data["weekly"]
    volume = data["volume_ratio"]
    volatility = data["volatility"]
    drawdown = data["drawdown"]

    score = 0

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

    if 3 <= daily <= 12:
        score += 20

    elif 1 <= daily < 3:
        score += 15

    elif 12 < daily <= 20:
        score += 12

    elif daily > 20:
        # 이미 너무 많이 오른 경우 추격 위험
        score += 5

    elif daily < -10:
        score += 3

    # --------------------------------------------------------
    # 주간 모멘텀
    # --------------------------------------------------------

    if 5 <= weekly <= 20:
        score += 20

    elif 0 <= weekly < 5:
        score += 12

    elif 20 < weekly <= 35:
        score += 10

    elif weekly > 35:
        score += 5

    # --------------------------------------------------------
    # 눌림/반등 가능성
    # --------------------------------------------------------

    if -15 <= drawdown <= -5:
        score += 15

    elif -5 < drawdown <= 0:
        score += 8

    # --------------------------------------------------------
    # 변동성
    # --------------------------------------------------------

    if 2 <= volatility <= 8:
        score += 10

    elif 8 < volatility <= 15:
        score += 7

    elif volatility > 15:
        score += 3

    return min(score, 100)


# ============================================================
# 상태 판단
# ============================================================

def get_status(data, score):

    daily = data["daily"]
    volume = data["volume_ratio"]

    # 이미 급등 + 거래량 폭발
    if daily >= 20 and volume >= 2:
        return "⚠️ 급등 후 과열주의"

    if score >= 75:
        return "🚀 급등 관심"

    if score >= 65:
        return "🔥 강한 관심"

    if score >= 55:
        return "🔄 반등 관심"

    return "🔎 관찰"


# ============================================================
# Gemini 분석
# ============================================================

def gemini_analysis(candidates):

    if not GEMINI_API_KEY:
        return None, "API KEY 없음"

    if genai is None:
        return None, "google-genai 라이브러리 없음"

    compact_data = []

    for item in candidates:

        compact_data.append({
            "ticker": item["ticker"],
            "name": item["name"],
            "price": round(item["price"], 2),
            "daily": round(item["daily"], 2),
            "weekly": round(item["weekly"], 2),
            "volume": round(item["volume_ratio"], 2),
            "score": item["score"],
            "type": item["type"]
        })

    prompt = f"""
당신은 미국 주식 전략 분석가다.

아래는 실제 시장 데이터로 계산된 후보 종목이다.

{compact_data}

중요 규칙:

1. 확인되지 않은 뉴스나 사실을 만들어내지 마라.
2. 실시간 뉴스를 실제로 확인하지 못했다면 확인하지 못했다고 명시하라.
3. 확률을 실제 통계적 확률처럼 표현하지 마라.
4. '전략 점수'와 '상승 시나리오 가능성'을 구분하라.
5. 이미 하루에 20% 이상 오른 종목은 추격매수 위험을 반드시 표시하라.
6. 대형주만 선정하지 말고 중형주/소형주도 평가하라.
7. 가격 상승률만 보고 추천하지 마라.
8. 거래량과 주간 추세를 함께 고려하라.
9. 투자 판단을 확정적으로 표현하지 마라.

다음 형식으로 매우 짧게 작성하라.

각 종목:
티커:
판단:
핵심 이유:
상승 촉매:
주요 위험:

마지막:
오늘 가장 주목할 3개:
1.
2.
3.

그리고 마지막 줄에
"뉴스/GitHub/Google Trends 실시간 검증 여부"를 표시하라.
"""

    try:

        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        for attempt in range(MAX_GEMINI_RETRIES):

            try:

                config = types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=1800
                )

                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=config
                )

                text = getattr(
                    response,
                    "text",
                    None
                )

                if text:
                    return text, None

                return None, "Gemini 응답 내용 없음"

            except Exception as e:

                error = str(e)

                print(
                    f"Gemini 오류 {attempt + 1}:",
                    error
                )

                lower = error.lower()

                # 모델 자체가 존재하지 않는 경우
                # 재시도해도 의미 없음
                if "404" in lower or "not found" in lower:
                    return None, error

                # quota는 짧게 재시도
                if "429" in lower or "quota" in lower:
                    if attempt + 1 < MAX_GEMINI_RETRIES:
                        time.sleep(5)
                        continue

                    return None, error

                if attempt + 1 < MAX_GEMINI_RETRIES:
                    time.sleep(3)
                    continue

                return None, error

    except Exception as e:
        return None, str(e)


# ============================================================
# 메시지 생성
# ============================================================

def build_message(results, gemini_text, gemini_error):

    KST = timezone(
        timedelta(hours=9)
    )

    now = datetime.now(
        KST
    ).strftime(
        "%Y-%m-%d %H:%M:%S KST"
    )

    lines = []

    lines.append(
        "🚨 미국 주식 전략 레이더"
    )

    lines.append("")
    lines.append(
        f"⏰ {now}"
    )

    lines.append("")
    lines.append(
        "📊 실제 가격/거래량 기반 TOP 10"
    )

    lines.append(
        "※ 데이터 점수는 시장 데이터 계산값입니다."
    )

    lines.append(
        "※ 투자 성공확률을 보장하는 지표가 아닙니다."
    )

    lines.append("")
    lines.append(
        "━━━━━━━━━━━━━━"
    )

    for index, item in enumerate(
        results,
        start=1
    ):

        ticker = item["ticker"]

        name = item["name"]

        price = item["price"]

        daily = item["daily"]

        weekly = item["weekly"]

        volume = item["volume_ratio"]

        score = item["score"]

        status = item["status"]

        stock_type = item["type"]

        lines.append(
            f"{index}️⃣ {ticker} ({name})"
        )

        lines.append(
            f"현재가: ${price:.2f}"
        )

        lines.append(
            f"일간: {daily:+.2f}%"
        )

        lines.append(
            f"주간: {weekly:+.2f}%"
        )

        lines.append(
            f"거래량: {volume:.2f}배"
        )

        lines.append(
            f"데이터 점수: {score:.0f}/100"
        )

        lines.append(
            f"상태: {status}"
        )

        lines.append(
            f"유형: {stock_type}"
        )

        # 과열 경고
        if daily >= 20:
            lines.append(
                "⚠️ 이미 급등: 추격매수 주의"
            )

        elif daily >= 10:
            lines.append(
                "⚠️ 단기 상승폭 확대"
            )

        lines.append("")

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    # --------------------------------------------------------
    # Gemini 결과
    # --------------------------------------------------------

    if gemini_text:

        lines.append("")
        lines.append(
            "🤖 Gemini 전략 검토"
        )

        lines.append("")
        lines.append(
            gemini_text
        )

    else:

        lines.append("")
        lines.append(
            "⚠️ Gemini 최신정보 검증"
        )

        lines.append(
            "현재 Gemini 분석을 완료하지 못했습니다."
        )

        if gemini_error:

            lower = gemini_error.lower()

            if "429" in lower or "quota" in lower:

                lines.append(
                    "원인: Gemini API quota/rate limit"
                )

            elif "404" in lower:

                lines.append(
                    "원인: Gemini 모델/엔드포인트 오류"
                )

            else:

                lines.append(
                    "원인: Gemini API 오류"
                )

        lines.append("")
        lines.append(
            "따라서 확인되지 않은 뉴스나"
        )

        lines.append(
            "급등확률을 임의로 생성하지 않았습니다."
        )

    lines.append("")
    lines.append(
        "━━━━━━━━━━━━━━"
    )

    lines.append(
        "⚠️ 참고: 본 레이더는 자동 분석 도구이며 "
        "투자 수익이나 성공을 보장하지 않습니다."
    )

    return "\n".join(lines)


# ============================================================
# 메인
# ============================================================

def main():

    print("================================")
    print("미국 주식 전략 레이더 시작")
    print("================================")

    # --------------------------------------------------------
    # 환경변수
    # --------------------------------------------------------

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

        message = (
            "🚨 미국 주식 전략 레이더\n\n"
            "Telegram 환경변수가 없습니다.\n\n"
            + "\n".join(
                f"- {x}" for x in missing
            )
        )

        print(message)

        return

    # --------------------------------------------------------
    # yfinance 확인
    # --------------------------------------------------------

    if yf is None:

        message = (
            "🚨 미국 주식 전략 레이더\n\n"
            "시장 데이터 라이브러리 "
            "yfinance가 설치되지 않았습니다.\n\n"
            "requirements.txt를 확인하세요."
        )

        send_telegram(message)

        return

    # --------------------------------------------------------
    # 시장 데이터
    # --------------------------------------------------------

    print("시장 데이터 수집 시작")

    market_results = []

    for ticker, name in WATCHLIST.items():

        print(
            f"{ticker} 데이터 수집 중..."
        )

        data = get_market_data(
            ticker
        )

        if not data:
            continue

        score = calculate_score(
            data
        )

        data["name"] = name

        data["score"] = score

        data["type"] = classify_stock(
            ticker
        )

        data["status"] = get_status(
            data,
            score
        )

        market_results.append(
            data
        )

    # --------------------------------------------------------
    # 데이터 실패
    # --------------------------------------------------------

    if not market_results:

        message = (
            "🚨 미국 주식 전략 레이더\n\n"
            "시장 데이터를 수집하지 못했습니다.\n\n"
            "다음 실행 주기에 다시 시도합니다."
        )

        send_telegram(message)

        return

    # --------------------------------------------------------
    # 점수 정렬
    # --------------------------------------------------------

    market_results.sort(
        key=lambda x: (
            x["score"],
            x["volume_ratio"],
            x["weekly"]
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # 대형주만 나오지 않도록 구성
    #
    # 전체 점수 상위에서 먼저 뽑고,
    # 소형주가 일정 수준 이상이면 최소 2개 포함
    # --------------------------------------------------------

    top_candidates = market_results[:10]

    small_candidates = [
        x for x in market_results
        if x["type"] == "소형/고변동"
    ]

    # 소형주 최소 2개 시도
    for small in small_candidates:

        if small not in top_candidates:

            replace_index = None

            # 가장 낮은 점수 대형/중형 종목 찾기
            for i in range(
                len(top_candidates) - 1,
                -1,
                -1
            ):

                if (
                    top_candidates[i]["type"]
                    != "소형/고변동"
                    and
                    small["score"]
                    >=
                    top_candidates[i]["score"] - 8
                ):
                    replace_index = i
                    break

            if replace_index is not None:

                top_candidates[
                    replace_index
                ] = small

    top_candidates.sort(
        key=lambda x: (
            x["score"],
            x["volume_ratio"],
            x["weekly"]
        ),
        reverse=True
    )

    top_candidates = top_candidates[:10]

    # --------------------------------------------------------
    # Gemini
    # --------------------------------------------------------

    print("Gemini 전략 검토 시작")

    gemini_text, gemini_error = (
        gemini_analysis(
            top_candidates
        )
    )

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    final_message = build_message(
        top_candidates,
        gemini_text,
        gemini_error
    )

    print("")
    print(final_message)

    send_telegram(
        final_message
    )

    print("")
    print("================================")
    print("레이더 실행 완료")
    print("================================")


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    main()
