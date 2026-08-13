import os
import re
import sys
import time
import html
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types


# ============================================================
# 설정
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

MODEL_NAME = "gemini-3.6-flash"

KST = ZoneInfo("Asia/Seoul")

TELEGRAM_MAX_LENGTH = 4000


# ============================================================
# 환경변수 확인
# ============================================================

def check_environment():
    missing = []

    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        print("필수 환경변수가 없습니다.")
        print(", ".join(missing))
        sys.exit(1)


# ============================================================
# Telegram 메시지 전송
# ============================================================

def split_message(text, max_length=TELEGRAM_MAX_LENGTH):
    """
    Telegram의 메시지 길이 제한을 고려해서
    너무 긴 메시지를 여러 개로 나눔.
    """

    text = text.strip()

    if len(text) <= max_length:
        return [text]

    parts = []
    current = ""

    paragraphs = text.split("\n")

    for paragraph in paragraphs:

        # 한 줄 자체가 너무 긴 경우
        if len(paragraph) > max_length:

            if current:
                parts.append(current.strip())
                current = ""

            for i in range(0, len(paragraph), max_length):
                parts.append(paragraph[i:i + max_length])

            continue

        candidate = current + paragraph + "\n"

        if len(candidate) > max_length:

            if current:
                parts.append(current.strip())

            current = paragraph + "\n"

        else:
            current = candidate

    if current.strip():
        parts.append(current.strip())

    return parts


def send_telegram(text):
    """
    Telegram Bot API를 이용해 메시지를 전송한다.
    """

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    messages = split_message(text)

    for message in messages:

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": True
        }

        response = requests.post(
            url,
            data=payload,
            timeout=30
        )

        if response.status_code != 200:
            print("Telegram 전송 실패:")
            print(response.text)
            raise RuntimeError(
                f"Telegram API 오류: {response.status_code}"
            )

        print("Telegram 메시지 전송 성공")

        # 여러 메시지로 나뉜 경우 너무 빠르게 보내지 않도록 함
        if len(messages) > 1:
            time.sleep(1)


# ============================================================
# Gemini API 오류 종류 확인
# ============================================================

def is_quota_error(error):
    """
    Gemini 429 RESOURCE_EXHAUSTED 여부 확인
    """

    error_text = str(error).upper()

    return (
        "429" in error_text
        or "RESOURCE_EXHAUSTED" in error_text
        or "QUOTA" in error_text
        or "RATE LIMIT" in error_text
    )


# ============================================================
# Gemini 응답이 정상적인지 검사
# ============================================================

def clean_response(text):
    """
    Gemini가 반환한 텍스트를 정리한다.
    """

    if not text:
        return ""

    text = text.strip()

    # Markdown 코드블록 제거
    text = re.sub(r"^```.*?\n", "", text)
    text = re.sub(r"\n```$", "", text)

    # 불필요한 공백 정리
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def response_looks_broken(text):
    """
    Gemini 응답이 중간에서 잘린 것으로 보이는지 검사한다.

    예:
    - 고용 급...
    - 금리 인상 우려가 완
    - 못해...
    """

    if not text:
        return True

    stripped = text.strip()

    # 너무 짧으면 실패로 처리
    if len(stripped) < 120:
        return True

    # 끝이 명백한 말줄임표인 경우
    if stripped.endswith("..."):
        return True

    if stripped.endswith("…"):
        return True

    # 한국어 문장이 조사/접속사 등에서 끝나는 경우
    broken_endings = (
        "그리고",
        "또한",
        "하지만",
        "때문에",
        "영향",
        "영향을",
        "우려",
        "가능",
        "가능성",
        "증가",
        "감소",
        "급",
        "완",
        "못해",
        "따라",
        "관련",
        "대해",
        "및",
        "또는",
        "것으로",
        "전망"
    )

    last_line = stripped.splitlines()[-1].strip()

    for ending in broken_endings:
        if last_line.endswith(ending):
            return True

    return False


# ============================================================
# Gemini에게 미국 증시 브리핑 요청
# ============================================================

