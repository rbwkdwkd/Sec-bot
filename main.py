import os
import time
import requests
from datetime import datetime
import yfinance as yf

# ============================================================
# 환경변수
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# 현재 사용 가능한 Gemini 모델
# 2.0-flash 대신 2.5-flash 사용
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
).strip()


# ============================================================
# 한국 주식 후보군
#
# 대형 / 중형 / 소형을 섞어서 검색
# ============================================================

STOCKS = {
    # -------------------------
    # 대형주
    # -------------------------
    "005930.KS": {
        "name": "삼성전자",
        "code": "005930",
        "type": "대형주",
        "sector": "반도체"
    },

    "000660.KS": {
        "name": "SK하이닉스",
        "code": "000660",
        "type": "대형주",
        "sector": "HBM/반도체"
    },

    "373220.KS": {
        "name": "LG에너지솔루션",
        "code": "373220",
        "type": "대형주",
        "sector": "2차전지"
    },

    "207940.KS": {
        "name": "삼성바이오로직스",
        "code": "207940",
        "type": "대형주",
        "sector": "바이오"
    },

    "005380.KS": {
        "name": "현대차",
        "code": "005380",
        "type": "대형주",
        "sector": "자동차"
    },

    "035420.KS": {
        "name": "NAVER",
        "code": "035420",
        "type": "대형주",
        "sector": "인터넷"
    },

    "012330.KS": {
        "name": "현대모비스",
        "code": "012330",
        "type": "대형주",
        "sector": "자동차부품"
    },

    "068270.KS": {
        "name": "셀트리온",
        "code": "068270",
        "type": "대형주",
        "sector": "바이오"
    },

    # -------------------------
    # 중형주
    # -------------------------

    "403870.KQ": {
        "name": "HPSP",
        "code": "403870",
        "type": "중형주",
        "sector": "반도체 장비"
    },

    "066970.KQ": {
        "name": "엘앤에프",
        "code": "066970",
        "type": "중형주",
        "sector": "2차전지"
    },

    "272210.KS": {
        "name": "한화시스템",
        "code": "272210",
        "type": "중형주",
        "sector": "방산"
    },

    "108490.KQ": {
        "name": "로보티즈",
        "code": "108490",
        "type": "중형주",
        "sector": "로봇"
    },

    "079550.KS": {
        "name": "LIG넥스원",
        "code": "079550",
        "type": "중형주",
        "sector": "방산"
    },

    "298040.KS": {
        "name": "효성중공업",
        "code": "298040",
        "type": "중형주",
        "sector": "전력기기"
    },

    "047810.KS": {
        "name": "한국항공우주",
        "code": "047810",
        "type": "중형주",
        "sector": "방산"
    },

    # -------------------------
    # 소형주 / 성장주
    # -------------------------

    "095340.KQ": {
        "name": "ISC",
        "code": "095340",
        "type": "소형주",
        "sector": "반도체 부품"
    },

    "039030.KQ": {
        "name": "이오테크닉스",
        "code": "039030",
        "type": "소형주",
        "sector": "반도체 장비"
    },

    "058470.KQ": {
        "name": "리노공업",
        "code": "058470",
        "type": "소형주",
        "sector": "반도체 부품"
    },

    "196170.KQ": {
        "name": "알테오젠",
        "code": "196170",
        "type": "중형주",
        "sector": "바이오"
    },

    "141080.KQ": {
        "name": "레고켐바이오",
        "code": "141080",
        "type": "소형주",
        "sector": "바이오"
    },

    "950160.KQ": {
        "name": "코오롱티슈진",
        "code": "950160",
        "type": "소형주",
        "sector": "바이오"
    },

    "214150.KQ": {
        "name": "클래시스",
        "code": "214150",
        "type": "중형주",
        "sector": "의료기기"
    },

    "277810.KQ": {
        "name": "레인보우로보틱스",
        "code": "277810",
        "type": "중형주",
        "sector": "로봇"
    }
}


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

    except:
        return default


# ============================================================
# 시장 데이터 수집
# ============================================================

def get_stock_data():

    results = []

    for ticker, info in STOCKS.items():

        try:

            data = yf.download(
                ticker,
                period="1mo",
                interval="1d",
                progress=False,
                auto_adjust=False
            )

            if data is None or data.empty:
                continue

            # MultiIndex 처리
            if hasattr(data.columns, "levels"):
                try:
                    close = data["Close"]

                    if hasattr(close, "columns"):
                        close = close.iloc[:, 0]

                    volume = data["Volume"]

                    if hasattr(volume, "columns"):
                        volume = volume.iloc[:, 0]

                except:
                    continue

            else:
                close = data["Close"]
                volume = data["Volume"]

            close = close.dropna()
            volume = volume.dropna()

            if len(close) < 5:
                continue

            current = safe_float(close.iloc[-1])

            previous = safe_float(close.iloc[-2])

            week_price = safe_float(close.iloc[-6]) if len(close) >= 6 else previous

            avg_volume = safe_float(
                volume.iloc[-21:-1].mean()
            ) if len(volume) >= 21 else safe_float(
                volume.iloc[:-1].mean()
            )

            current_volume = safe_float(volume.iloc[-1])

            if previous != 0:
                daily_change = (
                    (current - previous)
                    / previous
                    * 100
                )
            else:
                daily_change = 0

            if week_price != 0:
                weekly_change = (
                    (current - week_price)
                    / week_price
                    * 100
                )
            else:
                weekly_change = 0

            if avg_volume > 0:
                volume_ratio = current_volume / avg_volume
            else:
                volume_ratio = 1

            results.append({
                "ticker": ticker,
                "name": info["name"],
                "code": info["code"],
                "type": info["type"],
                "sector": info["sector"],
                "price": current,
                "daily": daily_change,
                "weekly": weekly_change,
                "volume_ratio": volume_ratio
            })

        except Exception as e:

            print(
                f"{info['name']} 데이터 오류: {e}"
            )

    return results


