import os
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

def main():
    print("1. Gemini Interactions API 요청 중...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/interactions?key={GEMINI_API_KEY}"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Interactions API 필수 'type' 파라미터 추가
    payload = {
        "model": "models/gemini-2.5-flash",
        "input": {
            "type": "text",
            "text": "오늘 미국 증시 개장 전 주요 체크포인트 3가지를 텔레그램 메시지용으로 짧고 간결하게 한국어로 작성해줘."
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        res_json = response.json()
        
        if response.status_code == 200:
            outputs = res_json.get("outputs", [])
            if outputs and "text" in outputs[0]:
                report_text = outputs[0]["text"]
            elif "text" in res_json:
                report_text = res_json["text"]
            else:
                report_text = str(res_json)
            print("2. AI 리포트 생성 성공!")
        else:
            err_msg = res_json.get("error", {}).get("message", res_json)
            report_text = f"API 오류 ({response.status_code}): {err_msg}"
            print(report_text)
            
    except Exception as e:
        report_text = f"요청 에러: {e}"
        print(report_text)

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
