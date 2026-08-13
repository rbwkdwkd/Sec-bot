import os
import time
import random
import requests

from google import genai
from google.genai import types


# ============================================================
# 환경변수
# GitHub Secrets에서 다음 3개를 설정하세요.
#
# GEMINI_API_KEY
# TELEGRAM_BOT_TOKEN
# TELEGRAM_CHAT_ID
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


# ============================================================
# 기본 설정
# ============================================================

MODEL_NAME = "gemini-3.6-flash"

# Gemini 일시적 오류 재시도 횟수
MAX_RETRIES = 4

# 최초 대기 시간
BASE_DELAY = 5


# ============================================================
# Telegram 메시지 전송
# ============================================================

def send_telegram_message(message):
    """Telegram Bot으로 메시지를 전송합니다."""

    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN이 없습니다.")
        return False

    if not TELEGRAM_CHAT_ID:
        print("TELEGRAM_CHAT_ID가 없습니다.")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        response = requests.post(
            url,
            data=data,
            timeout=30
        )

        response.raise_for_status()

        print("Telegram 메시지 전송 성공")
        return True

    except requests.exceptions.RequestException as e:
        print(f"Telegram 메시지 전송 실패: {e}")
        return False


# ============================================================
# 오류가 재시도 가능한 오류인지 확인
# ============================================================

def is_retryable_error(error):
    """
    Gemini 오류 중 재시도할 가치가 있는 오류인지 판단합니다.

    재시도:
    - 429 RESOURCE_EXHAUSTED
    - 503 UNAVAILABLE
    - 408 timeout
    - 일시적인 네트워크 오류

    재시도하지 않음:
    - API KEY 오류
    - 잘못된 요청
    - 권한 오류
    - 모델 이름 오류
    """

    error_text = str(error).lower()

    retry_keywords = [
        "429",
        "resource_exhausted",
        "too many requests",
        "rate limit",
        "quota",
        "503",
        "unavailable",
        "408",
        "timeout",
        "timed out",
        "temporarily unavailable",
        "internal server error"
    ]

    for keyword in retry_keywords:
        if keyword in error_text:
            return True

    return False


# ============================================================
# Gemini API 호출
# ============================================================

def generate_market_briefing():
    """
    Gemini를 이용하여 최신 미국 증시 개장 전 브리핑을 생성합니다.
    """

    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY가 GitHub Secrets에 설정되어 있지 않습니다."
        )

    print("Gemini API 요청 준비 중...")

    # Gemini Client 생성
    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    # --------------------------------------------------------
    # 최신 웹 검색을 사용하는 Gemini 설정
    # --------------------------------------------------------

    config = types.GenerateContentConfig(
        tools=[
            types.Tool(
                google_search=types.GoogleSearch()
            )
        ],

        # 너무 긴 답변을 방지
        max_output_tokens=1200,

        # 답변을 너무 창작하지 않도록 낮게 설정
        temperature=0.2
    )

    # --------------------------------------------------------
    # 프롬프트
    # --------------------------------------------------------

    prompt = """
오늘 미국 증시 개장 전 브리핑을 작성해줘.

반드시 최신 웹 검색 정보를 활용해줘.

다음 내용을 중심으로 한국어로 작성해줘.

1. 미국 주요 지수
   - S&P 500
   - Nasdaq
   - Dow Jones

2. 미국 증시에 영향을 줄 주요 경제 이슈
   - 금리
   - 연준(Fed)
   - 물가
   - 고용
   - 주요 경제지표

3. 미국 빅테크 및 주요 기업 뉴스

4. 오늘 미국 증시에 영향을 줄 가능성이 큰 핵심 뉴스 3가지

5. 오늘 미국 증시 전망
   - 상승/하락에 영향을 줄 요인
   - 투자자가 주의할 점

작성 규칙:

- 최신 웹 검색 결과를 기준으로 작성할 것
- 가능한 경우 오늘 발표된 정보와 최근 24시간 이내 정보를 우선할 것
- 확인되지 않은 사실을 만들어내지 말 것
- 한국어로 짧고 이해하기 쉽게 작성할 것
- 투자 조언이 아니라 시장 정보 브리핑이라는 점을 유지할 것
- 각 항목은 핵심 내용 위주로 작성할 것
- 너무 긴 설명은 하지 말 것

맨 처음에는 다음 제목을 사용해줘.

🚨 [미국 증시 개장 전 브리핑]
"""

    # --------------------------------------------------------
    # Gemini API 호출 + 재시도
    # --------------------------------------------------------

    for attempt in range(MAX_RETRIES + 1):

        try:
            print(
                f"Gemini API 요청 중... "
                f"(시도 {attempt + 1}/{MAX_RETRIES + 1})"
            )

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=config
            )

            # ------------------------------------------------
            # 정상 응답
            # ------------------------------------------------

            text = response.text

            if not text:
                raise ValueError(
                    "Gemini가 빈 응답을 반환했습니다."
                )

            print("Gemini API 요청 성공")

            return text.strip()

        except Exception as e:

            print("----------------------------------------")
            print("Gemini API 오류 발생")
            print(str(e))
            print("----------------------------------------")

            # -----------------------------------------------
            # 재시도 가능한 오류인지 확인
            # -----------------------------------------------

            if not is_retryable_error(e):

                print(
                    "재시도할 수 없는 오류입니다."
                )

                raise

            # -----------------------------------------------
            # 마지막 시도였다면 종료
            # -----------------------------------------------

            if attempt >= MAX_RETRIES:

                print(
                    "최대 재시도 횟수를 초과했습니다."
                )

                raise

            # -----------------------------------------------
            # 지수 백오프
            #
            # 5초
            # 10초
            # 20초
            # 40초
            #
            # + 약간의 랜덤 시간(jitter)
            # -----------------------------------------------

            delay = BASE_DELAY * (2 ** attempt)

            jitter = random.uniform(0, 2)

            total_delay = delay + jitter

            print(
                f"잠시 후 재시도합니다: "
                f"{total_delay:.1f}초"
            )

            time.sleep(total_delay)

    raise RuntimeError(
        "Gemini API 호출에 실패했습니다."
    )