# ============================================================
# 데이터 점수 계산
#
# AI가 만든 점수가 아니라
# 실제 가격/거래량 계산값
# ============================================================

def calculate_score(stock):

    daily = stock["daily"]
    weekly = stock["weekly"]
    volume = stock["volume_ratio"]

    score = 50.0

    # 일간 상승 모멘텀
    if daily >= 10:
        score += 20
    elif daily >= 5:
        score += 12
    elif daily >= 3:
        score += 7
    elif daily >= 0:
        score += 3
    elif daily <= -10:
        score -= 15
    elif daily <= -5:
        score -= 10

    # 주간 모멘텀
    if weekly >= 20:
        score += 15
    elif weekly >= 10:
        score += 10
    elif weekly >= 5:
        score += 6
    elif weekly < -10:
        score -= 10

    # 거래량
    if volume >= 3:
        score += 15
    elif volume >= 2:
        score += 12
    elif volume >= 1.5:
        score += 8
    elif volume >= 1.2:
        score += 4
    elif volume < 0.7:
        score -= 5

    score = max(0, min(100, score))

    return round(score, 1)


# ============================================================
# 상태 판정
# ============================================================

def get_status(stock, score):

    daily = stock["daily"]
    volume = stock["volume_ratio"]

    # 너무 많이 오른 경우
    if daily >= 20:
        return "⚠️ 과열주의"

    # 강한 거래량 + 상승
    if score >= 80 and volume >= 2:
        return "🚀 급등 관심"

    if score >= 70:
        return "🔥 강한 관심"

    if score >= 60:
        return "🔄 반등 관심"

    return "🔎 관찰"


# ============================================================
# TOP 10 선정
# ============================================================

def select_top10(data):

    for stock in data:

        stock["score"] = calculate_score(stock)

        stock["status"] = get_status(
            stock,
            stock["score"]
        )

    data.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return data[:10]


# ============================================================
# Gemini AI 분석
# ============================================================

def ask_gemini(top10):

    if not GEMINI_API_KEY:

        return (
            "⚠️ Gemini API 키가 설정되지 않았습니다.\n\n"
            "시장 데이터 기반 레이더는 정상적으로 작동합니다."
        )

    market_text = ""

    for i, stock in enumerate(top10, 1):

        market_text += f"""
{i}. {stock['name']} ({stock['code']})
현재가: {stock['price']:.2f}
일간: {stock['daily']:+.2f}%
주간: {stock['weekly']:+.2f}%
거래량: {stock['volume_ratio']:.2f}배
데이터 점수: {stock['score']}/100
유형: {stock['type']}
섹터: {stock['sector']}
"""

    prompt = f"""
당신은 한국 주식시장을 분석하는 시니어 전략 분석가입니다.

아래는 실제 시장 데이터로 계산된 한국 주식 TOP 10입니다.

{market_text}

중요:
- 확인되지 않은 뉴스나 공시를 만들어내지 마세요.
- 실제로 제공된 데이터와 일반적인 시장 해석을 구분하세요.
- 특정 종목의 상승을 보장한다고 말하지 마세요.
- "성공확률"을 실제 통계처럼 꾸며서 제시하지 마세요.
- 대신 "상승 시나리오", "하락 위험", "확인할 조건"을 제시하세요.
- 급등한 종목은 추격매수 위험을 반드시 평가하세요.
- 소형주도 분석하되 유동성과 변동성 위험을 강조하세요.

특히 다음을 분석하세요.

1. 오늘 TOP 10 중 가장 강한 모멘텀 3개
2. 단기 반등 후보 3개
3. 급등 추격매수 주의 종목
4. 대형주 / 중형주 / 소형주 중 어떤 쪽이 유리한지
5. 반도체 / 방산 / 로봇 / 바이오 / 2차전지 등 강한 섹터
6. 오늘 장에서 확인해야 할 조건
7. 급락 위험이 높은 상황
8. 내일도 관심을 유지할 종목 3개

출력은 텔레그램에 바로 보낼 수 있도록 간결하게 작성하세요.

형식:

🤖 AI 시니어 전략 분석

🔥 오늘의 핵심
- ...

🎯 단기 모멘텀 TOP 3
1. 종목:
   이유:
   확인조건:

2. ...

🔄 반등 후보 TOP 3
1. 종목:
   이유:
   반등 조건:

⚠️ 급락/추격매수 주의
- ...

🏭 강한 섹터
- ...

📌 내일 관심
- ...

⚠️ 반드시 확인
- 실적
- 공시
- 거래량
- 시장지수
- 외국인/기관 수급

마지막에 다음 문장을 포함하세요.

"본 분석은 투자 참고용이며 수익을 보장하지 않습니다."
"""

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
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
            "maxOutputTokens": 1800
        }
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=30
        )

        try:
            result = response.json()
        except:
            result = {}

        if response.status_code == 200:

            candidates = result.get(
                "candidates",
                []
            )

            if candidates:

                parts = candidates[0].get(
                    "content",
                    {}
                ).get(
                    "parts",
                    []
                )

                if parts:

                    return parts[0].get(
                        "text",
                        ""
                    )

            return (
                "⚠️ Gemini 응답 내용이 없습니다."
            )

        # 429
        if response.status_code == 429:

            return (
                "⚠️ Gemini 사용량 제한\n\n"
                "현재 Gemini API의 RPM/TPM/RPD "
                "또는 프로젝트 quota를 초과했습니다.\n\n"
                "시장 데이터 TOP 10은 정상적으로 "
                "수집되었으며 AI 분석만 다음 실행으로 "
                "넘어갑니다."
            )

        # 404
        if response.status_code == 404:

            return (
                "⚠️ Gemini 모델 연결 오류\n\n"
                f"현재 모델: {GEMINI_MODEL}\n\n"
                "Google AI Studio에서 현재 프로젝트가 "
                "사용 가능한 모델인지 확인하세요."
            )

        error = result.get(
            "error",
            {}
        ).get(
            "message",
            "알 수 없는 오류"
        )

        return (
            f"⚠️ Gemini API 오류\n\n"
            f"{error}"
        )

    except requests.exceptions.Timeout:

        return (
            "⚠️ Gemini 응답 시간 초과\n\n"
            "시장 데이터 분석은 정상적으로 완료되었습니다."
        )

    except Exception as e:

        return (
            "⚠️ Gemini 연결 실패\n\n"
            f"{str(e)[:500]}"
        )


