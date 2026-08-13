import os
import requests

from google import genai
from google.genai import types


# =========================
# 환경변수
# =========================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


# =========================
# 메인 함수
# =========================

def main():

    print("================================")
    print("미국 증시 브리핑 봇 시작")
    print("================================")


    # -------------------------
    # 1. 환경변수 확인
    # -------------------------

    print("1. 환경변수 확인 중...")

    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY가 없습니다.")
        return

    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN이 없습니다.")
        return

    if not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_CHAT_ID가 없습니다.")
        return

    print("✅ 환경변수 확인 완료")


    # -------------------------
    # 2. Gemini API 요청
    # -------------------------

    print("2. Gemini API 요청 중...")


    try:

        client = genai.Client(
            api_key=GEMINI_API_KEY
        )


        # Google 검색 기능
        google_search_tool = types.Tool(
            google_search=types.GoogleSearch()
        )


        prompt = """
오늘 미국 증시 개장 전 브리핑을 작성해줘.

반드시 Google 검색을 이용해서 최신 정보를 확인해줘.

다음 내용을 중심으로 가장 중요한 체크포인트 3가지만 선정해줘.

1. 미국 주요 지수 및 선물
2. 미국 국채금리와 연준(Fed) 관련 뉴스
3. 오늘 발표되는 주요 경제지표
4. 애플, 엔비디아, 마이크로소프트, 아마존 등 주요 빅테크 뉴스
5. 미국 주요 기업의 실적 및 중요한 뉴스
6. 국제유가, 달러, 금 등 시장에 영향을 줄 수 있는 주요 변수

가능하면 최근 24시간 이내의 뉴스를 우선해서 확인해줘.

각 항목은 다음 형식으로 작성해줘.

① 핵심 내용
- 한두 문장으로 간결하게

② 증시에 미칠 영향
- 상승 요인인지 하락 요인인지 또는 중립인지 설명

투자자에게 실제로 도움이 되는 내용만 골라줘.

확인되지 않은 정보나 추측은 사실처럼 작성하지 마.

전체 결과는 텔레그램으로 보내기 좋게 짧고 읽기 쉽게 작성해줘.

한국어로 작성해줘.
"""


        response = client.models.generate_content(

            model="gemini-3.6-flash",

            contents=prompt,

            config=types.GenerateContentConfig(

                tools=[
                    google_search_tool
                ]

            )
        )


        # Gemini 결과
        report_text = response.text


        if not report_text:
            report_text = "Gemini에서 브리핑 내용을 받지 못했습니다."


        print("✅ Gemini 리포트 생성 성공")
        print("--------------------------------")
        print(report_text)
        print("--------------------------------")


    except Exception as e:

        print("❌ Gemini API 오류")
        print(e)

        report_text = (
            "Gemini API 요청 중 오류가 발생했습니다.\n\n"
            f"오류 내용: {e}"
        )


    # -------------------------
    # 3. Telegram 전송
    # -------------------------

    print("3. Telegram 전송 중...")


    telegram_url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )


    telegram_text = (
        "🚨 [미국 증시 개장 전 브리핑]\n\n"
        f"{report_text}"
    )


    # Telegram 메시지는 최대 4096자이므로
    # 너무 길 경우 잘라서 전송
    if len(telegram_text) > 4000:
        telegram_text = telegram_text[:4000]


    telegram_payload = {

        "chat_id": TELEGRAM_CHAT_ID,

        "text": telegram_text
    }


    try:

        telegram_response = requests.post(

            telegram_url,

            json=telegram_payload,

            timeout=15
        )


        print(
            "Telegram 상태코드:",
            telegram_response.status_code
        )


        if telegram_response.status_code == 200:

            print("✅ Telegram 전송 성공")

        else:

            print("❌ Telegram 전송 실패")
            print(telegram_response.text)


    except Exception as e:

        print("❌ Telegram 전송 중 오류")
        print(e)


    print("================================")
    print("미국 증시 브리핑 봇 종료")
    print("================================")


# =========================
# 프로그램 실행
# =========================

if __name__ == "__main__":
    main()
