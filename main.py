import os
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

def main():
    print("1. Gemini API 요청 중 (HTTP Direct)...")
    # 모델명 경로 규격 반영 (models/gemini-1.5-flash)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{
            "parts": [{"text": "오늘 미국 증시 개장 전 주요 체크포인트 3가지를 텔레그램 메시지용으로 짧고 간결하게 한국어로 작성해줘."}]
        }]
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        res_json = response.json()
        
        if response.status_code == 200:
            report_text = res_json['candidates'][0]['content']['parts'][0]['text']
            print("2. AI 리포트 생성 성공!")
        else:
            report_text = f"API 오류 ({response.status_code}): {res_json.get('error', {}).get('message', '알 수 없는 오류')}"
            print(report_text)
    except Exception as e:
        report_text = f"요청 에러: {e}"
        print(report_text)

    print("3. 텔레그램 전송 중...")
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🚨 [미국 증시 브리핑]\n\n{report_text}"
    }
    
    tg_res = requests.post(tg_url, json=payload, timeout=5)
    print(f"4. 텔레그램 응답 상태코드: {tg_res.status_code}")
    print(f"5. 텔레그램 응답 내용: {tg_res.text}")

if __name__ == "__main__":
    main()
    
