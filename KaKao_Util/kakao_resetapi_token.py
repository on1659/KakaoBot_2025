import requests
import json
import os
from Lib import json_data_manager

ACCESS_TOKEN = os.environ.get("KAKAO_ACCESS_TOKEN")

# 환경변수에 값이 없으면, JSON 파일에서 키를 로드합니다.
if ACCESS_TOKEN is None:
    # 예를 들어, json_data_manager.load_api_keys()가 아래와 같이 딕셔너리를 반환한다고 가정합니다.
    # {
    #    "KAKAO_ACCESS_TOKEN": "your_client_id_here",
    #    "KAKAO_REDIRECT_CODE": "your_redirect_code_here",
    #    ...
    # }

    os.chdir('..')
    keys = json_data_manager.load_api_keys("api_key.json")
    # 각 키를 환경변수에 저장합니다.
    ACCESS_TOKEN = os.environ.get("KAKAO_ACCESS_TOKEN")


class Kakao:
    def __init__(self):
        self.app_key = ACCESS_TOKEN  # REST API 키 입력

        # 저장된 json 파일 읽어오기 (with 문은 __init__ 내에 들여쓰기되어야 함)
        with open("../kakao_token.json", "r") as fp:
            self.tokens = json.load(fp)

        self.refresh_token()

    # 카카오 토큰 갱신하기
    def refresh_token(self):
        url = "https://kauth.kakao.com/oauth/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": self.app_key,
            "refresh_token": self.tokens['refresh_token']
        }
        response = requests.post(url, data=data)
        result = response.json()

        if 'access_token' in result:
            self.tokens['access_token'] = result['access_token']
        if 'refresh_token' in result:
            self.tokens['refresh_token'] = result['refresh_token']

        with open("../kakao_token.json", "w") as fp:
            json.dump(self.tokens, fp)

    def send_to_kakao(self, text):
        url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
        headers = {"Authorization": "Bearer " + self.tokens['access_token']}
        content = {
            "object_type": "text",
            "text": text,
            "link": {"mobile_web_url": "http://m.naver.com"}
        }
        data = {"template_object": json.dumps(content)}
        res = requests.post(url, headers=headers, data=data)
        return res.json()


if __name__ == "__main__":
    kakao = Kakao()
    kakao.send_to_kakao("보낼 내용")
