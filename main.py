import os
import time
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

# ============================================================
# 환경변수
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# ============================================================
# 한국 주식 후보군
# KOSPI + KOSDAQ
# ============================================================

STOCKS = {
    # AI / 반도체
    "005930.KS": ("삼성전자", "대형주", "반도체"),
    "000660.KS": ("SK하이닉스", "대형주", "HBM/반도체"),
    "042700.KQ": ("한미반도체", "중형주", "반도체 장비"),
    "036540.KQ": ("SFA반도체", "중소형주", "반도체"),
    "058470.KQ": ("리노공업", "중형주", "반도체"),
    "403870.KQ": ("HPSP", "중형주", "반도체 장비"),

    # 2차전지
    "373220.KS": ("LG에너지솔루션", "대형주", "2차전지"),
    "006400.KS": ("삼성SDI", "대형주", "2차전지"),
    "247540.KQ": ("에코프로비엠", "중형주", "2차전지"),
    "086520.KQ": ("에코프로", "중형주", "2차전지"),
    "066970.KS": ("엘앤에프", "중형주", "2차전지"),

    # 바이오
    "068270.KS": ("셀트리온", "대형주", "바이오"),
    "207940.KS": ("삼성바이오로직스", "대형주", "바이오"),
    "196170.KQ": ("알테오젠", "대형주", "바이오"),
    "141080.KQ": ("리가켐바이오", "중형주", "바이오"),
    "145020.KQ": ("휴젤", "중형주", "바이오"),

    # AI / 로봇
    "277810.KQ": ("레인보우로보틱스", "중형주", "로봇"),
    "454910.KQ": ("두산로보틱스", "중형주", "로봇"),
    "108490.KQ": ("로보티즈", "중소형주", "로봇"),
    "270660.KQ": ("에브리봇", "중소형주", "로봇"),

    # 방산
    "012450.KS": ("한화에어로스페이스", "대형주", "방산"),
    "047810.KS": ("한국항공우주", "대형주", "방산"),
    "272210.KS": ("한화시스템", "중형주", "방산"),
    "079550.KS": ("LIG넥스원", "대형주", "방산"),

    # 조선
    "009540.KS": ("HD한국조선해양", "대형주", "조선"),
    "042660.KS": ("한화오션", "대형주", "조선"),
    "010140.KS": ("삼성중공업", "대형주", "조선"),
    "010620.KS": ("HD현대미포", "중형주", "조선"),

    # 전력 / 원전
    "015760.KS": ("한국전력", "대형주", "전력"),
    "034020.KS": ("두산에너빌리티", "대형주", "원전"),
    "267260.KS": ("HD현대일렉트릭", "대형주", "전력기기"),
    "298040.KS": ("효성중공업", "대형주", "전력기기"),

    # 콘텐츠 / 엔터
    "352820.KS": ("하이브", "대형주", "엔터"),
    "035900.KQ": ("JYP Ent.", "중형주", "엔터"),
    "041510.KQ": ("에스엠", "중형주", "엔터"),
    "122870.KQ": ("와이지엔터테인먼트", "중형주", "엔터"),

    # 플랫폼 / 인터넷
    "035420.KS": ("NAVER", "대형주", "인터넷"),
    "035720.KS": ("카카오", "대형주", "인터넷"),

    # 자동차
    "005380.KS": ("현대차", "대형주", "자동차"),
    "000270.KS": ("기아", "대형주", "자동차"),
}

# ============================================================
# 점수 계산
# ============================================================

def calculate_score(change_day, change_week, volume_ratio):
    score = 50

    # 일간 상승
    if change_day >= 15:
        score += 20
    elif change_day >= 8:
        score += 15
    elif change_day >= 4:
        score += 10
    elif change_day >= 2:
        score += 5

    # 주간 모멘텀
    if change_week >= 20:
        score += 15
    elif change_week >= 10:
        score += 10
    elif change_week >= 5:
        score += 5

    # 거래량
    if volume_ratio >= 3:
        score += 15
    elif volume_ratio >= 2:
        score += 12
    elif volume_ratio >= 1.5:
        score += 8
    elif volume_ratio >= 1.2:
        score += 5

    return min(score, 100)


def get_status(day_change, score):
    # 급등 직후에는 무조건 매수 추천하지 않음
    if day_change >= 20:
        return "⚠️ 과열주의"

    if score >= 80:
        return "🚀 급등 관심"

    if score >= 65:
        return "🔥 강한 관심"

    if score >= 55:
        return "🔄 반등 관심"

    return "🔎 관찰"


