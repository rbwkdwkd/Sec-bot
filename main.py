import os
import time
from datetime import datetime, timezone, timedelta

import requests
import yfinance as yf


# ============================================================
# 환경변수
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


# ============================================================
# 분석 대상
# 대형주 + 중형주 + 소형주를 섞어서 구성
# ============================================================

TICKERS = {
    "NVDA": "NVIDIA",
    "AMD": "AMD",
    "INTC": "Intel",
    "ANET": "Arista Networks",
    "LRCX": "Lam Research",
    "AMAT": "Applied Materials",

    "CRWV": "CoreWeave",
    "NBIS": "Nebius",
    "IREN": "IREN",
    "SMCI": "Super Micro Computer",

    "IONQ": "IonQ",
    "ASTS": "AST SpaceMobile",
    "LUNR": "Intuitive Machines",
    "SOUN": "SoundHound AI",
}


# ============================================================
# Yahoo Finance 데이터 수집
# ============================================================

def get_market_data(ticker):

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

        current_price = float(close.iloc[-1])

        daily_change = (
            (close.iloc[-1] / close.iloc[-2]) - 1
        ) * 100

        weekly_change = (
            (close.iloc[-1] / close.iloc[-6]) - 1
        ) * 100 if len(close) >= 6 else 0

        avg_volume = volume.iloc[:-1].tail(20).mean()

        if avg_volume and avg_volume > 0:
            volume_ratio = volume.iloc[-1] / avg_volume
        else:
            volume_ratio = 1.0

        return {
            "ticker": ticker,
            "name": TICKERS[ticker],
            "price": current_price,
            "daily": daily_change,
            "weekly": weekly_change,
            "volume_ratio": volume_ratio,
        }

    except Exception as e:
        print(f"{ticker} 데이터 오류: {e}")
        return None


# ============================================================
# 대형/중형/소형 구분
# 실제 시총 조회가 실패해도 프로그램이 죽지 않도록 처리
# ============================================================

def get_company_type(ticker):

    large = {
        "NVDA",
        "AMD",
        "INTC",
        "ANET",
        "LRCX",
        "AMAT",
    }

    if ticker in large:
        return "대형주"

    medium = {
        "CRWV",
        "NBIS",
        "IREN",
        "SMCI",
        "IONQ",
    }

    if ticker in medium:
        return "중형주"

    return "소형주"


# ============================================================
# 자동 데이터 점수
#
# 가격 상승 + 거래량 증가 + 주간 모멘텀을 이용
#
# 주의:
# 이것은 AI가 만든 확률이 아니라
# 실제 가격/거래량에서 계산한 참고 점수
# ============================================================

def calculate_score(data):

    daily = data["daily"]
    weekly = data["weekly"]
    volume = data["volume_ratio"]

    score = 40

    # 일간 모멘텀
    if daily >= 15:
        score += 20
    elif daily >= 8:
        score += 15
    elif daily >= 4:
        score += 10
    elif daily >= 0:
        score += 5
    elif daily <= -10:
        score -= 10
    elif daily <= -5:
        score -= 5

    # 주간 모멘텀
    if weekly >= 20:
        score += 15
    elif weekly >= 10:
        score += 10
    elif weekly >= 5:
        score += 7
    elif weekly >= 0:
        score += 3
    elif weekly <= -15:
        score -= 10
    elif weekly <= -5:
        score -= 5

    # 거래량
    if volume >= 3:
        score += 15
    elif volume >= 2:
        score += 12
    elif volume >= 1.5:
        score += 8
    elif volume >= 1.2:
        score += 5
    elif volume < 0.7:
        score -= 5

    score = max(0, min(100, score))

    return round(score, 1)


# ============================================================
# 상태 판단
# ============================================================

def get_status(data, score):

    daily = data["daily"]
    volume = data["volume_ratio"]

    # 지나치게 급등한 경우
    if daily >= 25:
        return "⚠️ 과열주의"

    # 강한 거래량 + 강한 상승
    if score >= 70 and daily >= 8 and volume >= 1.5:
        return "🚀 급등 관심"

    if score >= 65:
        return "🔥 강한 관심"

    if score >= 55:
        return "🔄 반등 관심"

    return "🔎 관찰"


# ============================================================
# Gemini 호출
#
# 중요:
# 기존 gemini-2.5-flash 문제를 피하기 위해
# 환경변수 GEMINI_MODEL을 사용할 수 있도록 구성
# ============================================================

