import os
import json
import time
import requests
from datetime import datetime, timezone, timedelta

# ============================================================
# 미국 주식 전략 레이더
# Gemini + Google Search + Yahoo Finance + GitHub + Telegram
#
# 실행:
# GitHub Actions에서 1시간마다 실행
#
# 필요한 GitHub Secrets:
#
# GEMINI_API_KEY
# TELEGRAM_BOT_TOKEN
# TELEGRAM_CHAT_ID
#
# 선택:
# GITHUB_TOKEN
#
# ============================================================


# ============================================================
# 환경변수
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()


# ============================================================
# 기본 설정
# ============================================================

KST = timezone(timedelta(hours=9))

# Google이 현재 권장하는 최신 Flash 계열
GEMINI_MODEL = "gemini-3.6-flash"

# 최대 분석 종목
MAX_CANDIDATES = 40

# 최종 추천
TOP_N = 10

# Yahoo Finance
YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}


# ============================================================
# 시간
# ============================================================

def now_kst():
    return datetime.now(KST)


def time_text():
    return now_kst().strftime("%Y-%m-%d %H:%M:%S KST")


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram 설정이 없습니다.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Telegram 메시지 최대 길이 대비
    chunks = []

    while len(message) > 3900:
        cut = message.rfind("\n", 0, 3900)

        if cut < 1000:
            cut = 3900

        chunks.append(message[:cut])
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
                print("Telegram 오류:", response.text)
                success = False

        except Exception as e:
            print("Telegram 전송 오류:", e)
            success = False

    return success


# ============================================================
# Yahoo Finance
# ============================================================

def yahoo_quote(symbol):
    """
    Yahoo Finance chart API에서
    최근 가격 / 거래량 / 기간 수익률을 가져옵니다.
    """

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?range=1mo&interval=1d"
    )

    try:
        r = requests.get(
            url,
            headers=YAHOO_HEADERS,
            timeout=15
        )

        if r.status_code != 200:
            return None

        data = r.json()

        result = data.get("chart", {}).get("result")

        if not result:
            return None

        result = result[0]

        meta = result.get("meta", {})
        quote = result.get("indicators", {}).get("quote", [{}])[0]

        closes = quote.get("close", [])
        volumes = quote.get("volume", [])

        closes = [
            float(x) for x in closes
            if x is not None
        ]

        volumes = [
            float(x) for x in volumes
            if x is not None
        ]

        if len(closes) < 2:
            return None

        price = meta.get("regularMarketPrice")

        if price is None:
            price = closes[-1]

        price = float(price)

        # 일간
        daily_change = 0

        if len(closes) >= 2 and closes[-2] != 0:
            daily_change = (
                (closes[-1] / closes[-2]) - 1
            ) * 100

        # 5거래일
        weekly_change = 0

        if len(closes) >= 6 and closes[-6] != 0:
            weekly_change = (
                (closes[-1] / closes[-6]) - 1
            ) * 100

        # 20거래일
        monthly_change = 0

        if len(closes) >= 21 and closes[-21] != 0:
            monthly_change = (
                (closes[-1] / closes[-21]) - 1
            ) * 100

        volume_ratio = 1

        if len(volumes) >= 21:

            recent_volume = volumes[-1]

            previous_volumes = volumes[-21:-1]

            previous_volumes = [
                x for x in previous_volumes
                if x > 0
            ]

            if previous_volumes:

                avg_volume = (
                    sum(previous_volumes)
                    / len(previous_volumes)
                )

                if avg_volume > 0:
                    volume_ratio = (
                        recent_volume / avg_volume
                    )

        return {
            "symbol": symbol,
            "price": price,
            "daily_change": daily_change,
            "weekly_change": weekly_change,
            "monthly_change": monthly_change,
            "volume_ratio": volume_ratio
        }

    except Exception as e:

        print(f"Yahoo 오류 {symbol}:", e)

        return None


# ============================================================
# GitHub
# ============================================================

def github_headers():

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "stock-strategy-radar"
    }

    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    return headers


def github_search_repositories(keyword):

    url = "https://api.github.com/search/repositories"

    params = {
        "q": keyword,
        "sort": "stars",
        "order": "desc",
        "per_page": 5
    }

    try:

        r = requests.get(
            url,
            headers=github_headers(),
            params=params,
            timeout=15
        )

        if r.status_code != 200:
            return []

        data = r.json()

        return data.get("items", [])

    except Exception as e:

        print("GitHub 검색 오류:", e)

        return []


