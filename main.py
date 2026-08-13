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

# 현재 Gemini 모델
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.1-flash-lite"
).strip()


# ============================================================
# 분석 종목
# 대형 + 중형 + 소형주 혼합
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
# 한국시간
# ============================================================

def get_kst():

    kst = timezone(timedelta(hours=9))

    return datetime.now(kst).strftime(
        "%Y-%m-%d %H:%M:%S KST"
    )


# ============================================================
# Yahoo Finance 데이터
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
            close.iloc[-1] / close.iloc[-2] - 1
        ) * 100

        weekly_change = (
            close.iloc[-1] / close.iloc[-6] - 1
        ) * 100 if len(close) >= 6 else 0

        average_volume = (
            volume.iloc[:-1]
            .tail(20)
            .mean()
        )

        if average_volume and average_volume > 0:

            volume_ratio = (
                volume.iloc[-1] /
                average_volume
            )

        else:

            volume_ratio = 1.0

        return {
            "ticker": ticker,
            "name": TICKERS[ticker],
            "price": current_price,
            "daily": daily_change,
            "weekly": weekly_change,
            "volume_ratio": volume_ratio
        }

    except Exception as e:

        print(
            f"{ticker} 데이터 수집 실패: {e}"
        )

        return None


# ============================================================
# 기업 규모
# ============================================================

def get_company_type(ticker):

    large = {
        "NVDA",
        "AMD",
        "INTC",
        "ANET",
        "LRCX",
        "AMAT"
    }

    medium = {
        "CRWV",
        "NBIS",
        "IREN",
        "SMCI",
        "IONQ"
    }

    if ticker in large:
        return "대형주"

    if ticker in medium:
        return "중형주"

    return "소형주"


# ============================================================
# 자동 데이터 점수
# ============================================================

def calculate_score(data):

    daily = data["daily"]
    weekly = data["weekly"]
    volume = data["volume_ratio"]

    score = 40

    # 일간 상승
    if daily >= 20:
        score += 20

    elif daily >= 10:
        score += 16

    elif daily >= 5:
        score += 12

    elif daily >= 2:
        score += 7

    elif daily >= 0:
        score += 3

    # 일간 하락
    elif daily <= -10:
        score -= 10

    elif daily <= -5:
        score -= 6

    # 주간 모멘텀
    if weekly >= 20:
        score += 15

    elif weekly >= 10:
        score += 12

    elif weekly >= 5:
        score += 8

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

    return max(
        0,
        min(100, round(score, 1))
    )


# ============================================================
# 상태
# ============================================================

def get_status(data, score):

    daily = data["daily"]
    volume = data["volume_ratio"]

    if daily >= 25:
        return "⚠️ 과열주의"

    if (
        score >= 70
        and daily >= 8
        and volume >= 1.5
    ):
        return "🚀 급등 관심"

    if score >= 65:
        return "🔥 강한 관심"

    if score >= 55:
        return "🔄 반등 관심"

    return "🔎 관찰"


# ============================================================
# Gemini Interactions API
#
# Google Search grounding 사용
# ============================================================

