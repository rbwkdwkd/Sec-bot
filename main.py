import os
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests
import yfinance as yf


# =========================================================
# 🇰🇷 한국 주식 전략 레이더
# =========================================================

KST = timezone(timedelta(hours=9))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ---------------------------------------------------------
# 한국 주요 관심종목
# ---------------------------------------------------------
STOCKS = {
    "005930": {
        "name": "삼성전자",
        "sector": "반도체",
        "type": "대형주",
        "market": "KS",
    },
    "000660": {
        "name": "SK하이닉스",
        "sector": "HBM/반도체",
        "type": "대형주",
        "market": "KS",
    },
    "035420": {
        "name": "NAVER",
        "sector": "인터넷",
        "type": "대형주",
        "market": "KS",
    },
    "272210": {
        "name": "한화시스템",
        "sector": "방산",
        "type": "중형주",
        "market": "KS",
    },
    "079550": {
        "name": "LIG넥스원",
        "sector": "방산",
        "type": "대형주",
        "market": "KS",
    },
    "047810": {
        "name": "한국항공우주",
        "sector": "방산",
        "type": "대형주",
        "market": "KS",
    },
    "298040": {
        "name": "효성중공업",
        "sector": "전력기기",
        "type": "대형주",
        "market": "KS",
    },
    "403870": {
        "name": "HPSP",
        "sector": "반도체 장비",
        "type": "중형주",
        "market": "KQ",
    },
    "095340": {
        "name": "ISC",
        "sector": "반도체 부품",
        "type": "중소형주",
        "market": "KQ",
    },
    "108490": {
        "name": "로보티즈",
        "sector": "로봇",
        "type": "중형주",
        "market": "KQ",
    },
    "950160": {
        "name": "코오롱티슈진",
        "sector": "바이오",
        "type": "소형주",
        "market": "KQ",
    },
    "066970": {
        "name": "엘앤에프",
        "sector": "2차전지",
        "type": "중형주",
        "market": "KS",
    },
    "036540": {
        "name": "SFA반도체",
        "sector": "반도체",
        "type": "중소형주",
        "market": "KQ",
    },
    "042700": {
        "name": "한미반도체",
        "sector": "반도체 장비",
        "type": "대형주",
        "market": "KS",
    },
    "247540": {
        "name": "에코프로비엠",
        "sector": "2차전지",
        "type": "대형주",
        "market": "KQ",
    },
    "086520": {
        "name": "에코프로",
        "sector": "2차전지",
        "type": "대형주",
        "market": "KQ",
    },
    "196170": {
        "name": "알테오젠",
        "sector": "바이오",
        "type": "대형주",
        "market": "KQ",
    },
    "141080": {
        "name": "리가켐바이오",
        "sector": "바이오",
        "type": "중형주",
        "market": "KQ",
    },
    "012450": {
        "name": "한화에어로스페이스",
        "sector": "방산",
        "type": "대형주",
        "market": "KS",
    },
    "042660": {
        "name": "한화오션",
        "sector": "조선",
        "type": "대형주",
        "market": "KS",
    },
    "010130": {
        "name": "고려아연",
        "sector": "금속",
        "type": "대형주",
        "market": "KS",
    },
    "034730": {
        "name": "SK",
        "sector": "지주",
        "type": "대형주",
        "market": "KS",
    },
}


# =========================================================
# Yahoo Finance 조회
# =========================================================

