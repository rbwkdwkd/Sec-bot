import os
import time
import math
import json
import html
import requests
import feedparser
import yfinance as yf

from datetime import datetime, timezone, timedelta
from urllib.parse import quote


# =========================================================
# 환경변수
# =========================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# 선택사항
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

# Gemini 모델
# 현재 안정적인 2.5 Flash 사용
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
).strip()


# =========================================================
# 기본 설정
# =========================================================

KST = timezone(timedelta(hours=9))

REQUEST_TIMEOUT = 15

TOP_N = 10

# Gemini에 넘길 후보 수
AI_CANDIDATES = 25


# =========================================================
# 분석 대상
#
# 대형주 + 중형주 + 소형주를 일부러 섞음
# =========================================================

TICKERS = [

    # -------------------------
    # AI / 반도체 대형
    # -------------------------

    "NVDA",
    "AMD",
    "AVGO",
    "TSM",
    "MU",
    "AMAT",
    "LRCX",
    "MRVL",
    "ARM",
    "ASML",
    "INTC",
    "QCOM",
    "SMCI",
    "ANET",

    # -------------------------
    # 빅테크
    # -------------------------

    "MSFT",
    "GOOGL",
    "META",
    "AMZN",
    "AAPL",
    "TSLA",
    "NFLX",

    # -------------------------
    # AI / 데이터 / 성장
    # -------------------------

    "PLTR",
    "CRWV",
    "TEM",
    "NBIS",
    "IREN",
    "HIMS",
    "RDDT",

    # -------------------------
    # 우주 / 방산 / 미래산업
    # -------------------------

    "RKLB",
    "ASTS",
    "LUNR",
    "ACHR",
    "JOBY",
    "OKLO",

    # -------------------------
    # AI 소형주 / 고변동
    # -------------------------

    "SOUN",
    "BBAI",
    "AI",
    "VERI",
    "BIGB",

    # -------------------------
    # 양자컴퓨팅
    # -------------------------

    "IONQ",
    "RGTI",
    "QBTS",
    "QUBT",

    # -------------------------
    # 바이오 / 헬스
    # -------------------------

    "CRSP",
    "RXRX",
    "BEAM",
    "EDIT",

    # -------------------------
    # 기타 성장주
    # -------------------------

    "CELH",
    "SOFI",
    "HOOD",
    "NU",
    "AFRM",
    "UPST",
    "CVNA",
    "MARA",
    "CLSK",
    "RIOT",

]


# =========================================================
# 분야
# =========================================================

SECTOR_MAP = {

    "NVDA": "AI/반도체",
    "AMD": "AI/반도체",
    "AVGO": "AI/반도체",
    "TSM": "반도체",
    "MU": "메모리/HBM",
    "AMAT": "반도체장비",
    "LRCX": "반도체장비",
    "MRVL": "AI 네트워크",
    "ARM": "반도체/CPU",
    "ASML": "반도체장비",
    "INTC": "반도체",
    "QCOM": "반도체",
    "SMCI": "AI 서버",
    "ANET": "AI 네트워크",

    "MSFT": "빅테크/AI",
    "GOOGL": "빅테크/AI",
    "META": "빅테크/AI",
    "AMZN": "빅테크/AI",
    "AAPL": "빅테크",
    "TSLA": "전기차/AI",
    "NFLX": "미디어",

    "PLTR": "AI/데이터",
    "CRWV": "AI 데이터센터",
    "TEM": "AI 헬스케어",
    "NBIS": "AI 데이터센터",
    "IREN": "AI 데이터센터/채굴",
    "HIMS": "헬스케어",
    "RDDT": "소셜/AI",

    "RKLB": "우주",
    "ASTS": "우주",
    "LUNR": "우주",
    "ACHR": "UAM",
    "JOBY": "UAM",
    "OKLO": "원자력",

    "SOUN": "AI 음성",
    "BBAI": "AI",
    "AI": "AI",
    "VERI": "AI",
    "BIGB": "AI",

    "IONQ": "양자컴퓨팅",
    "RGTI": "양자컴퓨팅",
    "QBTS": "양자컴퓨팅",
    "QUBT": "양자컴퓨팅",

    "CRSP": "바이오",
    "RXRX": "AI 바이오",
    "BEAM": "바이오",
    "EDIT": "바이오",

    "CELH": "소비재",
    "SOFI": "핀테크",
    "HOOD": "핀테크",
    "NU": "핀테크",
    "AFRM": "핀테크",
    "UPST": "핀테크",
    "CVNA": "자동차",
    "MARA": "크립토/채굴",
    "CLSK": "크립토/채굴",
    "RIOT": "크립토/채굴",
}