def call_gemini(report_data):

    if not GEMINI_API_KEY:

        return None, "GEMINI_API_KEY가 없습니다."

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1/interactions"
    )

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }

    system_instruction = """
당신은 미국 주식 시장을 분석하는
시니어 주식 전략 분석가입니다.

반드시 다음 원칙을 지키십시오.

1. 최신 뉴스와 시장 정보를 검색하여 확인하십시오.
2. 확인되지 않은 뉴스를 만들어내지 마십시오.
3. 과거 뉴스를 현재 뉴스처럼 사용하지 마십시오.
4. 종목의 실제 가격과 거래량은 제공된 시장 데이터를 우선 사용하십시오.
5. 뉴스가 존재하면 반드시 현재 시점과 관련성이 있는지 검토하십시오.
6. 대형주만 추천하지 마십시오.
7. 중형주와 소형주도 분석하십시오.
8. 단순 급등주 추격과 반등 가능성이 있는 종목을 구분하십시오.
9. 급등 가능성과 급락 위험을 모두 평가하십시오.
10. 투자 성공을 보장하는 표현을 사용하지 마십시오.

특히 다음 요소를 종합하십시오.

- 최신 기업 뉴스
- 실적
- 가이던스
- 신규 계약
- AI 관련 투자
- 반도체 업황
- 금리
- 국채금리
- 유가
- 시장 전체 분위기
- 거래량
- 단기 모멘텀
- 과열 여부
- 소형주 수급
- 공매도/숏스퀴즈 가능성이 확인되는 경우
- 상장 예정/IPO 관련 뉴스가 실제로 확인되는 경우
- 기업의 공식 발표

GitHub 분석은 실제 GitHub 데이터가 제공되거나
검색으로 확인되는 경우에만 사용하십시오.

Google Trends 역시 실제 확인 가능한 정보가 있을 때만 사용하십시오.

확인되지 않은 데이터를 숫자로 만들어내지 마십시오.
"""


    user_prompt = f"""
현재 한국시간:

{get_kst()}

아래는 실제 시장 데이터로 수집한 종목입니다.

{report_data}

위 종목을 대상으로 최신 미국 주식 시장 정보를 검색하여
교차검증한 뒤 전략 분석을 수행하십시오.

==============================

최종 결과는 다음 형식으로 작성하십시오.

[오늘의 미국 주식 전략 레이더]

1. 시장 핵심 요약
- 오늘 시장에서 가장 중요한 변수 3개

2. TOP 10

각 종목:

티커:
기업명:
현재 가격:
현재 데이터 점수:

왜 주목하는가:
최신 뉴스/재료:
상승 촉매:
급락 위험:
현재 구간:
단기 전망:

반등 가능성:
낮음 / 보통 / 높음

급등 위험:
낮음 / 보통 / 높음

확신도:
1~10

3. 오늘의 TOP 3

가장 중요한 종목 3개만 선정하십시오.

각 종목마다:

- 핵심 이유
- 상승 촉매
- 위험요인
- 확인해야 할 가격/거래량 조건

4. 소형주 레이더

오늘 TOP 10 중
소형주 가운데 특별히 관찰할 종목이 있다면
최대 3개를 선정하십시오.

단순히 많이 오른 종목이 아니라
추가 상승 가능성과 위험을 함께 평가하십시오.

5. 급락 경고

현재 이미 과열되어 있거나
악재 가능성이 높은 종목을 표시하십시오.

6. 최종 결론

오늘 장에서

공격적 접근:
중립적 접근:
방어적 접근:

으로 나누어 간단하게 정리하십시오.

==============================

중요:

'성공 확률 90%' 같은 확정적인 표현을 하지 마십시오.

확률을 제시할 경우 반드시
'모델 추정치'라고 명시하십시오.

뉴스가 확인되지 않는 경우
'확인되지 않음'이라고 명시하십시오.
"""


    payload = {
        "model": GEMINI_MODEL,

        "input": user_prompt,

        "system_instruction": system_instruction,

        "tools": [
            {
                "type": "google_search"
            }
        ]
    }


    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60
        )

        print(
            "Gemini status:",
            response.status_code
        )

        result = response.json()

        if response.status_code != 200:

            error = (
                result
                .get("error", {})
                .get("message", str(result))
            )

            return None, (
                f"Gemini 오류 "
                f"{response.status_code}: "
                f"{error}"
            )


        # Interactions API 응답에서 output_text 탐색

        if result.get("output_text"):

            return (
                result["output_text"],
                None
            )


        # output 배열 탐색

        output = result.get(
            "output",
            []
        )

        texts = []

        for item in output:

            if not isinstance(item, dict):
                continue

            # text 직접 존재
            if item.get("text"):
                texts.append(
                    item["text"]
                )

            # content 내부
            content = item.get(
                "content",
                []
            )

            if isinstance(content, list):

                for c in content:

                    if isinstance(c, dict):

                        if c.get("text"):
                            texts.append(
                                c["text"]
                            )


        if texts:

            return (
                "\n".join(texts),
                None
            )


        return None, (
            "Gemini 응답은 성공했지만 "
            "텍스트를 찾지 못했습니다."
        )


    except Exception as e:

        return None, (
            f"Gemini 요청 오류: {e}"
        )


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
        "https://api.telegram.org/"
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
            timeout=20
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

    print(
        "================================"
    )

    print(
        "미국 주식 전략 레이더 시작"
    )

    print(
        get_kst()
    )

    print(
        "Gemini:",
        GEMINI_MODEL
    )

    print(
        "================================"
    )


    market_data = []


    # 시장 데이터 수집

    for ticker in TICKERS:

        print(
            f"{ticker} 수집 중..."
        )

        data = get_market_data(
            ticker
        )

        if data:

            data["score"] = (
                calculate_score(data)
            )

            data["status"] = (
                get_status(
                    data,
                    data["score"]
                )
            )

            data["type"] = (
                get_company_type(
                    ticker
                )
            )

            market_data.append(data)

        time.sleep(0.5)


    # 시장 데이터 자체가 없으면 종료

    if not market_data:

        message = f"""
🚨 미국 주식 전략 레이더

⏰ {get_kst()}

❌ 시장 데이터 수집 실패

Yahoo Finance에서 데이터를
가져오지 못했습니다.

이번 실행에서는
가짜 주가나 종목을 생성하지 않습니다.

다음 실행에서 다시 시도합니다.
"""

        send_telegram(message)

        return


    # 점수순

    market_data.sort(
        key=lambda x: x["score"],
        reverse=True
    )


    top10 = market_data[:10]


    # Gemini 입력용 데이터

    report = []

    for i, d in enumerate(
        top10,
        1
    ):

        report.append(
            f"""
{i}. {d['ticker']} ({d['name']})
가격: ${d['price']:.2f}
일간: {d['daily']:+.2f}%
주간: {d['weekly']:+.2f}%
거래량: {d['volume_ratio']:.2f}배
데이터 점수: {d['score']}/100
상태: {d['status']}
유형: {d['type']}
"""
        )


    report_data = "\n".join(
        report
    )


    # Gemini

    print(
        "Gemini 최신정보 검색/분석 중..."
    )

    ai_report, gemini_error = (
        call_gemini(
            report_data
        )
    )


    # ========================================================
    # Telegram 메시지
    # ========================================================

    message = f"""
🚨 미국 주식 전략 레이더

⏰ {get_kst()}

━━━━━━━━━━━━━━━━━━
📊 실제 시장 데이터 TOP 10
━━━━━━━━━━━━━━━━━━
"""


    for i, d in enumerate(
        top10,
        1
    ):

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
🤖 Gemini 최신정보 교차검증
━━━━━━━━━━━━━━━━━━
"""


    if ai_report:

        message += ai_report

    else:

        message += """
⚠️ Gemini 분석 실패

시장 데이터 수집은 정상적으로
완료되었습니다.

하지만 Gemini 최신정보 교차검증은
완료되지 않았습니다.

확인되지 않은 뉴스나
급등/급락 확률은 생성하지 않습니다.

"""

        if gemini_error:

            message += f"""
오류:
{gemini_error}
"""


    message += """

━━━━━━━━━━━━━━━━━━
⚠️ 투자 주의
━━━━━━━━━━━━━━━━━━

이 프로그램은 시장 데이터를 이용해
관심 종목을 자동 선별하는 분석 도구입니다.

AI 분석과 데이터 점수는
수익을 보장하지 않습니다.

특히 소형주와 급등주는
높은 변동성과 손실 위험이 있습니다.

최종 투자 판단은 별도의 공시,
실적, 재무정보 및 시장상황을
확인한 후 결정해야 합니다.
"""


    send_telegram(message)


    print(
        "================================"
    )

    print(
        "분석 완료"
    )

    print(
        "================================"
    )


if __name__ == "__main__":

    main()
