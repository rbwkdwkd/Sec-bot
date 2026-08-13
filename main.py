import os
import json
import time
import math
import requests
from datetime import datetime, timezone, timedelta
from urllib.parse import quote


# ============================================================
# 미국 주식 전략 레이더
# ============================================================
#
# 기능
# 1. Yahoo Finance 가격/거래량 자동 수집
# 2. query1 -> query2 자동 fallback
# 3. 시장 데이터 오류가 일부 발생해도 전체 프로그램 중단 방지
# 4. 대형주 + 중형주 + 소형주 후보군
# 5. 가격/거래량/모멘텀 기반 1차 점수
# 6. Gemini 최신 AI 분석
# 7. AI 실패 시에도 실제 시장 데이터 기반 결과 전송
# 8. GitHub/Google Trends 분석 아이디어를 AI 분석 규칙에 반영
# 9. TOP 10 종목 선정
# 10. 텔레그램 전송
#
# 주의:
# 이 프로그램은 투자자문/매매자동화가 아니라
# 정보 분석 및 후보 탐색용이다.
# ============================================================


# ============================================================
# 환경변수
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


# ============================================================
# 설정
# ============================================================

KST = timezone(timedelta(hours=9))

# Gemini 최신 모델
# 문제가 발생하면 아래 순서대로 자동 fallback
GEMINI_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
]

# Yahoo Finance 서버 fallback
YAHOO_HOSTS = [
    "query1.finance.yahoo.com",
    "query2.finance.yahoo.com",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# ============================================================
# 후보군
# ============================================================
#
# 대형주 + 중형주 + 소형주를 섞는다.
#
# 지나치게 많은 종목을 한꺼번에 조회하면 Yahoo rate limit에
# 걸릴 가능성이 있기 때문에 적절한 후보군으로 제한한다.
# ============================================================

STOCKS = {

    # ----------------------------
    # AI / 반도체 대형
    # ----------------------------
    "NVDA": "AI 반도체",
    "AMD": "AI 반도체",
    "AVGO": "AI 네트워크/반도체",
    "TSM": "파운드리",
    "ASML": "반도체 장비",
    "AMAT": "반도체 장비",
    "LRCX": "반도체 장비",
    "MU": "메모리/HBM",
    "INTC": "반도체",

    # ----------------------------
    # AI / 데이터센터
    # ----------------------------
    "CRWV": "AI 데이터센터",
    "NBIS": "AI 데이터센터",
    "IREN": "AI 데이터센터/채굴",
    "SMCI": "AI 서버",
    "ANET": "AI 네트워크",

    # ----------------------------
    # 성장주
    # ----------------------------
    "PLTR": "AI 소프트웨어",
    "TEM": "AI 헬스케어",
    "APP": "AI/광고",
    "ARM": "반도체 설계",
    "RDDT": "플랫폼",
    "HOOD": "핀테크",
    "SOFI": "핀테크",

    # ----------------------------
    # 우주/방산/신성장
    # ----------------------------
    "LUNR": "우주",
    "RKLB": "우주",
    "ASTS": "위성통신",
    "RDW": "우주",

    # ----------------------------
    # 고변동 성장주
    # ----------------------------
    "SOUN": "AI 음성",
    "BBAI": "AI",
    "AI": "AI 소프트웨어",
    "IONQ": "양자컴퓨팅",
    "RGTI": "양자컴퓨팅",
    "QBTS": "양자컴퓨팅",
    "HIMS": "디지털 헬스",
    "RKLB": "우주",

    # ----------------------------
    # 전기차/로봇
    # ----------------------------
    "TSLA": "전기차/AI",
    "RIVN": "전기차",
    "LCID": "전기차",
    "SERV": "로봇",
}


# 중복 제거
STOCKS = dict(STOCKS)


# ============================================================
# HTTP Session
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
})


# ============================================================
# 유틸
# ============================================================

def now_kst():
    return datetime.now(KST)


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def format_money(value):
    if value is None:
        return "N/A"

    try:
        value = float(value)

        if value >= 1000:
            return f"${value:,.2f}"

        return f"${value:.2f}"

    except Exception:
        return "N/A"


# ============================================================
# Yahoo Finance 데이터
# ============================================================

def yahoo_chart(symbol, range_value="5d", interval="1d"):
    """
    Yahoo Finance Chart API.

    query1 실패 -> query2 자동 fallback
    """

    encoded_symbol = quote(symbol, safe="")

    last_error = None

    for host in YAHOO_HOSTS:

        url = (
            f"https://{host}/v8/finance/chart/"
            f"{encoded_symbol}"
        )

        params = {
            "range": range_value,
            "interval": interval,
            "includePrePost": "true",
            "events": "div,splits",
        }

        try:

            response = session.get(
                url,
                params=params,
                timeout=15,
            )

            if response.status_code != 200:
                last_error = (
                    f"{host} HTTP {response.status_code}"
                )
                continue

            data = response.json()

            chart = data.get("chart", {})

            result = chart.get("result")

            if not result:
                error = chart.get("error")

                if error:
                    last_error = str(error)

                continue

            return result[0]

        except Exception as e:

            last_error = f"{host}: {e}"

            continue

    raise RuntimeError(
        f"{symbol} Yahoo 데이터 수집 실패: {last_error}"
    )


# ============================================================
# 종목 분석
# ============================================================

