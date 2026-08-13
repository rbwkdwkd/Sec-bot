import os
import time
import requests
from google import genai
from google.genai import types


# ============================================================
# 환경변수
# GitHub Secrets에서 가져옵니다.
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


# ============================================================
# Gemini 모델 설정
# ============================================================

# 1순위: Gemini 3.6 Flash
# 2순위: Gemini 3.5 Flash-Lite
#
# 3.5 Flash-Lite는 고처리량/저비용 작업에 적합하고
# Google Search grounding도 지원합니다.
MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
]


# ============================================================
# 기본 확인
# ============================================================

def check_environment():
    """필수 환경변수가 있는지 확인"""

    missing = []

    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        raise ValueError(
            "다음 GitHub Secrets가 없습니다: "
            + ", ".join(missing)
        )


# ============================================================
# Gemini API 요청
# ============================================================

def get_gemini_response():

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    prompt = """
오늘 미국 증시 개장 전 브리핑을 작성해 주세요.

반드시 최신 웹 검색 정보를 사용하세요.

다음 내용을 중심으로 확인하세요.

1. 미국 주요 지수
   - S&P 500
   - Nasdaq
   - Dow Jones

2. 미국 국채 금리와 연준
   - 미국 10년물 국채금리
   - 연준(Fed) 관련 주요 뉴스
   - 금리 전망에 영향을 줄 만한 내용

3. 주요 경제지표
   - CPI
   - PPI
   - 고용지표
   - GDP
   - 기타 시장에 중요한 최신 경제지표

4. 빅테크 및 주요 기업 뉴스
   - NVIDIA
   - Apple
   - Microsoft
   - Amazon
   - Alphabet
   - Meta
   - Tesla
   - 기타 미국 증시에 중요한 기업

5. 오늘 미국 증시에 영향을 줄 가능성이 높은 핵심 뉴스

6. 오늘 투자자들이 특히 주의해서 볼 포인트

작성 규칙:

- 최신 웹 검색 정보를 기준으로 작성하세요.
- 확인되지 않은 정보는 절대로 만들어내지 마세요.
- 가능하면 최근 24시간 이내의 정보를 우선하세요.
- 한국어로 작성하세요.
- 너무 길지 않게 핵심만 정리하세요.
- 주식 매수/매도를 직접적으로 권유하지 마세요.

다음 형식으로 작성하세요.

🚨 [미국 증시 개장 전 브리핑]

📊 주요 지수
- S&P 500:
- Nasdaq:
- Dow Jones:

💰 금리 및 연준
- 미국 10년물 국채금리:
- 연준 관련 핵심 내용:

📈 주요 경제지표
- 오늘 발표 예정:
- 최근 발표된 주요 지표:

🏢 빅테크 및 주요 기업
- NVIDIA:
- Apple:
- Microsoft:
- Amazon:
- Alphabet:
- Meta:
- Tesla:

🔥 오늘의 핵심 뉴스
1.
2.
3.

👀 오늘 주목할 포인트
- 
- 
- 

※ 본 내용은 정보 제공 목적이며 투자 권유가 아닙니다.
"""

    # Google Search grounding
    search_tool = types.Tool(
        google_search=types.GoogleSearch()
    )

    config = types.GenerateContentConfig(
        tools=[search_tool],
        max_output_tokens=2500,
    )

    # --------------------------------------------------------
    # 모델별 시도
    # --------------------------------------------------------

    last_error = None

    for model_name in MODELS:

        print(f"Gemini API 요청 시작: {model_name}")

        # 각 모델에 대해 최대 2번 시도
        for attempt in range(2):

            try:

                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )

                # 응답 확인
                if response is None:
                    raise ValueError(
                        "Gemini가 빈 응답을 반환했습니다."
                    )

                text = response.text

                if not text or not text.strip():
                    raise ValueError(
                        "Gemini 응답 내용이 비어 있습니다."
                    )

                print(
                    f"Gemini 응답 성공: {model_name}"
                )

                return text.strip()

            except Exception as error:

                last_error = error

                error_text = str(error)

                print(
                    f"Gemini 오류 "
                    f"(모델={model_name}, "
                    f"시도={attempt + 1}/2): "
                    f"{error_text}"
                )

                # 429 RESOURCE_EXHAUSTED
                if (
                    "429" in error_text
                    or "RESOURCE_EXHAUSTED" in error_text
                    or "TooManyRequests" in error_text
                ):

                    # 바로 반복 요청하지 않고 잠시 대기
                    wait_seconds = 10 * (attempt + 1)

                    print(
                        f"API 사용량 제한 감지. "
                        f"{wait_seconds}초 후 재시도합니다."
                    )

                    time.sleep(wait_seconds)

                    continue

                # 404 모델 없음
                if (
                    "404" in error_text
                    or "NOT_FOUND" in error_text
                    or "NotFound" in error_text
                ):

                    print(
                        f"{model_name} 모델을 사용할 수 없습니다."
                    )

                    # 다음 모델로 이동
                    break

                # API 키 문제
                if (
                    "401" in error_text
                    or "403" in error_text
                    or "API key" in error_text
                ):

                    raise ValueError(
                        "Gemini API 키를 확인하세요.\n"
                        f"원본 오류: {error_text}"
                    )

                # 그 외 오류는 같은 모델에서 한 번 더 시도
                time.sleep(5)

    # 모든 모델 실패
    raise RuntimeError(
        "모든 Gemini 모델 요청에 실패했습니다.\n"
        f"마지막 오류: {last_error}"
    )


