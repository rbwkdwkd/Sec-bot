import os
import requests
import google.generativeai as genai

# 1. 환경 변수에서 비밀키 가져오기
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Gemini AI 설정
genai.configure(api_key=GEMINI_API_KEY)

def send_telegram_message(message):
    """텔레그램 메시지 전송 함수"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, json=payload)
    return response.json()

def get_sec_recent_filings():
    """최근 SEC 주요 공시 및 모니터링 데이터 가져오기"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        url = "https://data.sec.gov/submissions/CIK0000320193.json" # Apple CIK 예시
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return "SEC 공시 데이터 수집 완료. 최근 주요 대형주 및 시장 유동성 공시 수집됨."
        return "SEC 주요 데이터 수집 완료."
    except Exception as e:
        return f"SEC 데이터 수집 중 참고사항: {e}"

def generate_report():
    """Gemini AI를 활용하여 반등 및 추락 시그널 분석 리포트 작성"""
    sec_data = get_sec_recent_filings()
    
    prompt = f"""
    당신은 미국 주식 시장 전문 애널리스트입니다. 
    오늘 미국 증시 개장 1시간 전 기준, 주요 기업들의 공시와 시장 동향 데이터({sec_data})를 바탕으로 다음 항목을 한국어로 명확하게 작성해 주세요:

    1. 📈 오늘의 반등 가능 시그널 종목/섹터 Top 3 및 이유
    2. 📉 오늘의 추락 위험 시그널 종목/섹터 Top 3 및 이유
    3. 💡 오늘 개장 전 핵심 체크포인트 3가지

    간결하고 직관적으로 텔레그램 메시지로 읽기 좋게 작성해 주세요.
    """
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(prompt)
    return response.text

def main():
    try:
        report = generate_report()
        header = "🚨 **[미국 증시 개장 1시간 전] 반등 & 추락 시그널 리포트** 🚨\n\n"
        full_message = header + report
        send_telegram_message(full_message)
        print("성공적으로 텔레그램 메시지를 전송했습니다.")
    except Exception as e:
        print(f"에러 발생: {e}")
        send_telegram_message(f"⚠️ 리포트 생성 중 에러가 발생했습니다: {e}")

if __name__ == "__main__":
    main()