def analyze_stock(symbol, category):

    try:

        data = yahoo_chart(
            symbol,
            range_value="1mo",
            interval="1d",
        )

        meta = data.get("meta", {})

        price = safe_float(
            meta.get("regularMarketPrice")
        )

        if price <= 0:
            price = safe_float(
                meta.get("previousClose")
            )

        timestamps = data.get("timestamp", [])
        indicators = data.get(
            "indicators",
            {}
        )

        quote_data = (
            indicators
            .get("quote", [{}])[0]
        )

        closes = quote_data.get(
            "close",
            []
        )

        volumes = quote_data.get(
            "volume",
            []
        )

        closes = [
            safe_float(x)
            for x in closes
            if x is not None
        ]

        volumes = [
            safe_float(x)
            for x in volumes
            if x is not None
        ]

        if len(closes) < 2:

            return None

        previous_close = closes[-2]

        if previous_close <= 0:
            daily_change = 0
        else:
            daily_change = (
                (price - previous_close)
                / previous_close
            ) * 100

        # ----------------------------
        # 5일 변화
        # ----------------------------

        if len(closes) >= 6:

            old_5d = closes[-6]

            if old_5d > 0:

                weekly_change = (
                    (price - old_5d)
                    / old_5d
                ) * 100

            else:
                weekly_change = 0

        else:

            weekly_change = 0

        # ----------------------------
        # 거래량 배수
        # ----------------------------

        volume_ratio = 1.0

        if len(volumes) >= 6:

            recent_volume = volumes[-1]

            historical_volumes = volumes[-6:-1]

            valid_volumes = [
                x for x in historical_volumes
                if x > 0
            ]

            if valid_volumes:

                avg_volume = (
                    sum(valid_volumes)
                    / len(valid_volumes)
                )

                if avg_volume > 0:

                    volume_ratio = (
                        recent_volume
                        / avg_volume
                    )

        # ----------------------------
        # 20일 고점 대비
        # ----------------------------

        high_20 = max(closes[-20:])

        if high_20 > 0:

            drawdown_from_high = (
                (price - high_20)
                / high_20
            ) * 100

        else:

            drawdown_from_high = 0

        # ----------------------------
        # 기본 점수
        # ----------------------------

        score = 50.0

        # 거래량 증가
        if volume_ratio >= 3:
            score += 20

        elif volume_ratio >= 2:
            score += 15

        elif volume_ratio >= 1.5:
            score += 10

        elif volume_ratio >= 1.2:
            score += 5

        # 일간 상승
        if 3 <= daily_change <= 12:
            score += 10

        elif 1 <= daily_change < 3:
            score += 5

        # 주간 모멘텀
        if 5 <= weekly_change <= 20:
            score += 10

        elif weekly_change > 20:
            score += 5

        # 너무 과도하게 오른 종목은 감점
        if daily_change > 20:
            score -= 10

        if daily_change > 35:
            score -= 15

        # 고점 대비 조정 후 반등 가능성
        if -25 <= drawdown_from_high <= -5:
            score += 5

        # 거래량이 너무 낮으면 감점
        if volume_ratio < 0.7:
            score -= 5

        score = clamp(score, 0, 100)

        # ----------------------------
        # 상태
        # ----------------------------

        if score >= 80:
            status = "🔥 강한 관심"

        elif score >= 70:
            status = "🚀 급등 관심"

        elif score >= 60:
            status = "🔄 반등 관심"

        elif score >= 50:
            status = "🔎 관찰"

        else:
            status = "⚠️ 주의"

        return {
            "symbol": symbol,
            "category": category,
            "price": price,
            "daily_change": daily_change,
            "weekly_change": weekly_change,
            "volume_ratio": volume_ratio,
            "drawdown": drawdown_from_high,
            "score": score,
            "status": status,
        }

    except Exception as e:

        print(
            f"[시장데이터 오류] {symbol}: {e}"
        )

        return None


# ============================================================
# 시장 데이터 수집
# ============================================================

def collect_market_data():

    results = []

    failed = []

    print(
        f"[{now_kst().strftime('%Y-%m-%d %H:%M:%S')}] "
        "시장 데이터 수집 시작"
    )

    for symbol, category in STOCKS.items():

        result = analyze_stock(
            symbol,
            category
        )

        if result:

            results.append(result)

        else:

            failed.append(symbol)

        # Yahoo rate limit 방지
        time.sleep(0.15)

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
# 상위 10개 선정
# ============================================================

def select_top10(results):

    if not results:
        return []

    # 점수 우선
    sorted_results = sorted(
        results,
        key=lambda x: (
            x["score"],
            x["volume_ratio"],
            x["weekly_change"]
        ),
        reverse=True
    )

    return sorted_results[:10]


# ============================================================
# Gemini Prompt
# ============================================================