# ============================================================
# 텔레그램 전송
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
# 메시지 작성
# ============================================================

def build_message(top10, ai_text):

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    text = f"""
🚨 한국 주식 전략 레이더

⏰ {now} KST

━━━━━━━━━━━━━━━━━━
🇰🇷 KOSPI / KOSDAQ TOP 10
━━━━━━━━━━━━━━━━━━
"""

    for i, stock in enumerate(top10, 1):

        text += f"""
{i}️⃣ {stock['name']}
({stock['code']})

💵 현재가: {stock['price']:,.0f}원
📈 일간: {stock['daily']:+.2f}%
📊 주간: {stock['weekly']:+.2f}%
🔥 거래량: {stock['volume_ratio']:.2f}배

⭐ 데이터 점수: {stock['score']}/100
📌 상태: {stock['status']}
🏷 유형: {stock['type']}
🏭 섹터: {stock['sector']}

"""

    text += """
━━━━━━━━━━━━━━━━━━
🤖 AI 시니어 전략 분석
━━━━━━━━━━━━━━━━━━

"""

    text += ai_text

    text += """

━━━━━━━━━━━━━━━━━━
⚠️ 투자 주의
━━━━━━━━━━━━━━━━━━

본 프로그램은 실제 시장 가격/거래량을
기반으로 관심 종목을 자동 선별합니다.

데이터 점수와 AI 분석은
주가 상승을 보장하는 확률이 아닙니다.

특히 급등주와 소형주는
변동성과 손실 위험이 높습니다.

실적, 공시, 거래대금, 외국인/기관 수급,
시장지수 등을 반드시 추가 확인하세요.

본 분석은 투자 참고용이며
수익을 보장하지 않습니다.
"""

    return text


# ============================================================
# 메인
# ============================================================

def main():

    print("================================")
    print("한국 주식 전략 레이더 시작")
    print("================================")

    print("1. 한국 시장 데이터 수집 중...")

    data = get_stock_data()

    if not data:

        send_telegram(
            "🚨 한국 주식 전략 레이더\n\n"
            "시장 데이터를 수집하지 못했습니다.\n\n"
            "다음 실행 주기에 다시 시도합니다."
        )

        return

    print(
        f"시장 데이터 {len(data)}개 수집 완료"
    )

    print("2. TOP 10 계산 중...")

    top10 = select_top10(data)

    if not top10:

        send_telegram(
            "🚨 한국 주식 전략 레이더\n\n"
            "분석 가능한 종목이 없습니다."
        )

        return

    print("3. Gemini AI 분석 요청...")

    ai_text = ask_gemini(top10)

    print("4. Telegram 전송...")

    message = build_message(
        top10,
        ai_text
    )

    success = send_telegram(message)

    if success:
        print("5. 전송 성공!")
    else:
        print("5. 전송 실패")


if __name__ == "__main__":
    main()