def github_repo_activity(repo):

    """
    프로젝트의 개발활동을 간단하게 평가합니다.
    """

    full_name = repo.get("full_name")

    if not full_name:
        return None

    url = (
        f"https://api.github.com/repos/"
        f"{full_name}/commits"
    )

    params = {
        "per_page": 30
    }

    try:

        r = requests.get(
            url,
            headers=github_headers(),
            params=params,
            timeout=15
        )

        if r.status_code != 200:
            return None

        commits = r.json()

        return {
            "repo": full_name,
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "open_issues": repo.get("open_issues_count", 0),
            "recent_commits": len(commits)
        }

    except Exception as e:

        print("GitHub activity 오류:", e)

        return None


# ============================================================
# 종목 후보군
# ============================================================

def build_stock_universe():

    """
    대형주만 고르지 않도록
    대형 / 중형 / 소형 / AI / 반도체 / 우주 / 핀테크
    등을 혼합합니다.

    아래 종목들은 '분석 후보군'입니다.
    최종 추천은 데이터와 Gemini 검증 후 결정합니다.
    """

    symbols = [

        # -----------------------
        # 대형 AI / 반도체
        # -----------------------

        "NVDA",
        "AMD",
        "AVGO",
        "TSM",
        "MU",
        "INTC",
        "QCOM",
        "AMAT",
        "LRCX",
        "ASML",
        "ANET",

        # -----------------------
        # AI / 데이터센터
        # -----------------------

        "CRWV",
        "NBIS",
        "IREN",
        "SMCI",
        "VRT",
        "EQIX",
        "DLR",
        "CIFR",
        "CORZ",

        # -----------------------
        # 성장주
        # -----------------------

        "PLTR",
        "TEM",
        "SOUN",
        "AI",
        "BBAI",
        "PATH",
        "RXRX",
        "IONQ",
        "QBTS",
        "RGTI",

        # -----------------------
        # 우주
        # -----------------------

        "LUNR",
        "RKLB",
        "ASTS",

        # -----------------------
        # 전기차 / 미래산업
        # -----------------------

        "TSLA",
        "RIVN",
        "LCID",

        # -----------------------
        # 핀테크 / 결제
        # -----------------------

        "SOFI",
        "HOOD",
        "AFRM",
        "NU",

        # -----------------------
        # 바이오 / 헬스케어
        # -----------------------

        "CRSP",
        "EDIT",
        "BEAM",
        "VKTX",
        "HIMS",

        # -----------------------
        # 에너지
        # -----------------------

        "OKLO",
        "SMR",
        "CEG",
        "CCJ",

        # -----------------------
        # 기타
        # -----------------------

        "MARA",
        "RIOT",
        "COIN",
        "MSTR"
    ]

    return list(dict.fromkeys(symbols))


# ============================================================
# 기술적 점수
# ============================================================

def calculate_market_score(data):

    """
    주가 데이터만으로 0~100 점수를 계산합니다.

    이것은 AI 분석 점수가 아닙니다.
    """

    score = 0

    daily = data["daily_change"]
    weekly = data["weekly_change"]
    monthly = data["monthly_change"]
    volume = data["volume_ratio"]

    # 거래량
    if volume >= 3:
        score += 30
    elif volume >= 2:
        score += 25
    elif volume >= 1.5:
        score += 20
    elif volume >= 1.2:
        score += 10

    # 단기 모멘텀
    if daily > 15:
        score += 20
    elif daily > 8:
        score += 16
    elif daily > 3:
        score += 12
    elif daily > 0:
        score += 6

    # 주간 모멘텀
    if weekly > 20:
        score += 20
    elif weekly > 10:
        score += 15
    elif weekly > 5:
        score += 10
    elif weekly > 0:
        score += 5

    # 월간 추세
    if monthly > 30:
        score += 15
    elif monthly > 15:
        score += 12
    elif monthly > 5:
        score += 8
    elif monthly > 0:
        score += 4

    # 지나치게 오른 종목은 추격 위험
    if daily >= 30:
        score -= 10

    if daily >= 50:
        score -= 15

    return max(0, min(100, score))


# ============================================================
# Gemini Interactions API
# ============================================================