# =========================================================
# 공통
# =========================================================

def now_kst():
    return datetime.now(KST)


def safe_float(value, default=0.0):

    try:

        if value is None:
            return default

        if isinstance(value, float) and math.isnan(value):
            return default

        return float(value)

    except Exception:

        return default


def clamp(value, low=0, high=100):

    return max(low, min(high, value))


# =========================================================
# Telegram
# =========================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:

        print("Telegram 환경변수가 없습니다.")

        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {

        "chat_id": TELEGRAM_CHAT_ID,

        "text": message,

        "disable_web_page_preview": True,

    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=REQUEST_TIMEOUT
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


# =========================================================
# Yahoo Finance
# =========================================================

def get_stock_data(ticker):

    try:

        stock = yf.Ticker(ticker)

        hist = stock.history(
            period="3mo",
            interval="1d",
            auto_adjust=False
        )

        if hist.empty or len(hist) < 10:

            return None

        hist = hist.dropna()

        close = safe_float(
            hist["Close"].iloc[-1]
        )

        prev_close = safe_float(
            hist["Close"].iloc[-2]
        )

        volume = safe_float(
            hist["Volume"].iloc[-1]
        )

        avg_volume_20 = safe_float(
            hist["Volume"].tail(20).mean()
        )

        volume_ratio = (
            volume / avg_volume_20
            if avg_volume_20 > 0
            else 0
        )

        day_change = (
            ((close / prev_close) - 1) * 100
            if prev_close > 0
            else 0
        )

        week_base = safe_float(
            hist["Close"].iloc[-6]
        ) if len(hist) >= 6 else close

        month_base = safe_float(
            hist["Close"].iloc[-22]
        ) if len(hist) >= 22 else close

        week_change = (
            ((close / week_base) - 1) * 100
            if week_base > 0
            else 0
        )

        month_change = (
            ((close / month_base) - 1) * 100
            if month_base > 0
            else 0
        )

        high_3m = safe_float(
            hist["High"].max()
        )

        low_3m = safe_float(
            hist["Low"].min()
        )

        from_high = (
            ((close / high_3m) - 1) * 100
            if high_3m > 0
            else 0
        )

        from_low = (
            ((close / low_3m) - 1) * 100
            if low_3m > 0
            else 0
        )

        # RSI
        delta = hist["Close"].diff()

        gain = delta.clip(lower=0)

        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(14).mean().iloc[-1]

        avg_loss = loss.rolling(14).mean().iloc[-1]

        if avg_loss == 0:

            rsi = 100

        else:

            rs = avg_gain / avg_loss

            rsi = 100 - (
                100 / (1 + rs)
            )

        # 단기 이동평균
        ma5 = safe_float(
            hist["Close"].tail(5).mean()
        )

        ma20 = safe_float(
            hist["Close"].tail(20).mean()
        )

        trend_score = 0

        if close > ma5:
            trend_score += 5

        if close > ma20:
            trend_score += 5

        # 반등 점수
        rebound_score = 0

        if -15 <= from_high <= -3:
            rebound_score += 10

        if 30 <= rsi <= 55:
            rebound_score += 10

        if volume_ratio >= 1.3:
            rebound_score += 10

        if week_change > 0:
            rebound_score += 5

        # 급등 모멘텀
        momentum_score = 0

        if day_change > 2:
            momentum_score += 10

        if week_change > 5:
            momentum_score += 10

        if volume_ratio >= 2:
            momentum_score += 10

        # 과열 위험
        overheat_score = 0

        if rsi >= 75:
            overheat_score += 20

        if day_change >= 10:
            overheat_score += 15

        if week_change >= 30:
            overheat_score += 15

        # 급락 위험
        crash_score = 0

        if day_change <= -5:
            crash_score += 15

        if week_change <= -15:
            crash_score += 15

        if rsi <= 25:
            crash_score += 10

        info = {}

        try:

            info = stock.info or {}

        except Exception:

            info = {}

        market_cap = safe_float(
            info.get("marketCap")
        )

        short_ratio = safe_float(
            info.get("shortRatio")
        )

        float_shares = safe_float(
            info.get("floatShares")
        )

        shares_outstanding = safe_float(
            info.get("sharesOutstanding")
        )

        company_name = (
            info.get("longName")
            or info.get("shortName")
            or ticker
        )

        return {

            "ticker": ticker,

            "name": company_name,

            "sector": SECTOR_MAP.get(
                ticker,
                "기타"
            ),

            "price": close,

            "day_change": day_change,

            "week_change": week_change,

            "month_change": month_change,

            "volume_ratio": volume_ratio,

            "rsi": rsi,

            "ma5": ma5,

            "ma20": ma20,

            "from_high": from_high,

            "from_low": from_low,

            "market_cap": market_cap,

            "short_ratio": short_ratio,

            "float_shares": float_shares,

            "shares_outstanding": shares_outstanding,

            "trend_score": trend_score,

            "rebound_score": rebound_score,

            "momentum_score": momentum_score,

            "overheat_score": overheat_score,

            "crash_score": crash_score,

        }

    except Exception as e:

        print(
            f"{ticker} 데이터 오류:",
            e
        )

        return None


# =========================================================
# 뉴스
# =========================================================

def get_news(ticker, company_name):

    try:

        query = quote(
            f"{ticker} {company_name} stock"
        )

        url = (
            "https://news.google.com/rss/search?"
            f"q={query}"
            "&hl=en-US"
            "&gl=US"
            "&ceid=US:en"
        )

        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent":
                "Mozilla/5.0"
            }
        )

        feed = feedparser.parse(
            response.content
        )

        articles = []

        for entry in feed.entries[:5]:

            title = entry.get(
                "title",
                ""
            )

            published = entry.get(
                "published",
                ""
            )

            if title:

                articles.append({
                    "title": title,
                    "published": published
                })

        return articles

    except Exception as e:

        print(
            f"{ticker} 뉴스 오류:",
            e
        )

        return []