def build_gemini_prompt(top10):

    market_text = ""

    for i, item in enumerate(top10, 1):

        market_text += f"""
{i}.
종목: {item['symbol']}
분야: {item['category']}
현재가: {format_money(item['price'])}
일간 변화: {item['daily_change']:.2f}%
주간 변화: {item['weekly_change']:.2f}%
거래량 배수: {item['volume_ratio']:.2f}배
20일 고점 대비: {item['drawdown']:.2f}%
자동 데이터 점수: {item['score']:.1f}/100
"""


    prompt = f"""
당신은 미국 주식 시장을 분석하는
시니어 주식 전략 분석가다.

아래 종목은 실제 시장 데이터 수집 단계에서
확인된 후보들이다.

절대로 존재하지 않는 뉴스,
주가,
실적,
거래량,
공시,
기관 매수,
Google Trends,
GitHub 활동을 만들어내지 마라.

확인할 수 없는 정보는
반드시 "확인되지 않음"이라고 표시하라.

========================
분석 목표
========================

오늘 향후 24~48시간 동안
상대적으로 반등 가능성이 높은
미국 주식 TOP 10을 분석한다.

대형주뿐 아니라
중형주와 소형주도 평가한다.

단,
소형주라고 해서 무조건 높은 점수를 주지 마라.

========================
아이디어 1
========================

GitHub 개발활동 가속도와
Google 검색 관심도의 시간차 다이버전스를
분석 관점으로 사용한다.

실제 데이터가 제공되지 않았다면
추측하지 말고
"GitHub/Google Trends 검증 데이터 없음"이라고 표시한다.

========================
아이디어 2
========================

GitHub 보안 취약점,
exploit,
emergency,
unauthorized,
overflow,
rollback 등의 위험 신호가
실제로 확인되는 경우에만
급락 위험을 높인다.

확인되지 않은 경우
해당 내용을 만들어내지 마라.

========================
아이디어 3
========================

개발자 유입,
GitHub contributor,
star,
fork,
watch 증가 등의 신호가
실제 확인되는 경우에만 반영한다.

========================
아이디어 4
========================

인위적인 hype,
과도한 뉴스 노출,
실제 기술활동 부족 여부를 평가한다.

확인되지 않은 경우
판단 보류한다.

========================
아이디어 5
========================

개발팀 갈등,
fork,
abandon,
scam,
proposal rejected 등의
실제 위험 신호가 확인되는 경우
급락 위험을 높인다.

========================
아이디어 6
========================

신규 release,
업그레이드,
신제품,
상장,
실적,
파트너십 등의 촉매를 분석한다.

실제 확인된 자료가 없는 경우
추측하지 않는다.

========================
아이디어 7
========================

보안/코드 위험 신호가 실제로
확인되는 경우 급락 위험을 평가한다.

========================
아이디어 8
========================

개발자 이탈,
활동 감소,
프로젝트 ghosting을
실제 데이터가 있을 경우 평가한다.

========================
아이디어 9
========================

악재로 급락했지만
실제 문제가 해결되었거나
과매도 후 반등 조건이 발생한 경우
역발상 반등 후보로 평가한다.

========================
아이디어 10
========================

두 개의 가상 분석가를 활용한다.

Agent A:
기술적/개발활동/시장 데이터 관점

Agent B:
뉴스/대중심리/시장심리 관점

두 관점이 일치할 때
신뢰도를 높인다.

단,
실제 뉴스/Google Trends 데이터가
제공되지 않은 경우
그 부분을 사실처럼 표현하지 않는다.

========================
중요한 분석 원칙
========================

1. 가격 상승률만 보고 추천하지 않는다.

2. 거래량 증가와 가격 움직임을 함께 본다.

3. 이미 하루에 30~40% 이상 폭등한 종목은
추격매수 위험을 명확하게 표시한다.

4. 반등 가능성과 급등 가능성을 구분한다.

5. 소형주는 변동성이 높기 때문에
급락 위험도 함께 평가한다.

6. "성공확률"이라는 표현은
통계적으로 검증된 확률이 아니라
현재 데이터에 기반한
전략적 신뢰도 점수로 표현한다.

7. 데이터가 부족하면
"판단 보류"라고 한다.

8. 투자자에게 특정 가격에서
무조건 매수하라고 명령하지 않는다.

========================
출력 형식
========================

아래 형식을 반드시 따른다.

📊 미국 주식 전략 레이더

1️⃣ 종목명 / 티커
분야:
현재가:
일간:
주간:
거래량:
데이터 점수:

🔥 전략 판단:
[급등관심 / 반등관심 / 관찰 / 급락주의]

📈 반등 가능성:
[높음 / 중간 / 낮음]

⚠️ 급락 위험:
[높음 / 중간 / 낮음]

🎯 핵심 이유:
최대 2줄

🚀 상승 촉매:
확인된 내용만

⚠️ 위험 요인:
확인된 내용만

🔬 검증 상태:
[시장데이터 확인]
[뉴스 확인 여부]
[GitHub 확인 여부]
[Google Trends 확인 여부]

------------------------

마지막에

🏆 오늘의 TOP 3

1.
2.
3.

🔥 가장 공격적인 후보
1개

🛡 가장 안정적인 후보
1개

⚠️ 가장 주의해야 할 후보
1개

그리고

"AI 검증 신뢰도"

를 표시한다.

시장 데이터만 있고
뉴스/GitHub/Google Trends가 없으면
신뢰도를 낮게 표시한다.

========================

실제 시장 데이터
========================

{market_text}
"""

    return prompt


# ============================================================
# Gemini Interactions API
# ============================================================

def call_gemini(prompt):

    if not GEMINI_API_KEY:

        return None, "GEMINI_API_KEY 없음"

    # 최신 모델부터 시도
    for model in GEMINI_MODELS:

        url = (
            "https://generativelanguage.googleapis.com/"
            "v1beta/interactions"
        )

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        }

        payload = {
            "model": model,
            "input": prompt,
        }

        try:

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=60,
            )

            # 성공
            if response.status_code == 200:

                data = response.json()

                # Interactions API 응답에서 text 찾기
                text = extract_interaction_text(data)

                if text:

                    return text, None

                return None, (
                    "Gemini 응답은 성공했지만 "
                    "텍스트를 찾지 못했습니다."
                )

            # quota
            if response.status_code == 429:

                print(
                    f"Gemini 429: {model}"
                )

                # 다음 모델로 시도
                continue

            # model not found
            if response.status_code == 404:

                print(
                    f"Gemini 404: {model}"
                )

                continue

            print(
                f"Gemini 오류 {response.status_code}: "
                f"{response.text[:500]}"
            )

        except Exception as e:

            print(
                f"Gemini 요청 오류: {e}"
            )

    return None, (
        "Gemini 최신정보 검증 실패"
    )


# ============================================================
# Gemini 응답 파싱
# ============================================================

def extract_interaction_text(data):

    # 가장 흔한 형태
    if isinstance(data.get("output"), str):

        return data["output"]

    output = data.get("output")

    if isinstance(output, list):

        texts = []

        for item in output:

            if not isinstance(item, dict):
                continue

            # content
            content = item.get("content")

            if isinstance(content, list):

                for c in content:

                    if isinstance(c, dict):

                        text = c.get("text")

                        if text:
                            texts.append(text)

            # 직접 text
            text = item.get("text")

            if text:
                texts.append(text)

        if texts:

            return "\n".join(texts)

    # fallback
    response = data.get("response")

    if isinstance(response, str):

        return response

    return None


# ============================================================
# Gemini 실패 시 데이터 기반 메시지
# ============================================================