def gemini_analyze(prompt):

    """
    Google Gemini Interactions API

    Google Search grounding을 이용하여
    최신 뉴스/시장 정보를 확인합니다.
    """

    if not GEMINI_API_KEY:

        return {
            "success": False,
            "reason": "GEMINI_API_KEY가 없습니다."
        }

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/interactions"
    )

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "model": GEMINI_MODEL,
        "input": prompt,

        "tools": [
            {
                "type": "google_search"
            }
        ],

        "store": False
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=90
        )

        print(
            "Gemini 상태코드:",
            response.status_code
        )

        # -------------------------
        # 성공
        # -------------------------

        if response.status_code == 200:

            data = response.json()

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
            outputs = data.get("outputs", [])

            texts = []

            for item in outputs:

                if isinstance(item, dict):

                    text = item.get("text")

                    if text:
                        texts.append(text)

            if texts:

                return {
                    "success": True,
                    "text": "\n".join(texts)
                }

            return {
                "success": False,
                "reason": "Gemini 응답 내용이 없습니다."
            }

        # -------------------------
        # 429
        # -------------------------

        if response.status_code == 429:

            return {
                "success": False,
                "quota": True,
                "reason": (
                    "Gemini API quota/rate limit에 "
                    "도달했습니다."
                )
            }

        # -------------------------
        # 404
        # -------------------------

        if response.status_code == 404:

            return {
                "success": False,
                "reason": (
                    "Gemini 모델/API endpoint를 "
                    "찾을 수 없습니다."
                )
            }

        # -------------------------
        # 기타
        # -------------------------

        try:
            err = response.json()
        except:
            err = response.text

        return {
            "success": False,
            "reason": f"Gemini 오류 {response.status_code}: {err}"
        }

    except Exception as e:

        return {
            "success": False,
            "reason": f"Gemini 요청 오류: {e}"
        }


# ============================================================
# Gemini 프롬프트
# ============================================================

