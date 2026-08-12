import os
import requests
from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

def main():
    print("1. Gemini API 요청 중 (Official SDK)...")
    try:
        # 공식 SDK Client 생성
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # 모델 호출
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="오늘 미국 증시 개장 전 주요 체크포인트 3가지를 텔레그램 메시지용으로 짧고 간결하게 한국어로 작성해줘."
        )
        report_text = response.text
        print("2. AI 리포트 생성 성공!")
    except Exception as e:
        report_text = f"API 요청 에러: {e}"
        print(f"오류 상세: {e}")

    print("3. 텔레그램 전송 중...")
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    tg_payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🚨 [미국 증시 브리핑]\n\n{report_text}"
    }
    
    tg_res = requests.post(tg_url, json=tg_payload, timeout=5)
    print(f"4. 텔레그램 전송 완료 (상태코드: {tg_res.status_code})")

if __name__ == "__main__":
    main()