def create_fallback_report(top10):

    if not top10:

        return (
            "🚨 미국 주식 전략 레이더\n\n"
            "시장 데이터를 수집하지 못했습니다.\n"
            "다음 실행 주기에 다시 시도합니다."
        )

    now = now_kst().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    text = []

    text.append(
        "🚨 미국 주식 전략 레이더"
    )

    text.append(
        f"\n⏰ {now} KST"
    )

    text.append(
        "\n⚠️ Gemini AI 검증은 현재 사용할 수 없습니다."
    )

    text.append(
        "\n아래 내용은 실제 시장 가격/거래량을 "
        "기반으로 계산한 자동 데이터 점수입니다."
    )

    text.append(
        "\n※ AI가 확인하지 못한 뉴스나 재료를 "
        "임의로 생성하지 않습니다."
    )

    text.append(
        "\n━━━━━━━━━━━━━━"
    )

    for i, item in enumerate(top10, 1):

        text.append(
            f"\n{i}️⃣ {item['symbol']} "
            f"({item['category']})"
        )

        text.append(
            f"\n현재가: {format_money(item['price'])}"
        )

        text.append(
            f"\n일간: {item['daily_change']:+.2f}%"
        )

        text.append(
            f"\n주간: {item['weekly_change']:+.2f}%"
        )

        text.append(
            f"\n거래량: {item['volume_ratio']:.2f}배"
        )

        text.append(
            f"\n데이터 점수: "
            f"{item['score']:.1f}/100"
        )

        text.append(
            f"\n상태: {item['status']}"
        )

    text.append(
        "\n━━━━━━━━━━━━━━"
    )

    text.append(
        "\nGemini 상태"
    )

    text.append(
        "\n최신 뉴스/재료/GitHub/Google Trends "
        "교차검증을 완료하지 못했습니다."
    )

    text.append(
        "\n따라서 급등 확률이나 성공 확률을 "
        "임의로 생성하지 않았습니다."
    )

    return "\n".join(text)


# ============================================================
# 텔레그램 메시지 분할
# ============================================================

def send_telegram(text):

    if not TELEGRAM_BOT_TOKEN:

        print(
            "TELEGRAM_BOT_TOKEN 없음"
        )

        return False

    if not TELEGRAM_CHAT_ID:

        print(
            "TELEGRAM_CHAT_ID 없음"
        )

        return False

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    # Telegram 메시지 길이 제한 대비
    max_length = 3900

    chunks = [
        text[i:i + max_length]
        for i in range(
            0,
            len(text),
            max_length
        )
    ]

    success = True

    for chunk in chunks:

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
        }

        try:

            response = requests.post(
                url,
                json=payload,
                timeout=15,
            )

            if response.status_code != 200:

                print(
                    "Telegram 오류:",
                    response.text[:500]
                )

                success = False

        except Exception as e:

            print(
                "Telegram 요청 오류:",
                e
            )

            success = False

        time.sleep(0.5)

    return success


# ============================================================
# 메인
# ============================================================

def main():

    print("=" * 60)

    print(
        "미국 주식 전략 레이더 시작"
    )

    print(
        now_kst().strftime(
            "%Y-%m-%d %H:%M:%S KST"
        )
    )

    print("=" * 60)

    # --------------------------------------------------------
    # 1. 시장 데이터
    # --------------------------------------------------------

    results = collect_market_data()

    # --------------------------------------------------------
    # 2. 데이터가 일부라도 있으면 계속 진행
    # --------------------------------------------------------

    if not results:

        report = (
            "🚨 미국 주식 전략 레이더\n\n"
            "시장 데이터를 수집하지 못했습니다.\n\n"
            "Yahoo Finance 데이터 서버의 "
            "일시적 오류 또는 네트워크 오류일 수 있습니다.\n\n"
            "다음 실행 주기에 자동 재시도합니다."
        )

        send_telegram(report)

        return

    # --------------------------------------------------------
    # 3. TOP 10
    # --------------------------------------------------------

    top10 = select_top10(results)

    # --------------------------------------------------------
    # 4. Gemini 분석
    # --------------------------------------------------------

    gemini_text = None
    gemini_error = None

    if GEMINI_API_KEY:

        prompt = build_gemini_prompt(
            top10
        )

        print(
            "Gemini AI 분석 시작..."
        )

        gemini_text, gemini_error = (
            call_gemini(prompt)
        )

    else:

        gemini_error = (
            "GEMINI_API_KEY가 설정되지 않았습니다."
        )

    # --------------------------------------------------------
    # 5. Gemini 성공
    # --------------------------------------------------------

    if gemini_text:

        report = (
            "🚨 미국 주식 전략 레이더\n\n"
            + gemini_text
        )

    # --------------------------------------------------------
    # 6. Gemini 실패
    # --------------------------------------------------------

    else:

        print(
            "Gemini 분석 실패:",
            gemini_error
        )

        report = create_fallback_report(
            top10
        )

    # --------------------------------------------------------
    # 7. Telegram
    # --------------------------------------------------------

    print(
        "Telegram 전송 시작..."
    )

    telegram_success = send_telegram(
        report
    )

    if telegram_success:

        print(
            "Telegram 전송 성공"
        )

    else:

        print(
            "Telegram 전송 실패"
        )

    print("=" * 60)

    print("프로그램 종료")


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    main()
def now_kst():
    return datetime.now(KST)


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def pct_change(current, previous):
    if previous is None or previous == 0:
        return 0.0

    return ((current - previous) / previous) * 100.0


def request_json(url, params=None, headers=None, timeout=15):
    try:
        r = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout
        )

        if r.status_code != 200:
            return None

        return r.json()

    except Exception:
        return None


# ============================================================
# 상태 저장
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return {}


def save_state(state):

    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                state,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception as e:
        print("상태 저장 오류:", e)


# ============================================================
# Yahoo Finance 데이터
# ============================================================

def yahoo_chart(symbol, range_value="1mo", interval="1h"):

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    params = {
        "range": range_value,
        "interval": interval,
        "includePrePost": "true"
    }

    return request_json(url, params=params)


