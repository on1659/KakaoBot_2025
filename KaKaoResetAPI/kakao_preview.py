import requests
import os

ACCESS_TOKEN = "ULozniXpyWuptw9xWGkJRPxN-kHASrvFAAAAAQo8IlIAAAGVqVdkA8c_xW4TVk05" # os.environ['KAKAO_ACCESS_TOKEN']  # Make sure this is correct!

def send_instagram_preview(opentalk_name, image_url, video_url, link_url):
    """
    KakaoTalk으로 Instagram 링크, 이미지, 비디오를 포함한 미리보기 메시지를 전송합니다.
    :param opentalk_name: 카카오톡 대화방 이름
    :param image_url: 이미지 URL (이미지가 있는 경우)
    :param video_url: 비디오 URL (비디오가 있는 경우)
    :param link_url: Instagram 링크 URL
    """
    headers = {
         "Authorization": "Bearer ${ACCESS_TOKEN}"
    }

    data = {
        "object_type": "text",
        "text": "Instagram Post Preview",
        "link": {
            "web_url": link_url,
            "mobile_web_url": link_url
        },
        "buttons": [{
            "title": "View on Instagram",
            "link": {
                "web_url": link_url
            }
        }]
    }

    # 이미지가 있다면 이미지도 전송
    if image_url:
        data["image_url"] = image_url

    # 비디오 URL이 있다면, 그 URL을 텍스트로 전송
    if video_url:
        data["text"] = f"Instagram Video: {video_url}"

    # 카카오톡 메시지 API 호출
    response = requests.post('https://kapi.kakao.com/v1/api/talk/friends/message/default/send', headers=headers, json=data)
    if response.status_code == 200:
        Helper.CustomPrint("Message sent successfully")
    else:
        Helper.CustomPrint("Failed to send message:", response.status_code, "\n", response.content)


# 사용 예시
if __name__ == "__main__":
    url = "https://www.instagram.com/reel/DHGOg5VJfTb/?igsh=ZTRhN241OXdnbXVv"
    # description, image_url, video_url = insta.get_instagram_post_summary_and_media(url)
    image_url = "https://scontent-ssn1-1.cdninstagram.com/v/t51.75761-15/483613588_17878588434266747_2390330666814293488_n.jpg?stp=cmp1_dst-jpg_e35_s640x640_tt6&_nc_cat=104&ccb=1-7&_nc_sid=18de74&_nc_ohc=bR-shA-iLhsQ7kNvgG14kHn&_nc_oc=Adi8_VXPQvwdklhiC8VulHiilSEYcrlm6xQ-WLK0_8Q3Wic_A33oJUz4fDfXG19K4Xg&_nc_zt=23&_nc_ht=scontent-ssn1-1.cdninstagram.com&_nc_gid=E_hKCOY4orz3BrNgKqBsdQ&oh=00_AYEcx0vuPP7_tvYzW1JHXyLX2On2TJqjTt_LOWsPJpyB5A&oe=67DE1D6D"
    link_url = url  # Instagram 링크
    video_url = ""

    send_instagram_preview("test_chat", image_url, video_url, link_url)