def build_gemini_prompt(stock_data):

    stock_json = json.dumps(
        stock_data,
        ensure_ascii=False,
        indent=2
    )

    prompt = f"""
당신은 미국 주식시장의 시니어 전략 분석가입니다.

목표:
오늘부터 향후 24~72시간 동안
반등/추가상승 가능성이 상대적으로 높은 미국 주식
10개를 선정하세요.

중요:
절대로 확인되지 않은 뉴스나 숫자를 만들어내지 마세요.

반드시 Google Search를 이용해 최신 정보를 검증하세요.

현재 시각:
{time_text()}

==================================================
분석 후보 데이터
==================================================

{stock_json}

==================================================
핵심 분석 원칙
==================================================

1. 대형주만 추천하지 마세요.

대형주:
NVDA, AMD, TSM, AVGO 등

중형주:
ANET, SMCI, LUNR, RKLB 등

소형/고변동 성장주:
SOUN, BBAI, IONQ, QBTS, RGTI 등

후보군 전체를 비교하세요.

단, 소형주라고 무조건 높은 점수를 주지 마세요.

==================================================
2. 최신 뉴스 검증
==================================================

각 종목에 대해 최근 24~48시간의
중요 뉴스를 검색하세요.

확인할 것:

- 실적
- 가이던스
- 신규 계약
- AI 투자
- 반도체 수요
- 정부 정책
- 금리
- FDA
- 우주산업
- 데이터센터
- IPO
- 증자
- 전환사채
- 내부자 매도
- 공매도
- 소송
- 규제
- 악재

확인되지 않은 뉴스는 사용하지 마세요.

==================================================
3. 기술적 모멘텀
==================================================

거래량 증가

일간 상승률

주간 상승률

월간 추세

급등 후 과열 여부

눌림목 가능성

지지선/저항선

을 고려하세요.

==================================================
4. 급등 선행 아이디어
==================================================

GitHub 개발활동이 실제로 존재하는
기술기업/프로젝트라면 다음을 조사하세요.

- 최근 커밋
- 개발활동 증가
- Release
- PR
- Issue
- 핵심 개발자 활동

개발활동 증가 + 대중 관심 낮음

이라면

"잠재적 기술 모멘텀"

으로 평가하세요.

단순히 GitHub가 존재한다는 이유만으로
주가 상승을 예측하지 마세요.

==================================================
5. GitHub Dumping Radar
==================================================

다음 키워드가 발견되면 위험 점수를 높이세요.

exploit
emergency
pause
unauthorized
overflow
rug pull
freeze
hack
security
rollback

특히 실제 보안문제와 관련된 내용이면
급락 위험을 높이세요.

==================================================
6. Developer Migration
==================================================

개발자 활동 증가,
새로운 Release,
Contributor 증가,
Fork 증가 등이 확인되면
기술 모멘텀으로 참고하세요.

하지만 GitHub 데이터만으로
주가 급등을 단정하지 마세요.

==================================================
7. Fake Hype
==================================================

뉴스와 검색량은 폭발하는데

실제 개발활동

실적

매출

계약

제품

등의 근거가 부족하면

"과열 위험"

으로 평가하세요.

==================================================
8. Governance / Developer Conflict
==================================================

다음 키워드를 확인하세요.

fork
abandon
rejected
disagree
scam
shutdown
delay

심각한 개발자 갈등이나 프로젝트 중단이
확인되면 급락 위험을 높이세요.

==================================================
9. Release / Upgrade
==================================================

신제품

신규 플랫폼

신규 Release

대형 업그레이드

상장

파트너십

등이 실제로 확인되면
촉매로 평가하세요.

==================================================
10. Panic + Recovery
==================================================

악재 뉴스가 발생했지만

회사 공식 발표

제품 업데이트

보안 패치

실적

계약

등으로 문제가 해결된 것이 확인되면

"반등 후보"

로 평가하세요.

==================================================
11. Agent A
==================================================

GitHub / 기술 / 사업 데이터를
엄격하게 평가하세요.

==================================================
12. Agent B
==================================================

Google Search / 뉴스 / 시장 심리를
평가하세요.

==================================================
13. Consensus
==================================================

Agent A와 Agent B의 결과를 합쳐

최종 점수를 만드세요.

==================================================
점수
==================================================

반등/추가상승 모멘텀:

0~100

급락 위험:

0~100

추격매수 위험:

0~100

데이터 신뢰도:

0~100

==================================================
중요
==================================================

"성공확률"이라는 표현 대신
"분석 점수"를 사용하세요.

실제 미래 수익률을 보장하지 마세요.

최신 정보가 확인되지 않은 종목은
TOP 10에서 제외하세요.

==================================================
출력 형식
==================================================

반드시 다음 JSON 형태로 답하세요.

{{
    "market_summary": "오늘 시장 핵심 3줄",
    "top10": [
        {{
            "rank": 1,
            "symbol": "종목코드",
            "company": "회사명",
            "category": "대형/중형/소형",
            "current_price": "확인된 가격",
            "momentum_score": 0,
            "downside_risk": 0,
            "chase_risk": 0,
            "confidence": 0,
            "action": "관심/눌림목 관심/주의",
            "reason": "핵심 이유",
            "catalyst": "상승 촉매",
            "risk": "주요 위험",
            "news_verified": true
        }}
    ],
    "small_cap_pick": {{
        "symbol": "",
        "reason": "",
        "risk": ""
    }},
    "ipo_watch": {{
        "symbol": "",
        "reason": "",
        "risk": ""
    }},
    "danger_top3": [
        {{
            "symbol": "",
            "risk_score": 0,
            "reason": ""
        }}
    ]
}}

JSON 이외의 문장은 출력하지 마세요.
"""

    return prompt


# ============================================================
# JSON 추출
# ============================================================

def extract_json(text):

    if not text:
        return None

    text = text.strip()

    # ```json 제거
    if "```json" in text:
        text = text.replace("```json", "")

    if "```" in text:
        text = text.replace("```", "")

    text = text.strip()

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        return None

    text = text[start:end + 1]

    try:

        return json.loads(text)

    except Exception as e:

        print("JSON 파싱 오류:", e)

        return None


# ============================================================
# Telegram 보고서
# ============================================================