def get_market_data(symbol):

    data = yahoo_chart(symbol, "1mo", "1h")

    if not data:
        return None

    try:

        result = data["chart"]["result"][0]

        meta = result.get("meta", {})

        timestamps = result.get("timestamp", [])
        quote = result["indicators"]["quote"][0]

        closes = quote.get("close", [])
        volumes = quote.get("volume", [])

        clean_prices = []
        clean_volumes = []

        for c in closes:

            if c is not None:
                clean_prices.append(float(c))

        for v in volumes:

            if v is not None:
                clean_volumes.append(float(v))

        if not clean_prices:
            return None

        current_price = clean_prices[-1]

        # 최근 1시간
        one_hour_price = None

        if len(clean_prices) >= 2:
            one_hour_price = clean_prices[-2]

        # 대략 하루 전
        day_price = None

        if len(clean_prices) >= 8:
            day_price = clean_prices[-8]

        # 5거래일 전
        week_price = None

        if len(clean_prices) >= 35:
            week_price = clean_prices[-35]

        # 이동평균
        ma5 = (
            sum(clean_prices[-5:]) / 5
            if len(clean_prices) >= 5
            else current_price
        )

        ma20 = (
            sum(clean_prices[-20:]) / 20
            if len(clean_prices) >= 20
            else current_price
        )

        # 거래량 평균
        recent_volume = (
            clean_volumes[-1]
            if clean_volumes
            else 0
        )

        if len(clean_volumes) >= 20:

            avg_volume = (
                sum(clean_volumes[-20:-1])
                / len(clean_volumes[-20:-1])
            )

        else:

            avg_volume = (
                sum(clean_volumes)
                / len(clean_volumes)
                if clean_volumes
                else 0
            )

        volume_ratio = (
            recent_volume / avg_volume
            if avg_volume > 0
            else 1
        )

        # 최근 20개 고점
        recent_high = max(clean_prices[-20:])

        drawdown = (
            ((current_price - recent_high) / recent_high) * 100
            if recent_high > 0
            else 0
        )

        # RSI
        rsi = calculate_rsi(clean_prices)

        return {
            "symbol": symbol,
            "price": current_price,

            "hour_change": pct_change(
                current_price,
                one_hour_price
            ),

            "day_change": pct_change(
                current_price,
                day_price
            ),

            "week_change": pct_change(
                current_price,
                week_price
            ),

            "volume_ratio": volume_ratio,

            "ma5": ma5,
            "ma20": ma20,

            "rsi": rsi,

            "drawdown": drawdown,

            "timestamp": (
                now_kst().strftime("%Y-%m-%d %H:%M:%S")
            )
        }

    except Exception as e:

        print(symbol, "데이터 분석 오류:", e)

        return None


# ============================================================
# RSI
# ============================================================

def calculate_rsi(prices, period=14):

    if len(prices) < period + 1:
        return 50.0

    gains = []
    losses = []

    for i in range(1, len(prices)):

        diff = prices[i] - prices[i - 1]

        if diff > 0:
            gains.append(diff)
            losses.append(0)

        else:
            gains.append(0)
            losses.append(abs(diff))

    avg_gain = (
        sum(gains[-period:]) / period
    )

    avg_loss = (
        sum(losses[-period:]) / period
    )

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


# ============================================================
# 후보 종목
#
# 대형 + 중형 + 소형/고변동 후보를 섞음
# ============================================================

SYMBOLS = [

    # AI / 반도체
    "NVDA",
    "AMD",
    "AVGO",
    "INTC",
    "MU",
    "TSM",
    "AMAT",
    "LRCX",
    "ASML",
    "ANET",

    # AI 데이터센터
    "CRWV",
    "NBIS",
    "IREN",
    "SMCI",

    # 성장주
    "TEM",
    "PLTR",
    "SOFI",
    "RKLB",

    # 우주 / 고변동
    "LUNR",
    "ASTS",

    # 전기차 / 성장
    "TSLA",

    # 에너지 / 인프라
    "VST",
    "CEG",
    "OKLO",

    # 추가 중소형 성장 후보
    "SOUN",
    "BBAI",
    "AI",
    "IONQ",
    "RGTI",
    "QBTS",
]


# ============================================================
# 정량 점수
# ============================================================

def calculate_score(data):

    score = 50.0

    hour_change = data["hour_change"]
    day_change = data["day_change"]
    week_change = data["week_change"]

    volume_ratio = data["volume_ratio"]

    rsi = data["rsi"]

    price = data["price"]

    ma5 = data["ma5"]
    ma20 = data["ma20"]

    # ---------------------------------
    # 거래량
    # ---------------------------------

    if volume_ratio >= 3:
        score += 15

    elif volume_ratio >= 2:
        score += 12

    elif volume_ratio >= 1.5:
        score += 8

    elif volume_ratio >= 1.2:
        score += 4

    elif volume_ratio < 0.7:
        score -= 5

    # ---------------------------------
    # 단기 모멘텀
    # ---------------------------------

    if day_change > 10:
        score += 10

    elif day_change > 5:
        score += 7

    elif day_change > 2:
        score += 4

    elif day_change < -10:
        score -= 8

    elif day_change < -5:
        score -= 5

    # ---------------------------------
    # 주간 모멘텀
    # ---------------------------------

    if week_change > 20:
        score += 8

    elif week_change > 10:
        score += 5

    elif week_change > 5:
        score += 3

    elif week_change < -15:
        score -= 5

    # ---------------------------------
    # 이동평균
    # ---------------------------------

    if price > ma5:
        score += 4

    else:
        score -= 3

    if ma5 > ma20:
        score += 4

    else:
        score -= 3

    # ---------------------------------
    # RSI
    # ---------------------------------

    if 45 <= rsi <= 65:
        score += 5

    elif 30 <= rsi < 45:
        score += 3

    elif rsi > 80:
        score -= 8

    elif rsi > 70:
        score -= 4

    elif rsi < 25:
        score -= 5

    return clamp(score, 0, 100)


# ============================================================
# 뉴스
# ============================================================

def get_news(symbol):

    # Finnhub가 있으면 우선 사용
    if FINNHUB_API_KEY:

        today = now_kst().date()

        from_date = today

        url = "https://finnhub.io/api/v1/company-news"

        params = {
            "symbol": symbol,
            "from": str(from_date),
            "to": str(today),
            "token": FINNHUB_API_KEY
        }

        data = request_json(url, params=params)

        if data:

            news = []

            for item in data[:5]:

                headline = item.get("headline", "")

                source = item.get("source", "")

                url_value = item.get("url", "")

                if headline:

                    news.append({
                        "headline": headline,
                        "source": source,
                        "url": url_value
                    })

            return news

    # API가 없을 경우
    return []


# ============================================================
# GitHub 데이터
#
# 모든 주식이 GitHub 프로젝트와 직접 연결되는 것은 아니므로
# GitHub 데이터가 없다고 악재로 판단하지 않는다.
# ============================================================

