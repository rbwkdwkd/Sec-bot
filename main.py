import os
import requests
from google import genai


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def main():

    print("1. Gemini API 요청 중...")

    try:

        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY가 없습니다.")

        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=(
                "오늘 미국 증시 개장 전 주요 체크포인트 3가지를 "
                "최신 정보 기준으로 한국어로 짧고 간결하게 작성해줘. "
                "미국 주요 지수, 금리와 연준, 주요 경제지표, "
                "빅테크 및 주요 기업 뉴스 중 중요한 내용을 포함해줘. "
                "확인되지 않은 정보는 만들지 마."
            )
        )

        report_text = response.text

        print("2. AI 리포트 생성 성공!")
        print(report_text)

    except Exception as e:

        report_text = f"API 요청 에러: {e}"

        print("❌ Gemini 오류:")
        print(e)


    print("3. 텔레그램 전송 중...")

    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN이 없습니다.")
        return

    if not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_CHAT_ID가 없습니다.")
        return


    tg_url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    tg_payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🚨 [미국 증시 브리핑]\n\n{report_text}"
    }


    try:

        tg_res = requests.post(
            tg_url,
            json=tg_payload,
            timeout=15
        )

        print(
            f"4. 텔레그램 전송 완료 "
            f"(상태코드: {tg_res.status_code})"
        )

        if tg_res.status_code != 200:
            print("❌ 텔레그램 오류:")
            print(tg_res.text)

    except Exception as e:

        print("❌ 텔레그램 전송 오류:")
        print(e)


if __name__ == "__main__":
    main()
