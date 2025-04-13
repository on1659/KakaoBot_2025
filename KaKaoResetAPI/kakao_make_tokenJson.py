import requests
import json
import os
from Lib import json_data_manager

url = "https://kauth.kakao.com/oauth/token"
client_id = os.environ.get("KAKAO_ACCESS_TOKEN")
code = os.environ.get("KAKAO_REDIRECT_CODE")

# 환경변수에 값이 없으면, JSON 파일에서 키를 로드합니다.
if client_id is None or code is None:
    # 예를 들어, json_data_manager.load_api_keys()가 아래와 같이 딕셔너리를 반환한다고 가정합니다.
    # {
    #    "KAKAO_ACCESS_TOKEN": "your_client_id_here",
    #    "KAKAO_REDIRECT_CODE": "your_redirect_code_here",
    #    ...
    # }

    os.chdir('..')
    keys = json_data_manager.load_api_keys("api_key.json")
    # 각 키를 환경변수에 저장합니다.
    client_id = os.environ.get("KAKAO_ACCESS_TOKEN")
    code = os.environ.get("KAKAO_REDIRECT_CODE")

data = {
"grant_type" : "authorization_code",
"client_id" : client_id,
"redirect_uri" : "http://localhost",
"code" : code
}

response = requests.post(url, data=data)
tokens = response.json()

# 토큰을 파일로 저장하기
if "access_token" in tokens:
    with open("../kakao_token.json", "w") as fp:
        json.dump(tokens, fp)
        print("Tokens saved successfully")
else:
    print(tokens)