def format_report(ai_data, market_data):

    lines = []

    lines.append("🚨 미국 주식 전략 레이더")
    lines.append("")
    lines.append(f"⏰ {time_text()}")
    lines.append("")

    lines.append("📌 오늘의 시장 핵심")

    market_summary = ai_data.get(
        "market_summary",
        "최신 시장 요약 없음"
    )

    lines.append(market_summary)

    lines.append("")
    lines.append("🔥 반등/추가상승 관심 TOP 10")
    lines.append("")

    top10 = ai_data.get("top10", [])

    for item in top10[:10]:

        rank = item.get("rank", "?")
        symbol = item.get("symbol", "?")
        company = item.get("company", "")
        category = item.get("category", "")

        price = item.get(
            "current_price",
            "확인불가"
        )

        momentum = item.get(
            "momentum_score",
            0
        )

        downside = item.get(
            "downside_risk",
            0
        )

        chase = item.get(
            "chase_risk",
            0
        )

        confidence = item.get(
            "confidence",
            0
        )

        action = item.get(
            "action",
            ""
        )

        reason = item.get(
            "reason",
            ""
        )

        catalyst = item.get(
            "catalyst",
            ""
        )

        risk = item.get(
            "risk",
            ""
        )

        lines.append(
            f"{rank}️⃣ {symbol} {company}"
        )

        lines.append(
            f"분류: {category}"
        )

        lines.append(
            f"현재가: {price}"
        )

        lines.append(
            f"📈 모멘텀: {momentum}/100"
        )

        lines.append(
            f"⚠️ 급락위험: {downside}/100"
        )

        lines.append(
            f"🔥 추격위험: {chase}/100"
        )

        lines.append(
            f"🧠 데이터 신뢰도: {confidence}/100"
        )

        lines.append(
            f"🎯 전략: {action}"
        )

        lines.append(
            f"이유: {reason}"
        )

        lines.append(
            f"촉매: {catalyst}"
        )

        lines.append(
            f"위험: {risk}"
        )

        lines.append("")

    # 소형주
    small = ai_data.get(
        "small_cap_pick",
        {}
    )

    if small:

        lines.append("💎 오늘의 소형주 관심 후보")

        lines.append(
            f"⭐ {small.get('symbol', '없음')}"
        )

        lines.append(
            small.get(
                "reason",
                ""
            )
        )

        lines.append(
            f"⚠️ {small.get('risk', '')}"
        )

        lines.append("")

    # IPO
    ipo = ai_data.get(
        "ipo_watch",
        {}
    )

    if ipo:

        lines.append("🚀 IPO / 상장예정 관심")

        lines.append(
            f"⭐ {ipo.get('symbol', '없음')}"
        )

        lines.append(
            ipo.get(
                "reason",
                ""
            )
        )

        lines.append(
            f"⚠️ {ipo.get('risk', '')}"
        )

        lines.append("")

    # 급락
    danger = ai_data.get(
        "danger_top3",
        []
    )

    if danger:

        lines.append("🚨 급락 위험 TOP 3")

        for i, item in enumerate(
            danger[:3],
            1
        ):

            lines.append(
                f"{i}. "
                f"{item.get('symbol', '')} "
                f"위험도 "
                f"{item.get('risk_score', 0)}/100"
            )

            lines.append(
                item.get(
                    "reason",
                    ""
                )
            )

        lines.append("")

    # 자동 데이터
    lines.append("━━━━━━━━━━━━━━")
    lines.append("📊 자동 시장 데이터")
    lines.append("━━━━━━━━━━━━━━")

    for data in market_data[:10]:

        lines.append(
            f"{data['symbol']} "
            f"${data['price']:.2f} | "
            f"일 {data['daily_change']:+.2f}% | "
            f"주 {data['weekly_change']:+.2f}% | "
            f"거래량 {data['volume_ratio']:.1f}배"
        )

    lines.append("")

    lines.append(
        "⚠️ 본 분석은 투자 판단을 위한 참고자료이며 "
        "수익이나 급등을 보장하지 않습니다."
    )

    return "\n".join(lines)


# ============================================================
# Gemini 실패 보고서
# ============================================================

def quota_report(reason):

    return f"""
🚨 미국 주식 전략 레이더

⏰ {time_text()}

⚠️ Gemini 최신 정보 검증 실패

이번 분석에서는
최신 뉴스/시장정보 검증이 완료되지 않았습니다.

따라서 확인되지 않은 종목이나
가짜 AI 분석 점수를 생성하지 않았습니다.

원인:
{reason}

━━━━━━━━━━━━━━

📌 자동 데이터 수집 자체는 계속 가능합니다.

다음 실행에서 Gemini API가 정상화되면
다시 전체 분석을 수행합니다.

※ API 오류 상태에서는
임의의 종목 추천을 생성하지 않습니다.
"""


# ============================================================
# 메인
# ============================================================