def github_search(symbol):

    url = "https://api.github.com/search/repositories"

    params = {
        "q": symbol,
        "sort": "updated",
        "order": "desc",
        "per_page": 5
    }

    headers = {
        "Accept": "application/vnd.github+json"
    }

    data = request_json(
        url,
        params=params,
        headers=headers
    )

    if not data:
        return []

    results = []

    for item in data.get("items", []):

        results.append({
            "name": item.get("full_name"),
            "stars": item.get("stargazers_count"),
            "forks": item.get("forks_count"),
            "updated": item.get("updated_at"),
            "description": item.get("description")
        })

    return results


# ============================================================
# Gemini Interactions API
# ============================================================

def call_gemini(prompt):

    if not GEMINI_API_KEY:

        return {
            "success": False,
            "error": "GEMINI_API_KEY가 없습니다."
        }

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/interactions"
    )

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }

    payload = {

        "model": GEMINI_MODEL,

        "input": prompt,

        "generation_config": {

            "max_output_tokens": 5000
        }
    }

    # 429 대응
    retry_delays = [3, 8, 20]

    for attempt in range(len(retry_delays) + 1):

        try:

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=60
            )

            # 성공
            if response.status_code == 200:

                data = response.json()

                # 공식 response 구조
                output_text = data.get(
                    "output_text",
                    ""
                )

                if output_text:
                    return {
                        "success": True,
                        "text": output_text
                    }

                # 혹시 output_text가 없는 경우
                steps = data.get("steps", [])

                for step in reversed(steps):

                    if step.get("type") != "model_output":
                        continue

                    content = step.get(
                        "content",
                        []
                    )

                    for item in content:

                        if item.get("type") == "text":

                            text = item.get(
                                "text",
                                ""
                            )

                            if text:

                                return {
                                    "success": True,
                                    "text": text
                                }

                return {
                    "success": False,
                    "error": "Gemini 응답 텍스트를 찾지 못했습니다."
                }

            # 429
            if response.status_code == 429:

                print(
                    f"Gemini 429 발생 "
                    f"({attempt + 1}/{len(retry_delays) + 1})"
                )

                if attempt < len(retry_delays):

                    time.sleep(
                        retry_delays[attempt]
                    )

                    continue

                return {
                    "success": False,
                    "error": "429 RESOURCE_EXHAUSTED"
                }

            # 기타 오류
            try:

                error_json = response.json()

                message = (
                    error_json
                    .get("error", {})
                    .get("message", "")
                )

            except Exception:

                message = response.text[:500]

            return {
                "success": False,
                "error": (
                    f"Gemini HTTP {response.status_code}: "
                    f"{message}"
                )
            }

        except requests.exceptions.Timeout:

            if attempt < len(retry_delays):

                time.sleep(
                    retry_delays[attempt]
                )

                continue

            return {
                "success": False,
                "error": "Gemini 요청 시간 초과"
            }

        except Exception as e:

            return {
                "success": False,
                "error": str(e)
            }

    return {
        "success": False,
        "error": "Gemini 호출 실패"
    }


# ============================================================
# Gemini 분석 프롬프트
# ============================================================