def get_stock_data(code, info):

    market = info["market"]

    # 정상 거래소부터 시도
    tickers = [
        f"{code}.{market}"
    ]

    # 혹시 거래소가 바뀐 경우 반대 시장도 시도
    opposite = "KQ" if market == "KS" else "KS"
    tickers.append(f"{code}.{opposite}")

    for ticker in tickers:

        try:

            data = yf.download(
                ticker,
                period="1mo",
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False
            )

            if data is None or data.empty:
                continue

            # MultiIndex 대응
            if isinstance(data.columns, pd.MultiIndex):
                close = data["Close"].iloc[:, 0]
                volume = data["Volume"].iloc[:, 0]
            else:
                close = data["Close"]
                volume = data["Volume"]

            close = pd.to_numeric(close, errors="coerce").dropna()
            volume = pd.to_numeric(volume, errors="coerce").dropna()

            if len(close) < 5:
                continue

            current = float(close.iloc[-1])

            # 전일 대비
            if len(close) >= 2:
                daily = ((current / float(close.iloc[-2])) - 1) * 100
            else:
                daily = 0

            # 5거래일 기준
            if len(close) >= 6:
                weekly = ((current / float(close.iloc[-6])) - 1) * 100
            else:
                weekly = 0

            # 거래량 평균
            if len(volume) >= 21:
                avg_volume = float(volume.iloc[-21:-1].mean())
            else:
                avg_volume = float(volume.iloc[:-1].mean())

            today_volume = float(volume.iloc[-1])

            if avg_volume > 0:
                volume_ratio = today_volume / avg_volume
            else:
                volume_ratio = 1.0

            return {
                "code": code,
                "name": info["name"],
                "sector": info["sector"],
                "type": info["type"],
                "market": market,
                "ticker": ticker,
                "price": current,
                "daily": daily,
                "weekly": weekly,
                "volume_ratio": volume_ratio,
            }

        except Exception as e:
            print(f"{ticker} 조회 실패: {e}")

    print(f"{code} {info['name']} 데이터 조회 실패")
    return None


# =========================================================
# 데이터 점수
# =========================================================

def calculate_score(stock):

    daily = stock["daily"]
    weekly = stock["weekly"]
    volume = stock["volume_ratio"]

    score = 50.0

    # 일간 상승
    if daily >= 10:
        score += 20
    elif daily >= 5:
        score += 15
    elif daily >= 3:
        score += 10
    elif daily >= 1:
        score += 5
    elif daily < -5:
        score -= 10
    elif daily < -10:
        score -= 15

    # 주간 상승
    if weekly >= 20:
        score += 15
    elif weekly >= 10:
        score += 10
    elif weekly >= 5:
        score += 5
    elif weekly < -10:
        score -= 10

    # 거래량
    if volume >= 3:
        score += 15
    elif volume >= 2:
        score += 10
    elif volume >= 1.5:
        score += 7
    elif volume >= 1.2:
        score += 4
    elif volume < 0.7:
        score -= 5

    score = max(0, min(100, score))

    return round(score, 1)


# =========================================================
# 상태
# =========================================================

def get_status(stock, score):

    daily = stock["daily"]
    weekly = stock["weekly"]
    volume = stock["volume_ratio"]

    # 과열
    if daily >= 15 and volume >= 2:
        return "⚠️ 과열주의"

    if score >= 80:
        return "🚀 급등 관심"

    if score >= 70:
        return "🔥 강한 관심"

    if score >= 60:
        return "🔄 반등 관심"

    return "🔎 관찰"


# =========================================================
# Gemini AI
# =========================================================