def main():

    print("=" * 60)
    print("미국 주식 전략 레이더 시작")
    print(time_text())
    print("=" * 60)

    # --------------------------------------------------------
    # API 설정 확인
    # --------------------------------------------------------

    missing = []

    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:

        message = (
            "🚨 미국 주식 전략 레이더 설정 오류\n\n"
            "다음 GitHub Secrets가 없습니다:\n\n"
            + "\n".join(
                f"• {x}" for x in missing
            )
        )

        send_telegram(message)

        print(message)

        return

    # --------------------------------------------------------
    # 후보군
    # --------------------------------------------------------

    universe = build_stock_universe()

    print(
        f"후보 종목 {len(universe)}개 수집"
    )

    # --------------------------------------------------------
    # 시장 데이터
    # --------------------------------------------------------

    market_data = []

    for symbol in universe:

        data = yahoo_quote(symbol)

        if data:

            data["market_score"] = (
                calculate_market_score(data)
            )

            market_data.append(data)

            print(
                symbol,
                data["price"],
                data["daily_change"],
                data["volume_ratio"]
            )

        time.sleep(0.15)

    if not market_data:

        message = (
            "🚨 미국 주식 전략 레이더\n\n"
            "시장 데이터를 가져오지 못했습니다.\n"
            "이번 실행에서는 추천을 생성하지 않습니다."
        )

        send_telegram(message)

        return

    # --------------------------------------------------------
    # 시장 데이터 우선순위
    # --------------------------------------------------------

    market_data.sort(
        key=lambda x: x["market_score"],
        reverse=True
    )

    selected = market_data[:MAX_CANDIDATES]

    # --------------------------------------------------------
    # Gemini 입력용 데이터
    # --------------------------------------------------------

    gemini_input = []

    for data in selected:

        gemini_input.append({

            "symbol": data["symbol"],

            "price": round(
                data["price"],
                2
            ),

            "daily_change": round(
                data["daily_change"],
                2
            ),

            "weekly_change": round(
                data["weekly_change"],
                2
            ),

            "monthly_change": round(
                data["monthly_change"],
                2
            ),

            "volume_ratio": round(
                data["volume_ratio"],
                2
            ),

            "automatic_market_score": (
                data["market_score"]
            )
        })

    # --------------------------------------------------------
    # Gemini
    # --------------------------------------------------------

    print("Gemini 최신 정보 검증 시작")

    prompt = build_gemini_prompt(
        gemini_input
    )

    ai_result = gemini_analyze(
        prompt
    )

    # --------------------------------------------------------
    # Gemini 실패
    # --------------------------------------------------------

    if not ai_result.get("success"):

        reason = ai_result.get(
            "reason",
            "알 수 없는 오류"
        )

        message = quota_report(
            reason
        )

        send_telegram(message)

        print(message)

        return

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    ai_data = extract_json(
        ai_result.get("text", "")
    )

    if not ai_data:

        message = (
            "🚨 미국 주식 전략 레이더\n\n"
            "Gemini 응답은 성공했지만 "
            "분석 결과 JSON 검증에 실패했습니다.\n\n"
            "이번 실행에서는 "
            "추천 종목을 전송하지 않았습니다."
        )

        send_telegram(message)

        return

    # --------------------------------------------------------
    # 결과 검증
    # --------------------------------------------------------

    top10 = ai_data.get(
        "top10",
        []
    )

    verified_top10 = []

    valid_symbols = {
        x["symbol"]
        for x in market_data
    }

    for item in top10:

        symbol = item.get(
            "symbol",
            ""
        ).upper()

        # 실제 데이터에 존재하는 종목만
        if symbol not in valid_symbols:
            continue

        # 뉴스 검증
        if item.get(
            "news_verified",
            False
        ) is not True:

            continue

        # 점수 정상화
        for key in [
            "momentum_score",
            "downside_risk",
            "chase_risk",
            "confidence"
        ]:

            try:

                value = float(
                    item.get(
                        key,
                        0
                    )
                )

                value = max(
                    0,
                    min(
                        100,
                        value
                    )
                )

                item[key] = round(
                    value
                )

            except:

                item[key] = 0

        verified_top10.append(
            item
        )

    # --------------------------------------------------------
    # 검증된 종목이 부족하면
    # 임의로 채우지 않음
    # --------------------------------------------------------

    if len(verified_top10) < 3:

        message = (
            "🚨 미국 주식 전략 레이더\n\n"
            "Gemini 응답은 있었지만\n"
            "최신 정보 검증을 통과한 종목이 "
            "3개 미만입니다.\n\n"
            "확인되지 않은 종목을 임의로 추가하지 "
            "않았습니다.\n\n"
            f"검증 통과: {len(verified_top10)}개"
        )

        send_telegram(message)

        return

    ai_data["top10"] = verified_top10[:TOP_N]

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    report = format_report(
        ai_data,
        market_data
    )

    send_telegram(
        report
    )

    print("=" * 60)
    print("분석 완료")
    print("=" * 60)


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    main()