def call_gemini(report_data):

    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY 없음"

    model = os.environ.get(
        "GEMINI_MODEL",
        "gemini-2.0-flash"
    ).strip()

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
        f"?key={GEMINI_API_KEY}"
    )

    prompt = f"""
당신은 미국 주식 시장을 분석하는 시니어 전략 분석가입니다.

아래는 실제 시장 데이터로 수집한 종목 목록입니다.

{report_data}

중요 규칙:

1. 제공된 가격과 거래량을 사실로 사용하세요.
2. 확인되지 않은 뉴스나 기업 재료를 만들어내지 마세요.
3. 실시간 웹 검색이 제공되지 않은 경우 최신 뉴스라고 단정하지 마세요.
4. 급등 가능성은 '예측'이며 확정된 사실처럼 표현하지 마세요.
5. 하루 최종 관심 종목은 최대 10개만 선정하세요.
6. 대형주만 선정하지 말고 중형주와 소형주도 포함할 수 있습니다.
7. 단순히 이미 급등한 종목만 고르지 말고,
   거래량 증가, 주간 모멘텀, 아직 과열되지 않은 종목을 함께 평가하세요.
8. 위험도가 지나치게 높은 종목은 반드시 위험성을 표시하세요.

각 종목에 대해 다음을 작성하세요.

- 종목명 / 티커
- 선정 이유
- 상승 촉매 가능성
- 급락 위험
- 현재 구간 평가
- 1~10점 관심도

마지막에

'오늘의 TOP 3'

를 별도로 선정하세요.

그리고 전체 시장에서
대형주 / 중형주 / 소형주 중
어느 쪽이 상대적으로 유리한지 설명하세요.

투자 확정 추천이 아니라 데이터 기반 참고용 분석이라는 점도 표시하세요.
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
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 3000
        }
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

        result = response.json()

        if response.status_code == 200:

            candidates = result.get("candidates", [])

            if candidates:

                text = (
                    candidates[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )

                if text:
                    return text, None

        error_message = (
            result
            .get("error", {})
            .get("message", str(result))
        )

        return None, (
            f"Gemini 오류 {response.status_code}: "
            f"{error_message}"
        )

    except Exception as e:

        return None, f"Gemini 요청 오류: {e}"


# ============================================================
# 텔레그램
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN 없음")
        return False

    if not TELEGRAM_CHAT_ID:
        print("TELEGRAM_CHAT_ID 없음")
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
            response.status_code,
            response.text[:300]
        )

        return response.status_code == 200

    except Exception as e:

        print("Telegram 오류:", e)

        return False


# ============================================================
# 시간
# ============================================================

def get_kst():

    kst = timezone(timedelta(hours=9))

    return datetime.now(kst).strftime(
        "%Y-%m-%d %H:%M:%S KST"
    )


# ============================================================
# 메인 분석
# ============================================================

def main():

    print("미국 주식 전략 레이더 시작")

    market_data = []

    for ticker in TICKERS:

        print(f"{ticker} 데이터 수집 중...")

        data = get_market_data(ticker)

        if data:

            data["score"] = calculate_score(data)

            data["status"] = get_status(
                data,
                data["score"]
            )

            data["type"] = get_company_type(
                ticker
            )

            market_data.append(data)

        time.sleep(0.5)

    # ========================================================
    # 데이터 수집 실패
    # ========================================================

    if not market_data:

        message = f"""
🚨 미국 주식 전략 레이더

⏰ {get_kst()}

❌ 시장 데이터 수집 실패

Yahoo Finance에서 현재 데이터를 가져오지 못했습니다.

다음 실행 주기에 다시 시도합니다.

※ 데이터가 없을 경우
임의의 주가/종목/확률을 생성하지 않습니다.
"""

        send_telegram(message)
        return

    # 점수순 정렬
    market_data.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # 상위 10개
    top10 = market_data[:10]

    # ========================================================
    # 데이터 보고서
    # ========================================================

    report_lines = []

    for i, d in enumerate(top10, 1):

        report_lines.append(
            f"""
{i}. {d['ticker']} ({d['name']})
가격: ${d['price']:.2f}
일간: {d['daily']:+.2f}%
주간: {d['weekly']:+.2f}%
거래량: {d['volume_ratio']:.2f}배
데이터점수: {d['score']}/100
상태: {d['status']}
유형: {d['type']}
"""
        )

    raw_report = "\n".join(report_lines)

    # ========================================================
    # Gemini 분석
    # ========================================================

    print("Gemini 분석 요청")

    ai_report, gemini_error = call_gemini(
        raw_report
    )

    # ========================================================
    # Telegram 메시지
    # ========================================================

    message = f"""
🚨 미국 주식 전략 레이더

⏰ {get_kst()}

━━━━━━━━━━━━━━━━━━
📊 오늘의 TOP 10
━━━━━━━━━━━━━━━━━━
"""

    for i, d in enumerate(top10, 1):

        message += f"""
{i}️⃣ {d['ticker']} ({d['name']})

💵 현재가: ${d['price']:.2f}
📈 일간: {d['daily']:+.2f}%
📊 주간: {d['weekly']:+.2f}%
🔥 거래량: {d['volume_ratio']:.2f}배

⭐ 데이터 점수: {d['score']}/100
📌 상태: {d['status']}
🏷 유형: {d['type']}

"""

    message += """
━━━━━━━━━━━━━━━━━━
🤖 AI 전략 분석
━━━━━━━━━━━━━━━━━━
"""

    if ai_report:

        message += ai_report

    else:

        message += """
⚠️ Gemini AI 분석을 완료하지 못했습니다.

시장 데이터는 정상적으로 수집되었지만
AI 최신정보 검증은 실패했습니다.

따라서 확인되지 않은 뉴스,
급등 확률, 성공 확률을 임의로 생성하지 않았습니다.

"""

        if gemini_error:

            message += f"""
오류:
{gemini_error}
"""

    message += """

━━━━━━━━━━━━━━━━━━
⚠️ 투자 유의사항
━━━━━━━━━━━━━━━━━━

본 레이더는 시장 데이터를 기반으로
관심 종목을 자동 선별하는 시스템입니다.

데이터 점수와 AI 분석은
주가 상승을 보장하는 확률이 아닙니다.

특히 소형주는 변동성과 손실 위험이
대형주보다 클 수 있습니다.

투자 판단 전 실적, 공시, 재무상태,
거래량 및 시장 상황을 추가 확인하세요.
"""

    send_telegram(message)

    print("분석 완료")


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    main()
