import os
import re
import json
import time
import requests
import xml.etree.ElementTree as ET

from datetime import datetime, timezone, timedelta

from google import genai
from google.genai import types


# ============================================================
# 미국 주식 전략 레이더
#
# 목적:
# 1시간마다 최신 미국 증시 정보를 수집
# 10개의 가장 유망한 종목 선정
#
# 분석:
# - 대형주
# - 중형주
# - 소형주
# - 급등 후보
# - 반등 후보
# - 급락 위험
# - AI/반도체
# - GitHub 개발활동
# - 뉴스 모멘텀
# - 기술적/심리적 정보
#
# 주의:
# 투자수익을 보장하지 않음.
# "확률"은 실제 통계적 승률이 아니라
# 모델의 상대적 신뢰도 점수임.
# ============================================================


# ============================================================
# ENV
# ============================================================

GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY",
    ""
).strip()

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    ""
).strip()

TELEGRAM_CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID",
    ""
).strip()

GITHUB_TOKEN = os.environ.get(
    "GITHUB_TOKEN",
    ""
).strip()


# 현재 안정적인 Gemini Flash-Lite
MODEL_NAME = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite"
)


# ============================================================
# 시간
# ============================================================

KST = timezone(
    timedelta(hours=9)
)


# ============================================================
# 뉴스 검색어
# ============================================================

NEWS_QUERIES = [

    # 시장
    "US stocks S&P 500 Nasdaq Dow futures",

    # 금리
    "Federal Reserve Fed interest rates Treasury yields",

    # 물가
    "US CPI inflation PPI",

    # 고용
    "US jobs employment payroll unemployment",

    # AI
    "AI stocks artificial intelligence data center",

    # 반도체
    "semiconductor Nvidia AMD TSMC Micron Broadcom",

    # 소형주
    "small cap stocks surge US",

    # 급등
    "small cap stock surges contract earnings",

    # 급락
    "stock crashes warning investigation downgrade",

    # 실적
    "US stocks earnings surprise guidance",

    # IPO
    "US IPO upcoming IPO Nasdaq NYSE",

    # 신규상장
    "newly listed stocks Nasdaq NYSE",

    # 기술
    "technology stocks rebound",

    # 에너지
    "oil energy stocks WTI Brent",

]


# ============================================================
# GitHub 검색 키워드
# ============================================================

GITHUB_SEARCH_QUERIES = [

    "AI",
    "artificial intelligence",
    "machine learning",
    "semiconductor",
    "GPU",
    "data center",
    "cloud",
    "robotics",
    "cybersecurity",
    "blockchain",

]


# ============================================================
# 위험 키워드
# ============================================================

DANGER_KEYWORDS = [

    "exploit",
    "hack",
    "hacked",
    "breach",
    "emergency",
    "rollback",
    "vulnerability",
    "critical",
    "pause",
    "unauthorized",
    "overflow",
    "security issue",
    "investigation",
    "lawsuit",
    "fraud",
    "accounting",
    "bankruptcy",
    "delisting",
    "warning",
    "downgrade",
    "miss",

]


# ============================================================
# 상승 키워드
# ============================================================

BULLISH_KEYWORDS = [

    "beat",
    "beats",
    "strong earnings",
    "raised guidance",
    "contract",
    "partnership",
    "ai",
    "artificial intelligence",
    "data center",
    "chip",
    "semiconductor",
    "approval",
    "launch",
    "record revenue",
    "record sales",
    "buyback",
    "upgrade",
    "acquisition",
    "government contract",
    "order",
    "backlog",

]


# ============================================================
# Telegram
# ============================================================

def split_message(
    text,
    max_length=3900
):

    if len(text) <= max_length:
        return [text]

    chunks = []

    current = ""

    for line in text.split("\n"):

        candidate = (
            current + "\n" + line
            if current
            else line
        )

        if len(candidate) <= max_length:

            current = candidate

        else:

            if current:
                chunks.append(
                    current
                )

            current = line

    if current:
        chunks.append(
            current
        )

    return chunks