# ============================================================
# 주가 데이터
# ============================================================

def get_stock_data(ticker):

    try:
        stock = yf.Ticker(ticker)

        hist = stock.history(
            period="1mo",
            interval="1d",
            auto_adjust=False
        )

        if hist is None or len(hist) < 5:
            return None

        hist = hist.dropna()

        if len(hist) < 5:
            return None

        current = float(hist["Close"].iloc[-1])

        previous = float(hist["Close"].iloc[-2])

        week_base = float(hist["Close"].iloc[-6])

        day_change = ((current / previous) - 1) * 100

        week_change = ((current / week_base) - 1) * 100

        current_volume = float(hist["Volume"].iloc[-1])

        avg_volume = float(
            hist["Volume"].iloc[:-1].tail(20).mean()
        )

        if avg_volume > 0:
            volume_ratio = current_volume / avg_volume
        else:
            volume_ratio = 0

        name, size, sector = STOCKS[ticker]

        score = calculate_score(
            day_change,
            week_change,
            volume_ratio
        )

        status = get_status(
            day_change,
            score
        )

        return {
            "ticker": ticker,
            "name": name,
            "size": size,
            "sector": sector,
            "price": current,
            "day": day_change,
            "week": week_change,
            "volume": volume_ratio,
            "score": score,
            "status": status
        }

    except Exception as e:
        print(f"{ticker} 오류: {e}")
        return None


# ============================================================
# 전체 시장 검색
# ============================================================

def collect_market_data():

    results = []

    print("📊 한국 주식 시장 데이터 수집 시작")

    for ticker in STOCKS:

        data = get_stock_data(ticker)

        if data:
            results.append(data)

        # 너무 빠르게 요청하지 않음
        time.sleep(0.2)

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return results[:10]


# ============================================================
# Gemini 최신정보 분석
# ============================================================

def gemini_analysis(top10):

    if not GEMINI_API_KEY:

        return (
            "⚠️ Gemini API 키가 없습니다.\n"
            "시장 데이터 기반 TOP 10만 표시합니다."
        )

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/gemini-2.5-flash:generateContent"
        f"?key={GEMINI_API_KEY}"
    )

    stocks_text = ""

    for i, stock in enumerate(top10, 1):

        stocks_text += f"""
{i}. {stock['name']} ({stock['ticker']})
현재가: {stock['price']:.2f}
일간: {stock['day']:+.2f}%
주간: {stock['week']:+.2f}%
거래량: {stock['volume']:.2f}배
섹터: {stock['sector']}
유형: {stock['size']}
데이터 점수: {stock['score']}/100
"""

    prompt = f"""
당신은 한국 주식시장 전문 시니어 전략 분석가입니다.

현재 시점 기준으로 한국 KOSPI/KOSDAQ 종목을 분석합니다.

아래 종목들의 가격과 거래량 데이터를 참고하세요.

{stocks_text}

중요한 원칙:

1. 확인하지 못한 뉴스는 절대 만들어내지 마세요.
2. 실제 존재하지 않는 공시/기사/계약을 만들지 마세요.
3. 급등 확률을 확정적인 수익률처럼 표현하지 마세요.
4. '매수 확정'이라는 표현을 사용하지 마세요.
5. 대형주뿐 아니라 중형주와 소형주도 분석하세요.
6. 단순히 이미 많이 오른 종목만 추천하지 말고 반등 가능성이 있는 종목도 찾으세요.
7. 급등 가능성과 과열 가능성을 동시에 평가하세요.

각 종목에 대해 다음을 분석하세요.

- 핵심 재료
- 상승 촉매
- 하락 위험
- 반등 가능성
- 과열 여부
- 단기 관찰 포인트

그리고 TOP 10 중에서

🔥 단기 모멘텀 TOP 3
🔄 반등 후보 TOP 3
⚠️ 급락/과열 주의 TOP 3

를 선정하세요.

확인되지 않은 뉴스는
'확인 필요'라고 표시하세요.

마지막에는

'오늘 가장 중요한 3개 종목'

을 선정하고 이유를 짧게 설명하세요.

한국어로 작성하세요.
텔레그램에서 읽기 편하게 간결하게 작성하세요.
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:

            data = response.json()

            candidates = data.get(
                "candidates",
                []
            )

            if candidates:

                parts = candidates[0] \
                    .get("content", {}) \
                    .get("parts", [])

                if parts:

                    return parts[0].get(
                        "text",
                        "AI 분석 결과 없음"
                    )

        # 429
        if response.status_code == 429:

            return (
                "⚠️ Gemini API 사용량 제한\n\n"
                "이번 분석에서는 Gemini 최신정보 "
                "검증을 완료하지 못했습니다.\n\n"
                "시장 데이터 TOP 10은 정상적으로 "
                "수집되었습니다.\n\n"
                "※ 확인되지 않은 뉴스나 확률은 "
                "생성하지 않았습니다."
            )

        # 404
        if response.status_code == 404:

            return (
                "⚠️ Gemini 모델 연결 오류\n\n"
                "Gemini API 모델을 사용할 수 없습니다.\n\n"
                "시장 데이터 분석은 정상적으로 "
                "완료되었습니다.\n\n"
                "※ AI가 확인하지 못한 정보는 "
                "임의로 생성하지 않았습니다."
            )

        return (
            f"⚠️ Gemini 분석 실패\n"
            f"HTTP {response.status_code}\n\n"
            "시장 데이터 TOP 10은 정상적으로 "
            "수집되었습니다."
        )

    except Exception as e:

        return (
            "⚠️ Gemini 분석 연결 실패\n\n"
            f"{str(e)[:300]}\n\n"
            "시장 데이터 TOP 10은 정상적으로 "
            "수집되었습니다."
        )


# ============================================================
# 텔레그램 메시지
# ============================================================

def create_message(top10, ai_text):

    kst = timezone(
        timedelta(hours=9)
    )

    now = datetime.now(kst)

    message = f"""