def create_ai_prompt(candidates):

    today = now_kst().strftime(
        "%Y-%m-%d %H:%M KST"
    )

    data_text = []

    for item in candidates:

        market = item["market"]

        news = item["news"]

        github = item["github"]

        news_text = "\n".join(
            [
                f"- {n['headline']}"
                for n in news[:3]
            ]
        )

        if not news_text:
            news_text = "확인된 뉴스 없음"

        github_text = "\n".join(
            [
                (
                    f"- {g['name']} "
                    f"stars={g['stars']} "
                    f"forks={g['forks']} "
                    f"updated={g['updated']}"
                )
                for g in github[:3]
            ]
        )

        if not github_text:
            github_text = "직접 연관 GitHub 자료 없음"

        data_text.append(
            f"""
[종목 {market['symbol']}]

현재가: ${market['price']:.2f}

1시간 변화: {market['hour_change']:.2f}%
1일 변화: {market['day_change']:.2f}%
1주 변화: {market['week_change']:.2f}%

거래량/평균: {market['volume_ratio']:.2f}배

MA5: {market['ma5']:.2f}
MA20: {market['ma20']:.2f}

RSI: {market['rsi']:.1f}

정량 점수: {item['score']:.1f}/100

뉴스:
{news_text}

GitHub:
{github_text}
"""
        )

    prompt = f"""
당신은 미국 주식 시장을 분석하는 시니어 전략 분석가다.

분석 기준 시각:
{today}

목표:
제공된 실제 시장 데이터를 기반으로 미국 주식 중
향후 단기 반등 가능성이 상대적으로 높은 TOP 10을 선정한다.

중요:
절대로 데이터에 없는 가격, 뉴스, 실적, 공시를 만들어내지 마라.

최신성 검증:
- 제공된 뉴스가 없으면 "뉴스 확인 안 됨"이라고 표시
- 확인되지 않은 사실은 사실처럼 쓰지 마라.
- GitHub 자료가 주가와 직접 연결되지 않는 경우 억지로 연결하지 마라.
- 확률은 예측치일 뿐이며 확정적인 성공률로 표현하지 마라.

==================================================
10가지 분석 아이디어
==================================================

1. GitHub 커밋 가속도 + Google 검색 관심도의 시간차
   - 개발 활동 증가 + 대중 관심 낮음 = 잠재적 초기 모멘텀
   - 단, 직접적인 주식 연관성이 확인되는 경우에만 사용

2. GitHub 보안 취약점 / 코드 롤백
   - exploit
   - emergency
   - unauthorized
   - overflow
   - pause
   등의 위험 신호가 실제로 확인되는 경우 위험 점수 상승

3. Developer Migration
   - 주요 개발자 유입
   - stars/forks 증가
   - 프로젝트 개발활동 증가

4. Fake Star / 인위적 관심
   - 뉴스나 검색 관심만 급증하고 실질적 개발활동이 없는 경우 주의

5. Governance / 개발자 갈등
   - fork
   - abandon
   - proposal rejected
   - scam
   등의 실제 신호 확인

6. Release / 업그레이드
   - 실제 release
   - 업데이트
   - 제품 출시
   - 실적/가이던스
   등의 촉매 확인

7. 보안 / 코드 위험
   - 심각한 기술적 위험이 확인되면 급락 위험을 높인다.

8. Developer Ghosting
   - 개발활동 급감
   - 핵심 개발자 이탈
   등이 확인되면 위험 증가

9. Panic + 해결
   - 악재 이후 문제가 실제로 해결되었는지 확인
   - 해결되었다는 근거가 있을 경우 반등 가능성 검토

10. Cross-Agent Consensus
   다음 두 관점을 독립적으로 평가한다.

   Agent A:
   기술/개발/제품/실적/시장 구조 분석

   Agent B:
   뉴스/시장 심리/FOMO/공포/거래량/가격 모멘텀 분석

   두 분석이 일치하는 종목을 높은 우선순위로 둔다.

==================================================
주식 분석 원칙
==================================================

대형주만 고르지 마라.

다음 세 그룹을 균형 있게 검토한다.

A. 대형주
B. 중형주
C. 소형/고변동 성장주

단,

소형주라고 무조건 높은 점수를 주지 마라.

유동성 부족,
급격한 상승 후 과열,
악재,
과도한 RSI,
거래량만 증가하고 가격 구조가 약한 경우
위험 점수를 높여라.

==================================================
반등 판단
==================================================

다음 요소를 종합한다.

- 거래량 급증
- 가격 모멘텀
- MA5 / MA20
- RSI
- 최근 뉴스
- 실적
- 산업 모멘텀
- 시장 전체 분위기
- 기술적 지지
- 이벤트 촉매
- 악재 해결 여부

==================================================
급락 위험
==================================================

다음이 있으면 위험 증가:

- 지나친 단기 급등
- RSI 과열
- 거래량 폭증 후 가격 약화
- 악재 뉴스
- 실적 미스
- 가이던스 하향
- 보안 문제
- 개발활동 급감
- 과도한 기대감
- 시장 금리 급등
- 지수 급락

==================================================
확률 규칙
==================================================

"성공확률"이라는 표현 대신
"예상 반등 가능성"을 사용한다.

데이터가 충분한 경우에만 0~100 범위의
예상 반등 가능성을 제시한다.

이는 투자 성공 확률이 아니다.

근거가 부족하면:
"확률 산출 보류"

라고 한다.

==================================================
출력
==================================================

반드시 아래 JSON 형식으로 출력한다.

{
  "market_view": "상승/중립/하락",
  "top10": [
    {
      "rank": 1,
      "symbol": "XXXX",
      "direction": "반등/중립/하락주의",
      "score": 0,
      "rebound_probability": 0,
      "risk_probability": 0,
      "reason": "핵심 근거",
      "catalyst": "상승 촉매",
      "risk": "주요 위험",
      "entry_condition": "관찰 조건",
      "data_quality": "높음/보통/낮음"
    }
  ],
  "best_candidate": "XXXX",
  "market_risk": "낮음/보통/높음",
  "verification_note": "최신 데이터 검증 상태"
}

반드시 JSON만 출력한다.

분석 데이터:
{''.join(data_text)}
"""

    return prompt


# ============================================================
# JSON 추출
# ============================================================

def parse_ai_json(text):

    if not text:
        return None

    text = text.strip()

    # ```json 제거
    if text.startswith("```"):

        text = text.replace(
            "```json",
            ""
        )

        text = text.replace(
            "```",
            ""
        )

        text = text.strip()

    try:

        return json.loads(text)

    except Exception:

        # JSON 시작/끝 추출
        start = text.find("{")
        end = text.rfind("}")

        if start >= 0 and end > start:

            try:

                return json.loads(
                    text[start:end + 1]
                )

            except Exception:
                return None

    return None


# ============================================================
# 텔레그램
# ============================================================

def telegram_send(message):

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

    # Telegram 메시지 제한 방어
    chunks = []

    max_length = 3800

    while len(message) > max_length:

        cut = message.rfind(
            "\n",
            0,
            max_length
        )

        if cut < 1000:
            cut = max_length

        chunks.append(
            message[:cut]
        )

        message = message[cut:]

    chunks.append(message)

    success = True

    for chunk in chunks:

        try:

            response = requests.post(
                url,
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": chunk
                },
                timeout=15
            )

            if response.status_code != 200:

                print(
                    "Telegram 오류:",
                    response.text
                )

                success = False

        except Exception as e:

            print(
                "Telegram 전송 오류:",
                e
            )

            success = False

    return success


# ============================================================
# AI 결과 포맷
# ============================================================

def format_ai_report(ai):

    lines = []

    lines.append(
        "🚨 미국 주식 전략 레이더"
    )

    lines.append("")

    lines.append(
        f"⏰ {now_kst().strftime('%Y-%m-%d %H:%M:%S')} KST"
    )

    lines.append("")

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    lines.append(
        f"📊 시장 전망: {ai.get('market_view', '미확인')}"
    )

    lines.append(
        f"⚠️ 시장 위험: {ai.get('market_risk', '미확인')}"
    )

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    top10 = ai.get("top10", [])

    for item in top10[:10]:

        rank = item.get("rank", "?")

        symbol = item.get(
            "symbol",
            "UNKNOWN"
        )

        direction = item.get(
            "direction",
            "미확인"
        )

        score = item.get(
            "score",
            "-"
        )

        rebound = item.get(
            "rebound_probability",
            "보류"
        )

        risk = item.get(
            "risk_probability",
            "보류"
        )

        reason = item.get(
            "reason",
            "확인 필요"
        )

        catalyst = item.get(
            "catalyst",
            "확인 필요"
        )

        danger = item.get(
            "risk",
            "확인 필요"
        )

        condition = item.get(
            "entry_condition",
            "확인 필요"
        )

        quality = item.get(
            "data_quality",
            "낮음"
        )

        lines.append("")

        lines.append(
            f"{rank}️⃣ {symbol} "
            f"[{direction}]"
        )

        lines.append(
            f"종합점수: {score}/100"
        )

        lines.append(
            f"예상 반등 가능성: {rebound}%"
        )

        lines.append(
            f"급락 위험: {risk}%"
        )

        lines.append(
            f"데이터 신뢰도: {quality}"
        )

        lines.append(
            f"📌 {reason}"
        )

        lines.append(
            f"🚀 촉매: {catalyst}"
        )

        lines.append(
            f"⚠️ 위험: {danger}"
        )

        lines.append(
            f"🎯 조건: {condition}"
        )

    lines.append("")

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    lines.append(
        f"🏆 최우선 관심: "
        f"{ai.get('best_candidate', '미확인')}"
    )

    lines.append("")

    lines.append(
        "🔎 "
        + ai.get(
            "verification_note",
            "최신 데이터 검증 결과를 확인하세요."
        )
    )

    lines.append("")

    lines.append(
        "※ 반등 가능성은 투자 성공확률이 아닙니다."
    )

    lines.append(
        "※ 투자 판단 전 실시간 가격·공시·뉴스를 재확인하세요."
    )

    return "\n".join(lines)


