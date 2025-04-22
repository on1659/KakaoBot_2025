import requests
import re
from Lib import Helper
from bs4 import BeautifulSoup
from io import BytesIO
from PIL import Image
import win32clipboard
import win32con
import json


def get_instagram_post_summary_and_media_test(url: str):
    oembed_url = "https://api.instagram.com/oembed"
    params = {"url": url, "omitscript": True}

    try:
        resp = requests.get(oembed_url, params=params)

        if resp.status_code != 200:
            return "", None, None

        # 응답이 JSON이 아닌 경우 HTML로 처리
        if resp.headers.get("Content-Type") != "application/json":
            print("응답이 JSON이 아니고 HTML 형식입니다. HTML에서 필요한 정보를 추출합니다.")
            soup = BeautifulSoup(resp.text, "html.parser")

            # 필요한 데이터 추출 (예: thumbnail_url 등)
            thumbnail_url = None

            # Instagram oEmbed 응답에서 썸네일 URL을 찾아서 저장하는 예시
            # 실제 oEmbed 응답에는 `thumbnail_url`이 포함된 경우가 많습니다.
            # HTML 형식에 따라 적절한 방식으로 추출해야 합니다.
            if soup.find('meta', property='og:image'):
                thumbnail_url = soup.find('meta', property='og:image')['content']

            return "", thumbnail_url, ""  # 이미지 URL만 반환

        # 정상적으로 JSON인 경우
        data = resp.json()
        return "", data.get("thumbnail_url"), ""

    except requests.exceptions.RequestException as e:
        print(f"Error during request: {e}")
        return "", None, None
    except Exception as e:
        print(f"Error: {e}")
        return "", None, None

def get_instagram_post_summary_and_media(url):
    """
    Instagram 게시물에서 설명, 이미지 또는 비디오 URL을 추출합니다.
    :param url: Instagram 게시물 링크
    :return: 설명, 이미지 URL, 비디오 URL
    """
    # Instagram 페이지 가져오기
    response = requests.get(url)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')

        # 설명 추출 (og:description)
        try:
            description = soup.find('meta', property='og:description')['content']
        except (AttributeError, TypeError):
            description = "이 게시물에 대한 설명이 없습니다."

        # 이미지 URL 추출 (og:image)
        image_url = None
        try:
            image_url = soup.find('meta', property='og:image')['content']
        except (AttributeError, TypeError):
            image_url = None

        # 비디오 URL 추출 (og:video)
        video_url = None
        try:
            video_url = soup.find('meta', property='og:video')['content']
        except (AttributeError, TypeError):
            video_url = None

        return description, image_url, video_url
    else:
        return "페이지를 불러오지 못했습니다.", None, None

def copy_image_to_clipboard(image_url):
    """
    주어진 이미지 URL에서 이미지를 다운로드하여 Windows 클립보드에 복사합니다.
    """
    response = requests.get(image_url)
    if response.status_code == 200:
        image_data = response.content
        image = Image.open(BytesIO(image_data))
        # BMP 포맷으로 변환 (클립보드에 복사할 때는 BMP 형식의 데이터가 필요)
        output = BytesIO()
        image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]  # BMP 헤더의 처음 14바이트는 제거
        output.close()

        # 클립보드에 이미지 복사
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_DIB, data)
        win32clipboard.CloseClipboard()
        Helper.CustomPrint("이미지가 클립보드에 복사되었습니다.")
    else:
        Helper.CustomPrint("이미지 다운로드에 실패했습니다.")

def GetData(opentalk_name, cheate_commnad, message):
    description, image_url, video_url = get_instagram_post_summary_and_media(cheate_commnad + message)

    if image_url == None and video_url == None:
        return "Not Found Image", "text"

    Helper.CustomPrint("Instagram Post Summary:", description)
    if image_url:
        Helper.CustomPrint("Instagram Post Image URL:", image_url)
        # 이미지 URL이 있으면 클립보드에 복사
        copy_image_to_clipboard(image_url)
    if video_url:
        Helper.CustomPrint("Instagram Post Video URL:", video_url)
    return "", "image"

# 사용 예시
if __name__ == "__main__":
    url = "https://www.instagram.com/p/DIpzzT_TBor/?igsh=MWVsaWZpMXBweXk2Zw=="
    description, image_url, video_url = get_instagram_post_summary_and_media_test(url)
    Helper.CustomPrint("Instagram Post Summary:", description)
    if image_url:
        Helper.CustomPrint("Instagram Post Image URL:", image_url)
        # 이미지 URL이 있으면 클립보드에 복사
        copy_image_to_clipboard(image_url)
    if video_url:
        Helper.CustomPrint("Instagram Post Video URL:", video_url)