🚨 한국 주식 전략 레이더

⏰ {now.strftime('%Y-%m-%d %H:%M:%S')} KST

━━━━━━━━━━━━━━━━━━
🇰🇷 KOSPI / KOSDAQ TOP 10
━━━━━━━━━━━━━━━━━━
"""

    for i, stock in enumerate(top10, 1):

        message += f"""
{i}️⃣ {stock['name']}
({stock['ticker'].replace('.KS','').replace('.KQ','')})

💵 현재가: {stock['price']:,.0f}원
📈 일간: {stock['day']:+.2f}%
📊 주간: {stock['week']:+.2f}%
🔥 거래량: {stock['volume']:.2f}배

⭐ 데이터 점수: {stock['score']}/100
📌 상태: {stock['status']}
🏷 유형: {stock['size']}
🏭 섹터: {stock['sector']}

"""

    message += """
━━━━━━━━━━━━━━━━━━
🤖 AI 시니어 전략 분석
━━━━━━━━━━━━━━━━━━

"""

    message += ai_text

    message += """

━━━━━━━━━━━━━━━━━━
⚠️ 투자 주의
━━━━━━━━━━━━━━━━━━

이 레이더는 시장 데이터를 이용해
관심 종목을 자동 선별하는 분석 도구입니다.

데이터 점수와 AI 분석은
수익을 보장하는 확률이 아닙니다.

특히 소형주와 급등주는
높은 변동성과 손실 위험이 있습니다.

AI가 확인하지 못한 뉴스나 공시는
임의로 생성하지 않습니다.

투자 전 반드시 거래소 공시,
기업 공시, 실적 및 시장 상황을
추가 확인하세요.
"""

    return message


# ============================================================
# 텔레그램 전송
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:

        print("❌ TELEGRAM_BOT_TOKEN 없음")
        return False

    if not TELEGRAM_CHAT_ID:

        print("❌ TELEGRAM_CHAT_ID 없음")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
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

        return response.status_code == 200

    except Exception as e:

        print(
            "Telegram 오류:",
            e
        )

        return False


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 50)
    print("🇰🇷 한국 주식 전략 레이더 시작")
    print("=" * 50)

    # 1. 시장 데이터
    top10 = collect_market_data()

    if not top10:

        message = """
🚨 한국 주식 전략 레이더

시장 데이터를 수집하지 못했습니다.

다음 실행 주기에 다시 시도합니다.

가능한 원인:
- yfinance 연결 문제
- Yahoo Finance 응답 지연
- 인터넷/API 오류
- 장외 시간 데이터 문제
"""

        send_telegram(message)

        return

    print(
        f"✅ {len(top10)}개 종목 수집 완료"
    )

    # 2. Gemini
    print(
        "🤖 Gemini 최신정보 분석 요청"
    )

    ai_text = gemini_analysis(top10)

    # 3. 텔레그램
    message = create_message(
        top10,
        ai_text
    )

    send_telegram(message)

    print(
        "✅ 한국 주식 레이더 전송 완료"
    )


if __name__ == "__main__":
    main()
