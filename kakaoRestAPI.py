import requests

# Replace with your actual access token
ACCESS_TOKEN = "221ed2c8526e7cca6fc941db1dd03e0a"

def send_kakao_message(text):
    """Send a message to yourself via KakaoTalk API"""

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    data = {
        "template_object": '{"object_type":"text","text":"' + text + '","link":{"web_url":"https://kakao.com"}}'
    }

    response = requests.post(url, headers=headers, data=data)

    if response.status_code == 200:
        print("✅ Message sent successfully!")
    else:
        print(f"❌ Failed to send message: {response.json()}")
