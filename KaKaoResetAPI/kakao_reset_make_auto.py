from flask import Flask, request, redirect
import webbrowser

app = Flask(__name__)

@app.route("/")
def index():
    # 카카오 개발자 콘솔에서 발급받은 REST API 키를 입력하세요.
    client_id = ""
    # 카카오 개발자 콘솔에 등록한 redirect URI와 일치해야 합니다.
    redirect_uri = "http://localhost:5000/callback"
    # 필요한 scope(예: talk_friends, talk_message) 추가
    scope = "talk_friends,talk_message"
    # 카카오 인증 URL 생성
    kakao_auth_url = (
        f"https://kauth.kakao.com/oauth/authorize?"
        f"client_id={client_id}&redirect_uri={redirect_uri}"
        f"&response_type=code&scope={scope}"
    )
    # 사용자를 카카오 로그인 페이지로 리다이렉트합니다.
    return redirect(kakao_auth_url)

@app.route("/callback")
def callback():
    # 카카오가 리다이렉트 시 URL 쿼리 파라미터로 전달한 'code' 값을 추출합니다.
    code = request.args.get("code")
    if code:
        return f"Authorization code received: {code}"
    else:
        return "No code received", 400

if __name__ == "__main__":
    # 기본 브라우저에서 앱을 오픈합니다.
    webbrowser.open("http://localhost:5000")
    app.run(port=5000)
