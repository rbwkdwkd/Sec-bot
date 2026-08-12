import os
import requests
import google.generativeai as genai

# 환경 변수 로드
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    """텔레그램 메시지 안전 전송"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # 텔레그램 글자 수 제한(4000자) 대응 자르기
    for i in range(0, len(message), 3500):
        chunk = message[i:i+3500]
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"메시지 전송 실패: {e}")

def generate_report():
    """Gemini AI 시그널 분석"""
    genai.configure(api_key=GEMINI_API_KEY)
    
    prompt = """
    당신은 미국 주식 시장 전문 애널리스트입니다.
    오늘 미국 증시 개장 1시간 전 기준, 주요 기업 및 시장 동향을 분석하여 다음 항목을 한국어로 작성해 주세요:

    1. 📈 오늘의 반등 가능 시그널 종목/섹터 Top 3 및 이유
    2. 📉 오늘의 추락 위험 시그널 종목/섹터 Top 3 및 이유
    3. 💡 오늘 개장 전 핵심 체크포인트 3가지

    모바일 텔레그램으로 읽기 쉽고 깔끔하게 작성해 주세요.
    """
    
    # 가볍고 빠르며 안정적인 최신 flash 모델 사용
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content(prompt)
    return response.text

def main():
    print("1. AI 분석 시작...")
    try:
        report = generate_report()
        header = "🚨 **[미국 증시 개장 1시간 전] 반등 & 추락 시그널 리포트**\n\n"
        full_message = header + report
        print("2. 텔레그램 전송 중...")
        send_telegram_message(full_message)
        print("3. 모든 작업 완료!")
    except Exception as e:
        error_msg = f"⚠️ 리포트 생성 중 에러 발생: {e}"
        print(error_msg)
        send_telegram_message(error_msg)

if __name__ == "__main__":
    main()
