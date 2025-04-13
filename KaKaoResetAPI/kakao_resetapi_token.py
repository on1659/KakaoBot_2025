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

    def get_friend_uuid(self):
        url = "https://kapi.kakao.com/v1/api/talk/friends"
        headers = {"Authorization": "Bearer " + self.tokens['access_token']}
        response = requests.get(url, headers=headers)
        result = response.json()

        if response.status_code != 200:
            # 에러 발생 시 전체 응답을 반환
            return result

        # 'elements' 필드에 친구 리스트가 포함되어 있습니다.
        friend_list = result.get("elements", [])
        # 각 친구의 uuid와 닉네임 정보를 추출합니다.
        friends = [{"uuid": friend.get("uuid"), "nickname": friend.get("profile_nickname")} for friend in friend_list]
        return friends

if __name__ == "__main__":
    kakao = Kakao()
    result = kakao.send_to_kakao("나에게메시지보내기는 이걸로 성공?")
    print(result)
    r = kakao.get_friend_uuid()
    print(r)