# =========================================================
# GitHub 개발활동
#
# 주식회사 자체 GitHub가 있는 경우에 한해 참고지표로 사용
# =========================================================

GITHUB_REPOS = {

    "IONQ": [
        "ionq/ionq"
    ],

    "RGTI": [
        "rigetti/pyquil"
    ],

    "QBTS": [
        "dwavesystems/dwave-ocean-sdk"
    ],

    "QUBT": [
        "Qunnect/Qunnect"
    ],

    "PLTR": [
        "palantir/blueprint"
    ],

    "RKLB": [
        "Rocket-Lab"
    ],

}


def github_headers():

    headers = {
        "Accept":
        "application/vnd.github+json"
    }

    if GITHUB_TOKEN:

        headers["Authorization"] = (
            f"Bearer {GITHUB_TOKEN}"
        )

    return headers


def get_github_activity(ticker):

    repos = GITHUB_REPOS.get(
        ticker,
        []
    )

    if not repos:

        return {

            "available": False,

            "commits_30d": None,

            "issues": None,

            "activity_score": 0,

        }

    total_commits = 0

    total_issues = 0

    for repo in repos:

        try:

            url = (
                "https://api.github.com/repos/"
                f"{repo}/commits"
            )

            params = {
                "per_page": 30
            }

            response = requests.get(
                url,
                headers=github_headers(),
                params=params,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code != 200:

                continue

            commits = response.json()

            total_commits += len(commits)

        except Exception:

            continue

        try:

            url = (
                "https://api.github.com/repos/"
                f"{repo}/issues"
            )

            params = {

                "state": "open",

                "per_page": 20

            }

            response = requests.get(
                url,
                headers=github_headers(),
                params=params,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 200:

                issues = response.json()

                total_issues += len(
                    [
                        x for x in issues
                        if "pull_request" not in x
                    ]
                )

        except Exception:

            pass

    activity_score = clamp(
        total_commits * 2
    )

    return {

        "available": True,

        "commits_30d": total_commits,

        "issues": total_issues,

        "activity_score":
            activity_score,

    }


# =========================================================
# 후보 종목 사전 점수
# =========================================================

def calculate_pre_score(data, news_count, github):

    score = 0

    # 가격 모멘텀
    score += clamp(
        data["momentum_score"],
        0,
        30
    )

    # 반등 가능성
    score += clamp(
        data["rebound_score"],
        0,
        25
    )

    # 추세
    score += clamp(
        data["trend_score"],
        0,
        10
    )

    # 거래량
    if data["volume_ratio"] >= 1.5:
        score += 10

    elif data["volume_ratio"] >= 1.2:
        score += 5

    # 뉴스
    if news_count >= 4:
        score += 10

    elif news_count >= 2:
        score += 5

    # GitHub
    if github.get("available"):

        score += min(
            10,
            github.get(
                "activity_score",
                0
            )
        )

    # 소형주/중소형주 보너스
    market_cap = data["market_cap"]

    if 0 < market_cap < 2_000_000_000:

        score += 8

    elif 0 < market_cap < 10_000_000_000:

        score += 5

    # 과열 감점
    score -= data["overheat_score"] * 0.4

    # 급락 위험 감점
    score -= data["crash_score"] * 0.4

    return clamp(
        round(score, 1)
    )


# =========================================================
# 시장 상황
# =========================================================

def get_market_data():

    indexes = [
        "^GSPC",
        "^IXIC",
        "^DJI",
        "^VIX",
        "^TNX"
    ]

    result = {}

    for symbol in indexes:

        try:

            hist = yf.Ticker(
                symbol
            ).history(
                period="5d",
                interval="1d"
            )

            if hist.empty:
                continue

            close = safe_float(
                hist["Close"].iloc[-1]
            )

            previous = safe_float(
                hist["Close"].iloc[-2]
            )

            change = (
                ((close / previous) - 1)
                * 100
                if previous
                else 0
            )

            result[symbol] = {

                "value": close,

                "change": change

            }

        except Exception:

            continue

    return result


# =========================================================
# Gemini 분석
# =========================================================

def build_gemini_prompt(candidates, market):

    market_text = json.dumps(
        market,
        ensure_ascii=False
    )

    candidate_text = json.dumps(
        candidates,
        ensure_ascii=False,
        indent=2
    )

    prompt = f"""
당신은 미국 주식 시장을 분석하는
'시니어 주식 전략 분석가'다.

중요:
절대로 확인되지 않은 사실을 만들어내지 마라.
주가, 뉴스, 실적, 기업 이벤트를 추측해서 사실처럼 쓰지 마라.

입력 데이터에 없는 내용은
'확인되지 않음'이라고 표시하라.

목표:
미국 주식 가운데 향후 단기 반등 가능성이 높은
종목 10개를 선정한다.

대형주만 고르지 말고
중형주와 소형주도 적극적으로 검토한다.

단, 소형주라고 해서 무조건 높은 순위를 주지 마라.

====================================
분석 기준
====================================

1. 가격/거래량 모멘텀

2. 최근 반등 가능성

3. RSI 및 이동평균

4. 뉴스 모멘텀

5. 시장 전체 방향

6. 금리/VIX 환경

7. 공매도 및 숏스퀴즈 가능성
   단, 실제 데이터가 없으면 추측하지 않는다.

8. 소형주 급등 가능성

9. 과열 여부

10. 급락 위험

====================================
아이디어 1
====================================

GitHub 개발활동과 대중 관심도의 시간차를 분석한다.

GitHub 활동이 증가하면서
시장 관심이 낮다면
'미반영 기술 모멘텀' 가능성을 검토한다.

단, GitHub 데이터가 없으면
없는 것으로 처리한다.

====================================
아이디어 2
====================================

보안/코드 위험 신호를 검토한다.

공식적인 확인이 없는 경우
해킹이나 내부자 매도를 단정하지 않는다.

====================================
아이디어 3
====================================

개발자 유입/기술 생태계 확장을 검토한다.

데이터가 없으면 평가하지 않는다.

====================================
아이디어 4
====================================

과도한 뉴스/검색 관심 대비
실제 가격과 거래량의 질이 나쁜 경우
펌핑 위험으로 평가한다.

====================================
아이디어 5
====================================

기업/프로젝트 관련 갈등이나 악재가
실제로 확인되는 경우만 반영한다.

====================================
아이디어 6
====================================

신제품, 실적, 출시, 계약 등
확인된 촉매가 있는지 확인한다.

====================================
아이디어 7
====================================

심각한 기술적/보안적 위험이
실제 뉴스나 공식 자료로 확인되는 경우
급락 위험 점수를 높인다.

====================================
아이디어 8
====================================

개발활동 감소나 성장동력 약화를 검토한다.

====================================
아이디어 9
====================================

악재 이후 실제 가격이 안정되고
거래량이 회복되는 종목을
역발상 반등 후보로 검토한다.

====================================
아이디어 10
====================================

두 관점으로 분석한다.

Agent A:
가격/기술/개발활동

Agent B:
뉴스/시장심리/대중 관심

두 관점이 동시에 긍정적이면
상승 신뢰도를 높인다.

====================================
시장 데이터
====================================

{market_text}

====================================
후보 데이터
====================================

{candidate_text}

====================================
출력
====================================

반드시 상위 10개만 선정한다.

각 종목에 대해:

순위
티커
기업명
현재가격
종합점수 100점
상승 시나리오 점수 100점
급락 위험 점수 100점
소형주/중형주/대형주
핵심 이유
주요 촉매
주의할 위험
반등 가능성

'반등 가능성'은
실제 통계적 확률이라고 표현하지 말고
'모델 시나리오 점수'라고 표현한다.

마지막에는 반드시:

🔥 오늘 가장 강한 3개
⚡ 소형주 고위험 고수익 후보 3개
🚨 급락 위험 종목 3개

를 별도로 표시한다.

절대로
'무조건 상승'
'100% 상승'
'확실한 급등'
같은 표현을 사용하지 않는다.

JSON을 만들 필요는 없다.
사람이 읽기 좋은 한국어 보고서를 작성하라.
"""

    return prompt


def call_gemini(prompt):

    if not GEMINI_API_KEY:

        return None, "GEMINI_API_KEY 없음"

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )

    headers = {

        "Content-Type":
            "application/json",

        "x-goog-api-key":
            GEMINI_API_KEY,

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

        "generationConfig": {

            "temperature": 0.2,

            "maxOutputTokens": 7000

        }

    }

    for attempt in range(3):

        try:

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=60
            )

            if response.status_code == 200:

                data = response.json()

                candidates = data.get(
                    "candidates",
                    []
                )

                if not candidates:

                    return None, (
                        "Gemini 응답 후보 없음"
                    )

                text = (
                    candidates[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )

                if text:

                    return text, None

                return None, (
                    "Gemini 텍스트 응답 없음"
                )

            # quota
            if response.status_code == 429:

                print(
                    "Gemini 429 RESOURCE_EXHAUSTED"
                )

                # 재시도
                if attempt < 2:

                    time.sleep(
                        10 * (attempt + 1)
                    )

                    continue

                return None, (
                    "429 RESOURCE_EXHAUSTED"
                )

            try:

                error = response.json()

            except Exception:

                error = response.text

            return None, (
                f"Gemini API 오류 "
                f"{response.status_code}: "
                f"{error}"
            )

        except Exception as e:

            if attempt < 2:

                time.sleep(5)

                continue

            return None, str(e)

    return None, "Gemini 요청 실패"


# =========================================================
# Gemini 실패 시 사용할 기본 보고서
# =========================================================

def create_fallback_report(
    candidates,
    market
):

    candidates = sorted(
        candidates,
        key=lambda x:
        x["pre_score"],
        reverse=True
    )[:TOP_N]

    lines = []

    lines.append(
        "⚠️ Gemini AI 분석은 현재 사용량 제한으로 "
        "실행되지 않았습니다."
    )

    lines.append("")

    lines.append(
        "📊 아래 순위는 최신 시장 데이터 기반 "
        "자동 점수입니다."
    )

    lines.append(
        "※ AI 검증 완료 추천이 아닙니다."
    )

    lines.append("")

    for i, item in enumerate(
        candidates,
        1
    ):

        lines.append(
            f"{i}️⃣ {item['ticker']} "
            f"({item['sector']})"
        )

        lines.append(
            f"종합 데이터 점수: "
            f"{item['pre_score']}/100"
        )

        lines.append(
            f"현재가: "
            f"${item['price']:.2f}"
        )

        lines.append(
            f"일간: "
            f"{item['day_change']:+.2f}% | "
            f"주간: "
            f"{item['week_change']:+.2f}%"
        )

        lines.append(
            f"거래량: "
            f"{item['volume_ratio']:.1f}배"
        )

        lines.append("")

    return "\n".join(lines)


# =========================================================
# Telegram 메시지 길이 분할
# =========================================================

def split_message(text, max_length=3900):

    if len(text) <= max_length:

        return [text]

    chunks = []

    current = ""

    for line in text.split("\n"):

        if len(current) + len(line) + 1 > max_length:

            chunks.append(current)

            current = line

        else:

            current += (
                ("\n" if current else "")
                + line
            )

    if current:

        chunks.append(current)

    return chunks


# =========================================================
# 메인
# =========================================================

def main():

    start = now_kst()

    print(
        "=" * 60
    )

    print(
        "미국 주식 전략 레이더 시작"
    )

    print(
        start.strftime(
            "%Y-%m-%d %H:%M:%S KST"
        )
    )

    print(
        "=" * 60
    )

    # -----------------------------------------------------
    # 1. 시장
    # -----------------------------------------------------

    print(
        "\n[1/5] 시장 데이터 수집..."
    )

    market = get_market_data()

    # -----------------------------------------------------
    # 2. 종목 데이터
    # -----------------------------------------------------

    print(
        "\n[2/5] 종목 데이터 수집..."
    )

    raw_candidates = []

    for ticker in TICKERS:

        print(
            f"  분석 중: {ticker}"
        )

        data = get_stock_data(
            ticker
        )

        if not data:

            continue

        news = get_news(
            ticker,
            data["name"]
        )

        github = get_github_activity(
            ticker
        )

        pre_score = calculate_pre_score(
            data,
            len(news),
            github
        )

        data["news"] = news

        data["github"] = github

        data["pre_score"] = pre_score

        raw_candidates.append(
            data
        )

        time.sleep(0.15)

    if not raw_candidates:

        error_message = (
            "🚨 [미국 주식 전략 레이더]\n\n"
            "주식 데이터를 가져오지 못했습니다.\n\n"
            "Yahoo Finance 데이터 수집 상태를 "
            "확인해주세요."
        )

        send_telegram(
            error_message
        )

        return

    # -----------------------------------------------------
    # 3. 1차 후보 압축
    # -----------------------------------------------------

    print(
        "\n[3/5] 후보 종목 압축..."
    )

    raw_candidates.sort(
        key=lambda x:
        x["pre_score"],
        reverse=True
    )

    candidates = raw_candidates[
        :AI_CANDIDATES
    ]

    # Gemini용 데이터 축소
    ai_data = []

    for item in candidates:

        news_titles = [
            x["title"]
            for x in item["news"][:5]
        ]

        ai_data.append({

            "ticker":
                item["ticker"],

            "name":
                item["name"],

            "sector":
                item["sector"],

            "price":
                round(
                    item["price"],
                    2
                ),

            "day_change":
                round(
                    item["day_change"],
                    2
                ),

            "week_change":
                round(
                    item["week_change"],
                    2
                ),

            "month_change":
                round(
                    item["month_change"],
                    2
                ),

            "volume_ratio":
                round(
                    item["volume_ratio"],
                    2
                ),

            "rsi":
                round(
                    item["rsi"],
                    1
                ),

            "from_high":
                round(
                    item["from_high"],
                    2
                ),

            "market_cap":
                item["market_cap"],

            "short_ratio":
                item["short_ratio"],

            "pre_score":
                item["pre_score"],

            "news":
                news_titles,

            "github":
                item["github"],

        })

    # -----------------------------------------------------
    # 4. Gemini 분석
    # -----------------------------------------------------

    print(
        "\n[4/5] Gemini AI 분석..."
    )

    prompt = build_gemini_prompt(
        ai_data,
        market
    )

    ai_report, ai_error = call_gemini(
        prompt
    )

    # -----------------------------------------------------
    # 5. 결과
    # -----------------------------------------------------

    if ai_report:

        print(
            "Gemini 분석 성공"
        )

        header = (
            "🚨 [미국 주식 전략 레이더]\n\n"
            f"⏰ {start.strftime('%Y-%m-%d %H:%M:%S')} KST\n\n"
        )

        footer = (
            "\n\n━━━━━━━━━━━━━━\n"
            "⚠️ 투자 참고용\n"
            "━━━━━━━━━━━━━━\n"
            "본 분석은 최신 공개 데이터를 기반으로 "
            "자동 생성된 정보입니다.\n"
            "모델 점수는 실제 수익률이나 당첨 확률을 "
            "보장하지 않습니다.\n"
            "특히 소형주는 변동성과 손실 위험이 "
            "높을 수 있습니다.\n"
        )

        final_message = (
            header
            + ai_report
            + footer
        )

    else:

        print(
            "Gemini 실패:",
            ai_error
        )

        final_message = (
            "🚨 [미국 주식 전략 레이더]\n\n"
            f"⏰ {start.strftime('%Y-%m-%d %H:%M:%S')} KST\n\n"
            + create_fallback_report(
                candidates,
                market
            )
            + "\n\n"
            "━━━━━━━━━━━━━━\n"
            "Gemini 상태\n"
            "━━━━━━━━━━━━━━\n"
            f"{ai_error}\n\n"
            "※ AI 검증이 완료되지 않았으므로 "
            "자동 점수만 참고하세요."
        )

    # -----------------------------------------------------
    # Telegram
    # -----------------------------------------------------

    print(
        "\n[5/5] Telegram 전송..."
    )

    chunks = split_message(
        final_message
    )

    success = True

    for chunk in chunks:

        if not send_telegram(
            chunk
        ):

            success = False

        time.sleep(1)

    if success:

        print(
            "\n전송 완료!"
        )

    else:

        print(
            "\nTelegram 전송 일부 실패"
        )

    print(
        "=" * 60
    )


if __name__ == "__main__":

    main()