# ============================================================
# Gemini 실패 시 정량 분석만 전송
# ============================================================

def create_fallback_report(candidates):

    lines = []

    lines.append(
        "🚨 미국 주식 전략 레이더"
    )

    lines.append("")

    lines.append(
        f"⏰ {now_kst().strftime('%Y-%m-%d %H:%M:%S')} KST"
    )

    lines.append("")

    lines.append(
        "⚠️ Gemini AI 검증을 완료하지 못했습니다."
    )

    lines.append(
        "아래 순위는 실제 가격·거래량 기반 자동 점수입니다."
    )

    lines.append(
        "※ AI 검증 추천이 아니며 확률을 임의로 생성하지 않습니다."
    )

    lines.append("")

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    for i, item in enumerate(
        candidates[:10],
        start=1
    ):

        d = item["market"]

        lines.append("")

        lines.append(
            f"{i}️⃣ {d['symbol']}"
        )

        lines.append(
            f"현재가: ${d['price']:.2f}"
        )

        lines.append(
            f"1시간: {d['hour_change']:+.2f}%"
        )

        lines.append(
            f"1일: {d['day_change']:+.2f}%"
        )

        lines.append(
            f"1주: {d['week_change']:+.2f}%"
        )

        lines.append(
            f"거래량: {d['volume_ratio']:.2f}배"
        )

        lines.append(
            f"정량 점수: {item['score']:.1f}/100"
        )

        lines.append(
            "상태: 🔎 AI 검증 대기"
        )

    lines.append("")

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    lines.append(
        "Gemini가 복구되면 다음 주기에"
    )

    lines.append(
        "뉴스 + 시장심리 + 10가지 전략을"
    )

    lines.append(
        "추가하여 TOP 10을 다시 분석합니다."
    )

    return "\n".join(lines)


# ============================================================
# 메인
# ============================================================

def main():

    print("=" * 60)

    print(
        "미국 주식 전략 레이더 시작:",
        now_kst()
    )

    print("=" * 60)

    # ---------------------------------------
    # 1. 시장 데이터 수집
    # ---------------------------------------

    candidates = []

    for symbol in SYMBOLS:

        print(
            f"[시장 데이터] {symbol}"
        )

        market = get_market_data(symbol)

        if not market:
            continue

        score = calculate_score(market)

        print(
            f"  가격 ${market['price']:.2f}"
        )

        print(
            f"  점수 {score:.1f}"
        )

        # 뉴스
        news = get_news(symbol)

        # GitHub
        github = github_search(symbol)

        candidates.append({

            "market": market,

            "score": score,

            "news": news,

            "github": github

        })

        # API 과부하 방지
        time.sleep(0.15)

    # ---------------------------------------
    # 데이터 부족
    # ---------------------------------------

    if not candidates:

        telegram_send(
            "🚨 미국 주식 전략 레이더\n\n"
            "시장 데이터를 수집하지 못했습니다.\n"
            "다음 실행 주기에 다시 시도합니다."
        )

        return

    # ---------------------------------------
    # 정량 점수 정렬
    # ---------------------------------------

    candidates.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # Gemini에 보낼 후보
    # 너무 많은 데이터를 보내지 않음
    ai_candidates = candidates[:15]

    # ---------------------------------------
    # Gemini 분석
    # ---------------------------------------

    print(
        "[Gemini] 최신 전략 분석 시작"
    )

    prompt = create_ai_prompt(
        ai_candidates
    )

    ai_result = call_gemini(prompt)

    # ---------------------------------------
    # Gemini 성공
    # ---------------------------------------

    if ai_result["success"]:

        print(
            "[Gemini] 분석 성공"
        )

        ai_json = parse_ai_json(
            ai_result["text"]
        )

        if ai_json:

            report = format_ai_report(
                ai_json
            )

        else:

            # JSON 파싱 실패
            report = (
                "🚨 미국 주식 전략 레이더\n\n"
                "Gemini 분석은 완료되었으나 "
                "결과 형식을 검증하지 못했습니다.\n\n"
                "※ 검증되지 않은 AI 결과는 "
                "추천 결과로 전송하지 않습니다."
            )

    # ---------------------------------------
    # Gemini 실패
    # ---------------------------------------

    else:

        print(
            "[Gemini] 분석 실패:",
            ai_result["error"]
        )

        report = create_fallback_report(
            candidates
        )

        report += (
            "\n\n━━━━━━━━━━━━━━\n"
            "Gemini 상태\n"
            "━━━━━━━━━━━━━━\n"
            f"{ai_result['error']}\n\n"
            "※ API 오류 상태에서는 "
            "임의의 AI 확률을 생성하지 않습니다."
        )

    # ---------------------------------------
    # Telegram
    # ---------------------------------------

    print(
        "[Telegram] 전송 시작"
    )

    success = telegram_send(
        report
    )

    if success:

        print(
            "[Telegram] 전송 성공"
        )

    else:

        print(
            "[Telegram] 전송 실패"
        )

    print(
        "분석 종료:",
        now_kst()
    )


if __name__ == "__main__":

    main()