# ============================================================
# Telegram 메시지 전송
# ============================================================

def send_telegram_message(message):

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    # Telegram 메시지 길이 제한을 고려
    max_length = 4000

    messages = []

    if len(message) <= max_length:

        messages.append(message)

    else:

        # 긴 메시지는 여러 개로 분리
        for i in range(0, len(message), max_length):

            messages.append(
                message[i:i + max_length]
            )

    for part in messages:

        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": part,
        }

        response = requests.post(
            url,
            data=data,
            timeout=30,
        )

        if response.status_code != 200:

            raise RuntimeError(
                "Telegram 메시지 전송 실패\n"
                f"HTTP 상태 코드: {response.status_code}\n"
                f"응답: {response.text}"
            )

        print("Telegram 메시지 전송 성공")

        # 너무 빠른 연속 전송 방지
        time.sleep(1)


# ============================================================
# 오류 발생 시 Telegram으로 오류 알림
# ============================================================

def send_error_message(error):

    error_text = str(error)

    message = (
        "🚨 [미국 증시 개장 전 브리핑]\n\n"
        "Gemini API 요청 중 오류가 발생했습니다.\n\n"
        f"오류 내용:\n{error_text}"
    )

    try:

        send_telegram_message(message)

    except Exception as telegram_error:

        print(
            "오류 메시지 Telegram 전송도 실패했습니다:"
        )

        print(telegram_error)


# ============================================================
# 메인 실행
# ============================================================

def main():

    print("=" * 60)
    print("미국 증시 개장 전 브리핑 봇 시작")
    print("=" * 60)

    try:

        # 1. 환경변수 확인
        print("1. 환경변수 확인 중...")

        check_environment()

        print("환경변수 확인 완료")

        # 2. Gemini 요청
        print()
        print("2. Gemini API 요청 중...")

        briefing = get_gemini_response()

        print("Gemini 응답 수신 완료")

        # 3. Telegram 전송
        print()
        print("3. Telegram 메시지 전송 중...")

        send_telegram_message(briefing)

        print()
        print("=" * 60)
        print("미국 증시 브리핑 전송 완료")
        print("=" * 60)

    except Exception as error:

        print()
        print("=" * 60)
        print("프로그램 실행 중 오류 발생")
        print("=" * 60)

        print(str(error))

        # Telegram으로 오류 알림
        send_error_message(error)

        # GitHub Actions에서 실패로 표시
        raise


# ============================================================
# 프로그램 실행
# ============================================================

if __name__ == "__main__":
    main()