def generate_market_briefing():
    """
    Google Search grounding을 이용해서 최신 미국 증시 자료를 검색하고
    Gemini가 한국어 브리핑을 작성한다.

    중요:
    Gemini API는 이 함수에서 1회만 호출한다.
    """

    now = datetime.now(KST)

    today = now.strftime("%Y년 %m월 %d일")
    current_time = now.strftime("%H:%M")

    prompt = f"""
너는 미국 증시 개장 전 시장 브리핑을 작성하는 금융 뉴스 분석가다.

현재 한국시간:
{today} {current_time}

반드시 Google Search를 사용해서 최신 정보를 확인한 뒤 작성하라.

목적:
한국 투자자가 미국 증시 개장 전에 빠르게 읽을 수 있는
짧고 정확한 시장 브리핑을 만드는 것이다.

━━━━━━━━━━━━━━━━━━━━
[매우 중요한 사실 확인 규칙]
━━━━━━━━━━━━━━━━━━━━

1. 반드시 최신 웹 검색 결과를 바탕으로 작성한다.

2. 검색 결과에서 확인되지 않은 숫자를 절대 만들지 마라.

3. 유가, 금리, 국채금리, 지수, 고용지표 등의 수치는
   검색 결과에서 실제로 확인된 경우에만 사용한다.

4. 특히 다음과 같은 숫자를 임의로 만들지 마라.

   - 국제유가
   - WTI
   - 브렌트유
   - 미국 10년물 국채금리
   - 미국 기준금리
   - 실업률
   - 비농업 고용
   - CPI
   - PPI
   - 나스닥
   - S&P500
   - 다우지수

5. 검색 결과에서 숫자가 확인되지 않으면
   숫자를 쓰지 말고 "상승", "하락", "둔화" 등의 표현을 사용하라.

6. 과거 뉴스와 오늘 뉴스를 혼동하지 마라.

7. 오늘 발표된 자료가 없다면 억지로 오늘 발표된 것처럼 쓰지 마라.

8. 확인되지 않은 속보를 사실처럼 작성하지 마라.

9. "현물 유가가 140달러를 돌파했다"와 같은 내용도
   실제 검색 결과에서 확인되지 않았다면 절대 작성하지 마라.

10. 서로 충돌하는 뉴스가 있으면 양쪽 내용을 확인하고
    가장 신뢰할 수 있는 최신 정보를 우선하라.

━━━━━━━━━━━━━━━━━━━━
[검색해야 할 내용]
━━━━━━━━━━━━━━━━━━━━

다음 항목을 확인하라.

① 미국 주요 증시 선물
- S&P500 선물
- 나스닥100 선물
- 다우 선물

② 미국 국채 및 연준
- 미국 10년물 국채금리
- 연준 금리 전망
- 금리 인상/인하 기대 변화

③ 주요 경제지표
- 고용
- 실업률
- CPI
- PPI
- 소비자심리
- 소매판매
- 기타 오늘 발표된 주요 지표

④ 국제유가
- WTI
- 브렌트유
- 중동 지정학적 위험
- 유가 상승/하락 요인

⑤ 빅테크 및 주요 기업 뉴스
- NVIDIA
- Apple
- Microsoft
- Amazon
- Alphabet
- Meta
- Tesla
- 기타 미국 증시에 영향을 줄 만한 주요 기업

⑥ 오늘 미국 증시에 가장 중요한 뉴스

━━━━━━━━━━━━━━━━━━━━
[출력 형식]
━━━━━━━━━━━━━━━━━━━━

반드시 아래 형식으로 작성하라.

🚨 [미국 증시 개장 전 브리핑]

📅 {today}

1. 미국 증시 선물
- S&P500:
- 나스닥100:
- 다우:

2. 금리·연준
- 핵심 내용:
- 미국 증시에 미칠 영향:

3. 경제지표
- 핵심 내용:
- 시장 영향:

4. 유가·지정학
- 핵심 내용:
- 시장 영향:

5. 빅테크·기업
- 핵심 내용:
- 시장 영향:

6. 오늘의 핵심 체크포인트
- 첫 번째:
- 두 번째:
- 세 번째:

━━━━━━━━━━━━━━━━━━━━
[작성 스타일]
━━━━━━━━━━━━━━━━━━━━

- 한국어
- 짧고 명확하게
- 투자자가 1분 안에 읽을 수 있게 작성
- 각 항목은 1~2문장 정도
- 불필요한 설명 금지
- 확인되지 않은 사실 금지
- 추측은 반드시 "가능성"이라고 표시
- 투자 권유 금지
- "매수", "매도"를 단정하지 마라
- 뉴스가 없으면 없다고 작성하라
- 문장을 반드시 완결해서 끝내라
- 문장 중간에서 끊지 마라
- 말줄임표(...) 사용 금지
- 마지막 문장은 반드시 완결된 문장으로 끝내라.

중요:
검색 결과를 단순히 복사하지 말고,
미국 증시에 어떤 영향을 줄 수 있는지 짧게 설명하라.
"""

    print("Gemini API 요청 시작...")
    print(f"모델: {MODEL_NAME}")
    print("Google Search grounding 사용")

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    config = types.GenerateContentConfig(
        tools=[
            types.Tool(
                google_search=types.GoogleSearch()
            )
        ],
        max_output_tokens=1800
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=config
    )

    text = clean_response(response.text)

    if response_looks_broken(text):
        raise RuntimeError(
            "Gemini 응답이 완성되지 않은 것으로 판단되어 "
            "Telegram 전송을 중단했습니다."
        )

    return text