def run_gemini_analysis(stocks):

    if not GEMINI_API_KEY:
        return (
            "⚠️ Gemini API 키가 설정되지 않았습니다.\n\n"
            "시장 데이터 분석은 정상적으로 완료되었습니다."
        )

    try:

        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)

        stock_text = ""

        for i, s in enumerate(stocks, 1):
            stock_text += (
                f"{i}. {s['name']} ({s['code']})\n"
                f"현재가: {s['price']:,.0f}원\n"
                f"일간: {s['daily']:+.2f}%\n"
                f"주간: {s['weekly']:+.2f}%\n"
                f"거래량: {s['volume_ratio']:.2f}배\n"
                f"데이터 점수: {s['score']}/100\n"
                f"섹터: {s['sector']}\n\n"
            )

        prompt = f"""
너는 한국 주식 시장을 분석하는 시니어 전략 분석가다.

아래는 실제 시장 데이터로 계산된 TOP 10 종목이다.

{stock_text}

다음 원칙을 반드시 지켜라.

1. 제공된 가격/거래량/점수를 임의로 수정하지 않는다.
2. 확인하지 않은 뉴스나 공시를 만들어내지 않는다.
3. 주가 상승 확률을 숫자로 임의 생성하지 않는다.
4. 특정 종목의 매수/매도를 단정하지 않는다.
5. 각 종목의 강점과 위험요인을 간단하게 설명한다.
6. 가능하면 최근 뉴스/공시를 Google Search로 확인한다.
7. 최근 뉴스가 확인되지 않으면 "확인되지 않음"이라고 표시한다.
8. 투자자에게 가장 중요한 리스크를 우선적으로 설명한다.

답변 형식:

🤖 AI 시니어 전략 분석

🥇 1위 종목
- 강점:
- 위험:
- 체크할 뉴스/공시:

🥈 2위 종목
- 강점:
- 위험:
- 체크할 뉴스/공시:

🥉 3위 종목
- 강점:
- 위험:
- 체크할 뉴스/공시:

📌 전체 시장 관찰
- 현재 강한 섹터:
- 주의할 섹터:
- 가장 중요한 리스크:

마지막에 반드시:

"※ 본 분석은 투자 참고용이며 수익을 보장하지 않습니다."
"""

        # 최신 모델부터 시도
        models = [
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
        ]

        last_error = None

        for model in models:

            try:

                print(f"Gemini 모델 시도: {model}")

                interaction = client.interactions.create(
                    model=model,
                    input=prompt,
                    tools=[
                        {"type": "google_search"}
                    ]
                )

                result = interaction.output_text

                if result and result.strip():

                    print(f"Gemini 성공: {model}")

                    return (
                        f"모델: {model}\n\n"
                        + result.strip()
                    )

            except Exception as e:

                last_error = str(e)

                print(f"Gemini {model} 실패: {e}")

                # 429는 모델을 바꿔도 quota 문제일 가능성이 높음
                if "429" in str(e) or "quota" in str(e).lower():

                    return (
                        "⚠️ Gemini API 사용량 제한\n\n"
                        "시장 데이터 수집은 정상적으로 완료되었습니다.\n\n"
                        "하지만 Gemini API quota/rate limit에 "
                        "도달하여 AI 최신정보 분석을 실행하지 않았습니다.\n\n"
                        "※ API 오류 상태에서는 뉴스, 확률, "
                        "추천 점수를 임의로 생성하지 않습니다."
                    )

                time.sleep(1)

        return (
            "⚠️ Gemini 모델 연결 실패\n\n"
            "시장 데이터 분석은 정상적으로 완료되었습니다.\n\n"
            "현재 사용 가능한 Gemini 모델을 확인하지 못했습니다.\n\n"
            f"마지막 오류: {last_error}"
        )

    except Exception as e:

        return (
            "⚠️ Gemini 분석 실행 실패\n\n"
            "시장 데이터 분석은 정상적으로 완료되었습니다.\n\n"
            "AI가 확인하지 못한 정보는 임의로 생성하지 않았습니다.\n\n"
            f"오류: {e}"
        )


# =========================================================
# 텔레그램
# =========================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram 설정 없음")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=30
        )

        print("Telegram:", response.status_code)

        return response.ok

    except Exception as e:

        print("Telegram 오류:", e)

        return False


# =========================================================
# 메시지 생성
# =========================================================

