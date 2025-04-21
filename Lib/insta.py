import requests
from Lib import Helper
from bs4 import BeautifulSoup
from io import BytesIO
from PIL import Image
import win32clipboard
import win32con

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
    url = "https://www.instagram.com/reel/DHSFlcXysg4/?igsh=Y3E5bHRpbTh6NDhl"
    description, image_url, video_url = get_instagram_post_summary_and_media(url)
    Helper.CustomPrint("Instagram Post Summary:", description)
    if image_url:
        Helper.CustomPrint("Instagram Post Image URL:", image_url)
        # 이미지 URL이 있으면 클립보드에 복사
        copy_image_to_clipboard(image_url)
    if video_url:
        Helper.CustomPrint("Instagram Post Video URL:", video_url)