# ============================================================
# Gemini 실패 시 Telegram으로 보내는 안전한 안내
# ============================================================

def create_quota_error_message(error):
    """
    Gemini quota 오류가 발생했을 때
    잘못된 시장 정보를 보내지 않고 상태만 알려준다.
    """

    return f"""🚨 [미국 증시 개장 전 브리핑]

Gemini API 사용량 제한으로
최신 AI 브리핑을 생성하지 못했습니다.

현재 Gemini API가
429 RESOURCE_EXHAUSTED를 반환했습니다.

확인할 사항:
1. Gemini API 사용량
2. RPM / TPM / RPD quota
3. Google AI Studio 사용량 및 결제 상태

※ 이번 실행에서는 확인되지 않은 시장 정보를
임의로 생성하지 않고 전송하지 않았습니다.

오류 시간:
{datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")} KST
"""


def create_general_error_message(error):
    """
    Gemini의 일반적인 오류 발생 시
    잘못된 시장 정보를 보내지 않는다.
    """

    error_short = str(error)

    # 너무 긴 오류 메시지는 잘라서 표시
    if len(error_short) > 800:
        error_short = error_short[:800] + "..."

    return f"""🚨 [미국 증시 개장 전 브리핑]

최신 시장 브리핑 생성 중 오류가 발생했습니다.

이번 실행에서는 확인되지 않은 정보를
임의로 전송하지 않았습니다.

오류:
{error_short}

오류 시간:
{datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")} KST
"""


# ============================================================
# 메인 실행
# ============================================================

def main():

    print("=" * 60)
    print("미국 증시 개장 전 브리핑 봇 시작")
    print("=" * 60)

    check_environment()

    now = datetime.now(KST)

    print(
        "현재 한국시간:",
        now.strftime("%Y-%m-%d %H:%M:%S")
    )

    # --------------------------------------------------------
    # Gemini 브리핑 생성
    # --------------------------------------------------------

    try:

        briefing = generate_market_briefing()

        print("\nGemini 브리핑 생성 성공")
        print("-" * 60)
        print(briefing)
        print("-" * 60)

    except Exception as error:

        print("\nGemini API 오류 발생")
        print(error)

        # 429이면 quota 안내
        if is_quota_error(error):

            print("429 RESOURCE_EXHAUSTED 감지")

            telegram_message = create_quota_error_message(
                error
            )

        else:

            telegram_message = create_general_error_message(
                error
            )

        # ----------------------------------------------------
        # 오류 상황도 Telegram에는 정상적으로 알림
        # ----------------------------------------------------

        try:

            send_telegram(telegram_message)

            print("오류 안내 Telegram 전송 성공")

        except Exception as telegram_error:

            print("Telegram 오류 안내 전송 실패")
            print(telegram_error)

        # ----------------------------------------------------
        # 중요:
        # GitHub Actions를 불필요하게 실패시키지 않음
        # ----------------------------------------------------

        return

    # --------------------------------------------------------
    # 정상적인 Gemini 결과만 Telegram으로 전송
    # --------------------------------------------------------

    telegram_message = briefing

    try:

        send_telegram(telegram_message)

        print("=" * 60)
        print("최종 처리 완료")
        print("=" * 60)

    except Exception as error:

        print("Telegram 전송 중 오류 발생")
        print(error)

        raise


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    main()