# ============================================================
# 메인 프로그램
# ============================================================

def main():

    print("========================================")
    print("미국 증시 개장 전 브리핑 봇 시작")
    print("========================================")

    # --------------------------------------------------------
    # 환경변수 확인
    # --------------------------------------------------------

    missing = []

    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:

        error_message = (
            "🚨 [미국 증시 개장 전 브리핑]\n\n"
            "환경변수가 설정되지 않았습니다.\n\n"
            "누락된 항목:\n"
            + "\n".join(
                f"- {item}" for item in missing
            )
        )

        print(error_message)

        # Telegram 설정이 되어 있는 경우에만 오류 전송
        send_telegram_message(error_message)

        # GitHub Actions를 강제로 실패시키지 않음
        return

    # --------------------------------------------------------
    # Gemini 요청
    # --------------------------------------------------------

    try:

        briefing = generate_market_briefing()

    except Exception as e:

        error_text = str(e)

        print("Gemini API 최종 실패")
        print(error_text)

        # ----------------------------------------------------
        # 429 quota 오류인 경우 사용자에게 명확하게 안내
        # ----------------------------------------------------

        lower_error = error_text.lower()

        if (
            "429" in lower_error
            or "resource_exhausted" in lower_error
            or "quota" in lower_error
        ):

            telegram_message = (
                "🚨 [미국 증시 개장 전 브리핑]\n\n"
                "Gemini API 사용량 제한에 도달했습니다.\n\n"
                "현재 Gemini API가 429 "
                "RESOURCE_EXHAUSTED를 반환했습니다.\n\n"
                "자동 재시도를 수행했지만 성공하지 못했습니다.\n\n"
                "확인할 사항:\n"
                "1. Gemini API 사용량\n"
                "2. RPM / TPM / RPD quota\n"
                "3. Google AI Studio의 사용량 및 결제 상태\n\n"
                "※ API 키를 여러 개 만들어도 같은 프로젝트의 "
                "quota는 공유될 수 있습니다."
            )

        else:

            telegram_message = (
                "🚨 [미국 증시 개장 전 브리핑]\n\n"
                "Gemini API 요청 중 오류가 발생했습니다.\n\n"
                f"오류 내용:\n{error_text}"
            )

        # ----------------------------------------------------
        # Telegram 오류 알림
        # ----------------------------------------------------

        send_telegram_message(telegram_message)

        # ----------------------------------------------------
        # 중요:
        # 여기서 raise 하지 않습니다.
        #
        # 따라서 Gemini가 실패하더라도
        # GitHub Actions가 exit code 1로 종료되지 않습니다.
        # ----------------------------------------------------

        print(
            "Gemini 오류를 Telegram으로 알렸습니다."
        )

        print(
            "GitHub Actions 작업을 정상 종료합니다."
        )

        return

    # --------------------------------------------------------
    # Gemini 성공 → Telegram 전송
    # --------------------------------------------------------

    success = send_telegram_message(briefing)

    if success:

        print("========================================")
        print("브리핑 전송 완료")
        print("========================================")

    else:

        print(
            "Gemini 브리핑 생성은 성공했지만 "
            "Telegram 전송에 실패했습니다."
        )


# ============================================================
# 프로그램 실행
# ============================================================

if __name__ == "__main__":
    main()