def send_telegram(
    message
):

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
        "https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    for chunk in split_message(
        message
    ):

        payload = {

            "chat_id":
                TELEGRAM_CHAT_ID,

            "text":
                chunk,

            "disable_web_page_preview":
                True

        }

        try:

            response = requests.post(
                url,
                json=payload,
                timeout=30
            )

            print(
                "Telegram:",
                response.status_code
            )

        except Exception as e:

            print(
                "Telegram 오류:",
                e
            )

            return False

    return True


# ============================================================
# Google News RSS
# ============================================================

def fetch_google_news(
    query,
    limit=8
):

    url = (
        "https://news.google.com/rss/search"
        "?q="
        + requests.utils.quote(query)
        + "&hl=en-US"
        "&gl=US"
        "&ceid=US:en"
    )

    headers = {

        "User-Agent":
            "Mozilla/5.0 "
            "MarketStrategyBot/1.0"

    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

        root = ET.fromstring(
            response.content
        )

        results = []

        for item in root.findall(
            ".//item"
        )[:limit]:

            title = item.findtext(
                "title",
                ""
            ).strip()

            link = item.findtext(
                "link",
                ""
            ).strip()

            pub_date = item.findtext(
                "pubDate",
                ""
            ).strip()

            source_node = item.find(
                "source"
            )

            source = ""

            if source_node is not None:

                source = (
                    source_node.text
                    or ""
                ).strip()

            if not title:
                continue

            results.append({

                "title":
                    title,

                "link":
                    link,

                "date":
                    pub_date,

                "source":
                    source

            })

        return results

    except Exception as e:

        print(
            "Google News 오류:",
            query,
            e
        )

        return []


# ============================================================
# 뉴스 전체 수집
# ============================================================

def collect_news():

    all_news = []

    seen = set()

    for query in NEWS_QUERIES:

        results = fetch_google_news(
            query
        )

        for item in results:

            key = re.sub(
                r"\s+",
                " ",
                item["title"].lower()
            ).strip()

            if key in seen:
                continue

            seen.add(
                key
            )

            all_news.append(
                item
            )

    print(
        "수집 뉴스:",
        len(all_news)
    )

    return all_news


# ============================================================
# GitHub API
# ============================================================

def github_headers():

    headers = {

        "Accept":
            "application/vnd.github+json",

        "X-GitHub-Api-Version":
            "2022-11-28",

    }

    if GITHUB_TOKEN:

        headers["Authorization"] = (
            f"Bearer {GITHUB_TOKEN}"
        )

    return headers


def github_search_repositories():

    results = []

    headers = github_headers()

    for query in GITHUB_SEARCH_QUERIES:

        url = (
            "https://api.github.com/search/repositories"
            "?q="
            + requests.utils.quote(
                query
            )
            + "&sort=updated"
            + "&order=desc"
            + "&per_page=5"
        )

        try:

            response = requests.get(
                url,
                headers=headers,
                timeout=20
            )

            if response.status_code != 200:

                print(
                    "GitHub 검색 실패:",
                    response.status_code
                )

                continue

            data = response.json()

            for repo in data.get(
                "items",
                []
            ):

                results.append({

                    "name":
                        repo.get(
                            "full_name",
                            ""
                        ),

                    "description":
                        repo.get(
                            "description",
                            ""
                        ),

                    "stars":
                        repo.get(
                            "stargazers_count",
                            0
                        ),

                    "forks":
                        repo.get(
                            "forks_count",
                            0
                        ),

                    "issues":
                        repo.get(
                            "open_issues_count",
                            0
                        ),

                    "language":
                        repo.get(
                            "language",
                            ""
                        ),

                    "updated":
                        repo.get(
                            "updated_at",
                            ""
                        ),

                    "url":
                        repo.get(
                            "html_url",
                            ""
                        )

                })

        except Exception as e:

            print(
                "GitHub 오류:",
                e
            )

    return results


# ============================================================
# GitHub 활동 데이터
# ============================================================

def github_repo_activity(
    repo_name
):

    headers = github_headers()

    result = {

        "repo":
            repo_name,

        "commits":
            [],

        "issues":
            [],

        "releases":
            []

    }

    # --------------------------------------------------------
    # commits
    # --------------------------------------------------------

    try:

        url = (
            f"https://api.github.com/repos/"
            f"{repo_name}/commits"
            "?per_page=20"
        )

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        if response.status_code == 200:

            commits = response.json()

            result["commits"] = [

                {

                    "date":
                        c.get(
                            "commit",
                            {}
                        )
                        .get(
                            "author",
                            {}
                        )
                        .get(
                            "date",
                            ""
                        ),

                    "message":
                        c.get(
                            "commit",
                            {}
                        )
                        .get(
                            "message",
                            ""
                        )[:200]

                }

                for c in commits

            ]

    except Exception as e:

        print(
            "GitHub commit 오류:",
            e
        )

    # --------------------------------------------------------
    # issues
    # --------------------------------------------------------

    try:

        url = (
            f"https://api.github.com/repos/"
            f"{repo_name}/issues"
            "?state=all"
            "&per_page=20"
        )

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        if response.status_code == 200:

            issues = response.json()

            result["issues"] = [

                {

                    "title":
                        x.get(
                            "title",
                            ""
                        ),

                    "state":
                        x.get(
                            "state",
                            ""
                        ),

                    "created":
                        x.get(
                            "created_at",
                            ""
                        )

                }

                for x in issues

            ]

    except Exception as e:

        print(
            "GitHub issue 오류:",
            e
        )

    # --------------------------------------------------------
    # releases
    # --------------------------------------------------------

    try:

        url = (
            f"https://api.github.com/repos/"
            f"{repo_name}/releases"
            "?per_page=10"
        )

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        if response.status_code == 200:

            releases = response.json()

            result["releases"] = [

                {

                    "tag":
                        x.get(
                            "tag_name",
                            ""
                        ),

                    "name":
                        x.get(
                            "name",
                            ""
                        ),

                    "date":
                        x.get(
                            "published_at",
                            ""
                        )

                }

                for x in releases

            ]

    except Exception as e:

        print(
            "GitHub release 오류:",
            e
        )

    return result


# ============================================================
# GitHub 데이터 요약
# ============================================================

def build_github_context(
    repositories
):

    if not repositories:

        return (
            "GitHub 데이터를 수집하지 못했습니다."
        )

    output = []

    for repo in repositories[:30]:

        activity = github_repo_activity(
            repo["name"]
        )

        output.append(

            json.dumps(

                {

                    "repository":
                        repo,

                    "activity":
                        activity

                },

                ensure_ascii=False

            )

        )

    return "\n\n".join(
        output
    )


# ============================================================
# Gemini 분석
# ============================================================

def generate_strategy(
    news,
    github_context
):

    if not GEMINI_API_KEY:

        raise ValueError(
            "GEMINI_API_KEY가 없습니다."
        )

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    news_text = "\n\n".join(

        [

            f"[{i}] "
            f"{x['title']}\n"
            f"출처: {x['source']}\n"
            f"시간: {x['date']}\n"
            f"링크: {x['link']}"

            for i, x in enumerate(
                news[:80],
                1
            )

        ]

    )

    # ========================================================
    # 핵심 전략 프롬프트
    # ========================================================

    prompt = f"""
너는 지금부터

"미국 주식시장 시니어 전략 분석가"

다.

목표는 단순한 뉴스 요약이 아니다.

매시간 최신 정보를 다시 검증하여
앞으로 단기적으로 반등할 가능성이 상대적으로
높은 미국 주식 10개를 선정하는 것이다.

대형주만 선정하지 않는다.

대형주
중형주
소형주

모두 평가한다.

============================================================
🚨 최우선 원칙: 최신 정보 검증
============================================================

아래 뉴스와 GitHub 자료를 사용하되,
최신성이 의심되는 정보는 반드시 다시 검색하여
확인하라.

가능하면 다음을 교차 확인한다.

1. Reuters
2. Bloomberg
3. CNBC
4. WSJ
5. SEC
6. 회사 공식 발표
7. Nasdaq / NYSE
8. GitHub
9. Google News
10. 기타 신뢰할 수 있는 금융 매체

같은 뉴스가 여러 매체에서 확인되는지 확인하라.

오래된 뉴스를 오늘 뉴스처럼 사용하지 마라.

확인되지 않은 숫자를 만들지 마라.

확인되지 않은 주가를 만들지 마라.

확인되지 않은 거래량을 만들지 마라.

============================================================
🎯 최종 목표
============================================================

최종적으로

"현재 시점에서 반등 가능성이 가장 높다고
판단되는 종목 TOP 10"

만 보여준다.

분석 대상은 미국 상장주다.

============================================================
🧠 아이디어 1
GitHub Commit Acceleration + Search Divergence
============================================================

GitHub 데이터가 존재하는 프로젝트는

- 최근 개발 활동
- commit 증가
- release
- issue
- PR 관련 활동

을 평가한다.

가능하면

최근 개발 활동 증가
+
대중 관심이 아직 낮음

이면

"Pumping Divergence"

후보로 본다.

단,

실제 Google Trends API 데이터가 없는 경우
검색량 수치를 만들어내지 마라.

그 경우

"검색량 직접 검증 불가"

라고 표시한다.

============================================================
🛡 아이디어 2
보안 취약점 / 코드 위험
============================================================

GitHub issue / commit / release에서

reentrancy
exploit
emergency
pause
unauthorized
overflow
hack
breach
vulnerability
rollback

등의 위험 키워드를 확인한다.

위험 신호가 확인되면
해당 종목의 급등 점수를 낮추고
급락 위험 점수를 높인다.

============================================================
👨‍💻 아이디어 3
Developer Migration
============================================================

GitHub에서

star
fork
contributor
commit

활동이 급격히 증가하는 프로젝트를 확인한다.

단순 star 숫자만으로 판단하지 않는다.

실제 코드 활동이 있는지를 우선한다.

============================================================
🧪 아이디어 4
Fake Star / Artificial Hype
============================================================

GitHub star가 증가하더라도

실제 코드 변경이 거의 없거나
README 수정 위주라면

"인위적 관심 가능성"

으로 분류한다.

실제 근거가 없으면
가짜 스타라고 단정하지 않는다.

============================================================
⚔️ 아이디어 5
거버넌스 분열
============================================================

GitHub Issues에서

disagree
proposal rejected
fork
abandon
scam
conflict

등의 갈등 신호를 찾는다.

갈등이 급증하면
급락 위험을 높인다.

============================================================
🚀 아이디어 6
Release / Upgrade Momentum
============================================================

GitHub release가 최근 발생했고

실제 코드 활동
+
뉴스 증가

가 동시에 나타나면
상승 촉매로 평가한다.

단순 release만으로 급등이라고 판단하지 않는다.

============================================================
☠️ 아이디어 7
Black Swan 위험
============================================================

GitHub 코드/이슈에서

selfdestruct
mint
blacklist
ownership
exploit
emergency

등 위험 신호가 발견되면
위험도를 크게 높인다.

============================================================
👻 아이디어 8
Developer Ghosting
============================================================

최근 개발활동이

지속적으로 감소하거나

핵심 개발자의 활동이 사라지는 경우

장기 위험 신호로 평가한다.

============================================================
💥 아이디어 9
Panic + Fast Recovery
============================================================

악재 뉴스가 발생했지만

동시에

- 공식 해명
- hotfix
- patch
- 정상화
- 실제 코드 수정

등이 확인된다면

"역발상 반등 가능성"

후보로 평가한다.

============================================================
🤝 아이디어 10
Cross-Agent Consensus
============================================================

두 명의 분석가를 가상으로 분리해서 분석한다.

--------------------------------
Agent A
GitHub Tech Auditor
--------------------------------

평가:

- 개발활동
- commit
- release
- issue
- 코드 변화
- 개발자 활성도

--------------------------------
Agent B
Market / Crowd Sentiment Analyst
--------------------------------

평가:

- 뉴스
- 검색 관심
- 투자자 심리
- FOMO
- 공포
- 악재/호재
- 시장 모멘텀

두 분석 결과를 교차검증한다.

둘이 모두 긍정적이면
상승 확신 점수를 높인다.

둘이 모두 부정적이면
급락 위험을 높인다.

서로 의견이 다르면
"불확실"로 처리한다.

============================================================
📊 종목 평가 점수
============================================================

각 후보를 100점 만점으로 평가한다.

다음 가중치를 사용한다.

뉴스 모멘텀              25점

시장/업종 모멘텀         15점

실적/기업 촉매           15점

GitHub 개발 모멘텀       10점

개발자 활동               5점

대중 관심/심리            10점

악재 위험                 -10점

과열 위험                 -10점

유동성/변동성 위험        -5점

최종적으로 100점에 가까울수록
관심 후보로 평가한다.

============================================================
🔥 반등 가능성
============================================================

각 종목에 대해

"향후 24시간~72시간 단기 반등 가능성"

을 평가한다.

단,

이 숫자는 실제 통계적 승률이 아니다.

"현재 데이터에 대한 모델의 상대적 신뢰도"

라고 명시한다.

예:

반등 가능성:
78/100

신뢰도:
중간

처럼 표시한다.

============================================================
📉 급락 위험
============================================================

각 종목에 대해

급락 위험을

낮음
보통
높음
매우 높음

으로 평가한다.

============================================================
🚀 소형주 우선 탐색
============================================================

대형주만 뽑지 마라.

실제 촉매가 존재하는 소형주가 있다면
대형주보다 높은 순위에 올릴 수 있다.

단,

"소형주라서"

추천하지 않는다.

반드시

뉴스
실적
계약
수주
FDA
AI
반도체
데이터센터
정부계약
M&A
제품 출시

등 실제 촉매가 있어야 한다.

============================================================
🆕 IPO
============================================================

실제 최신 정보에서 확인되는
신규상장/IPO 종목도 후보로 검토한다.

하지만 IPO 예정이라는 이유만으로
TOP 10에 넣지 않는다.

실제 촉매와 거래 가능성이 있어야 한다.

============================================================
🏆 최종 출력
============================================================

아래 형식으로 Telegram 메시지를 만들어라.

━━━━━━━━━━━━━━━━━━
🚨 미국 주식 1시간 전략 레이더
━━━━━━━━━━━━━━━━━━

🕐 분석시간:
YYYY-MM-DD HH:MM KST

📊 시장상태:
강세 / 중립 / 약세

🔥 현재 핵심 테마:
1.
2.
3.

━━━━━━━━━━━━━━━━━━
🏆 오늘의 관심주 TOP 10
━━━━━━━━━━━━━━━━━━

1️⃣ 종목명 (TICKER)

종류:
대형 / 중형 / 소형 / IPO

🎯 전략점수:
XX/100

📈 반등 가능성:
XX/100

📉 급락 위험:
낮음 / 보통 / 높음 / 매우 높음

🔥 핵심 촉매:
-

📰 최신 뉴스:
-

🧠 분석:
-

🎯 반등 확인 조건:
-

⚠️ 가장 큰 위험:
-

🔎 데이터 신뢰도:
높음 / 중간 / 낮음

--------------------------------

2️⃣부터 10️⃣까지 동일하게 작성한다.

============================================================
⭐ 마지막 요약
============================================================

🥇 가장 강한 후보:
종목

🥈 두 번째:
종목

🥉 세 번째:
종목

🚀 가장 공격적인 소형주:
종목

🛡 가장 안정적인 대형주:
종목

⚠️ 급락 경계:
종목

============================================================
📌 중요한 정보
============================================================

이번 분석에서 사용한 주요 뉴스 출처를
마지막에 5개 이내로 표시한다.

각 출처는

매체명
기사 제목

형태로 표시한다.

============================================================
⚠️ 투자 위험
============================================================

이 분석은 최신 공개정보를 기반으로 한
자동화된 시장 분석이다.

반등 가능성 점수는 실제 통계적 승률이 아니라
현재 데이터에 대한 모델의 상대적 평가다.

주가 상승을 보장하지 않는다.

============================================================
최신 뉴스
============================================================

{news_text}

============================================================
GitHub 데이터
============================================================

{github_context}
"""

    # --------------------------------------------------------
    # Gemini 호출
    # --------------------------------------------------------

    print(
        "Gemini 전략 분석 시작"
    )

    # Google Search Grounding 사용
    # 최신 정보 재검증 목적
    config = types.GenerateContentConfig(

        max_output_tokens=12000,

        tools=[
            types.Tool(
                google_search=types.GoogleSearch()
            )
        ]

    )

    response = client.models.generate_content(

        model=MODEL_NAME,

        contents=prompt,

        config=config

    )

    if not response.text:

        raise ValueError(
            "Gemini 응답이 비어 있습니다."
        )

    return response.text.strip()


# ============================================================
# 오류 메시지
# ============================================================

def error_message(
    error
):

    text = str(error)

    if (
        "429" in text
        or
        "RESOURCE_EXHAUSTED"
        in text
        or
        "quota"
        in text.lower()
    ):

        return """
🚨 [미국 주식 전략 레이더]

Gemini API 사용량 제한에 도달했습니다.

이번 분석에서는 최신 정보 검증을 완료하지 못했기 때문에
확인되지 않은 종목을 임의로 추천하지 않았습니다.

다음 분석 주기에 다시 시도합니다.

⚠️ 중요:
API 오류 상태에서 가짜 주가/종목/확률을 생성하지 않습니다.
"""

    return f"""
🚨 [미국 주식 전략 레이더]

AI 분석 중 오류가 발생했습니다.

오류:
{text[:800]}

최신 정보 검증이 완료되지 않았으므로
종목 추천을 생성하지 않았습니다.
"""


# ============================================================
# 환경변수
# ============================================================

def check_environment():

    missing = []

    if not GEMINI_API_KEY:
        missing.append(
            "GEMINI_API_KEY"
        )

    if not TELEGRAM_BOT_TOKEN:
        missing.append(
            "TELEGRAM_BOT_TOKEN"
        )

    if not TELEGRAM_CHAT_ID:
        missing.append(
            "TELEGRAM_CHAT_ID"
        )

    return missing


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=========================================="
    )

    print(
        "미국 주식 1시간 전략 레이더 시작"
    )

    print(
        datetime.now(
            KST
        ).strftime(
            "%Y-%m-%d %H:%M:%S KST"
        )
    )

    print(
        "=========================================="
    )

    missing = check_environment()

    if missing:

        message = (
            "🚨 전략 레이더 설정 오류\n\n"
            "누락된 GitHub Secrets:\n\n"
            +
            "\n".join(
                f"- {x}"
                for x in missing
            )
        )

        send_telegram(
            message
        )

        return

    # --------------------------------------------------------
    # 1. 최신 뉴스
    # --------------------------------------------------------

    print(
        "1단계: 최신 뉴스 수집"
    )

    news = collect_news()

    # --------------------------------------------------------
    # 2. GitHub
    # --------------------------------------------------------

    print(
        "2단계: GitHub 개발활동 수집"
    )

    repositories = (
        github_search_repositories()
    )

    github_context = (
        build_github_context(
            repositories
        )
    )

    # --------------------------------------------------------
    # 3. Gemini
    # --------------------------------------------------------

    try:

        print(
            "3단계: AI 교차 분석"
        )

        result = generate_strategy(

            news,

            github_context

        )

        # ----------------------------------------------------
        # 4. Telegram
        # ----------------------------------------------------

        print(
            "4단계: Telegram 전송"
        )

        send_telegram(
            result
        )

        print(
            "=========================================="
        )

        print(
            "분석 완료"
        )

        print(
            "=========================================="
        )

    except Exception as e:

        print(
            "Gemini 분석 실패:"
        )

        print(
            str(e)
        )

        send_telegram(
            error_message(
                e
            )
        )


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":

    main()