def make_message(stocks, ai_text):

    now = datetime.now(KST)

    msg = []

    msg.append("🚨 한국 주식 전략 레이더")
    msg.append("")
    msg.append(
        f"⏰ {now.strftime('%Y-%m-%d %H:%M:%S')} KST"
    )

    msg.append("")
    msg.append("━━━━━━━━━━━━━━━━━━")
    msg.append("🇰🇷 KOSPI / KOSDAQ TOP 10")
    msg.append("━━━━━━━━━━━━━━━━━━")

    for i, s in enumerate(stocks[:10], 1):

        msg.append("")
        msg.append(
            f"{i}️⃣ {s['name']}"
        )

        msg.append(
            f"({s['code']})"
        )

        msg.append("")
        msg.append(
            f"💵 현재가: {s['price']:,.0f}원"
        )

        msg.append(
            f"📈 일간: {s['daily']:+.2f}%"
        )

        msg.append(
            f"📊 주간: {s['weekly']:+.2f}%"
        )

        msg.append(
            f"🔥 거래량: {s['volume_ratio']:.2f}배"
        )

        msg.append("")
        msg.append(
            f"⭐ 데이터 점수: {s['score']}/100"
        )

        msg.append(
            f"📌 상태: {s['status']}"
        )

        msg.append(
            f"🏷 유형: {s['type']}"
        )

        msg.append(
            f"🏭 섹터: {s['sector']}"
        )

    msg.append("")
    msg.append("━━━━━━━━━━━━━━━━━━")
    msg.append("🤖 AI 시니어 전략 분석")
    msg.append("━━━━━━━━━━━━━━━━━━")

    msg.append("")
    msg.append(ai_text)

    msg.append("")
    msg.append("━━━━━━━━━━━━━━━━━━")
    msg.append("⚠️ 투자 주의")
    msg.append("━━━━━━━━━━━━━━━━━━")

    msg.append("")
    msg.append(
        "본 프로그램은 실제 시장 가격/거래량을"
    )
    msg.append(
        "기반으로 관심 종목을 자동 선별합니다."
    )

    msg.append("")
    msg.append(
        "데이터 점수와 AI 분석은"
    )
    msg.append(
        "주가 상승을 보장하는 확률이 아닙니다."
    )

    msg.append("")
    msg.append(
        "특히 급등주와 소형주는"
    )
    msg.append(
        "변동성과 손실 위험이 높습니다."
    )

    msg.append("")
    msg.append(
        "AI가 확인하지 못한 뉴스나 공시는"
    )
    msg.append(
        "임의로 생성하지 않습니다."
    )

    msg.append("")
    msg.append(
        "투자 전 실적, 공시, 거래대금,"
    )
    msg.append(
        "외국인/기관 수급 및 시장 상황을"
    )
    msg.append(
        "추가 확인하세요."
    )

    msg.append("")
    msg.append(
        "※ 본 분석은 투자 참고용이며 "
        "수익을 보장하지 않습니다."
    )

    return "\n".join(msg)


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 40)
    print("한국 주식 전략 레이더 시작")
    print("=" * 40)

    results = []

    print("1. 한국 시장 데이터 수집 중...")

    for code, info in STOCKS.items():

        data = get_stock_data(code, info)

        if data:

            data["score"] = calculate_score(data)
            data["status"] = get_status(
                data,
                data["score"]
            )

            results.append(data)

        time.sleep(0.15)

    print(
        f"시장 데이터 {len(results)}개 수집 완료"
    )

    if not results:

        error_message = (
            "🚨 한국 주식 전략 레이더\n\n"
            "시장 데이터를 수집하지 못했습니다.\n\n"
            "다음 실행 주기에 다시 시도합니다."
        )

        send_telegram(error_message)

        return

    # 점수순 정렬
    results.sort(
        key=lambda x: (
            x["score"],
            x["daily"],
            x["weekly"]
        ),
        reverse=True
    )

    top10 = results[:10]

    print("2. TOP 10 계산 완료")

    for i, s in enumerate(top10, 1):

        print(
            f"{i}. {s['name']} "
            f"{s['score']}점 "
            f"{s['daily']:+.2f}%"
        )

    print("3. Gemini AI 분석 요청...")

    ai_text = run_gemini_analysis(top10)

    print("4. Telegram 전송...")

    message = make_message(
        top10,
        ai_text
    )

    success = send_telegram(message)

    if success:
        print("5. 전송 성공!")
    else:
        print("5. Telegram 전송 실패")


if __name__ == "__main__":
    main()
