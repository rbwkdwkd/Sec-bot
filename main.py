import os
import json
import time
import math
import requests
from datetime import datetime, timezone, timedelta

# ============================================================
# 미국 주식 전략 레이더
# Gemini 3.6 Flash + Interactions API
# ============================================================

# =========================
# 환경변수
# =========================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# 선택사항
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "").strip()

# Gemini 최신 모델
GEMINI_MODEL = "gemini-3.6-flash"

# 한국시간
KST = timezone(timedelta(hours=9))

# 데이터 저장 파일
STATE_FILE = "market_state.json"


# ============================================================
# 기본 유틸
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
