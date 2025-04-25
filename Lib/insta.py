import requests
import re
from Lib import Helper
from io import BytesIO
from PIL import Image
import win32clipboard
import win32con
import instaloader

def extract_shortcode(url):
    """
    Instagram URL에서 shortcode 추출 (Post와 Reels 모두 지원)
    """
    match = re.search(r"(/(p|reel)/([^/?]+)/)", url)
    if match:
        return match.group(3)  # shortcode 반환
    else:
        raise ValueError("URL에서 shortcode를 추출할 수 없습니다.")

def ig_thumb(url):
    try:
        shortcode = extract_shortcode(url)
        L = instaloader.Instaloader(download_pictures=False, quiet=True)
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        return post.url  # 썸네일 URL
    except Exception as e:
        Helper.CustomPrint(f"Error extracting image: {e}")
        return None

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
    image_url = ig_thumb(cheate_commnad + message)

    if image_url is None:
        return "Not Found Image", "text"

    Helper.CustomPrint("Instagram Post Image URL:", image_url)
    copy_image_to_clipboard(image_url)

    return "", "image"

# 사용 예시
if __name__ == "__main__":
   # url = "https://www.instagram.com/reel/DIqS2bfS0_q/?igsh=MXQ2b3V3OGcwbGRmcg=="
    # 또는
    url = "https://www.instagram.com/p/DIpzzT_TBor/?igsh=MWVsaWZpMXBweXk2Zw=="

    image_url = ig_thumb(url)
    if image_url:
        Helper.CustomPrint(f"Instagram Post Image URL: {image_url}")
        # 이미지 URL이 있으면 클립보드에 복사
        copy_image_to_clipboard(image_url)
