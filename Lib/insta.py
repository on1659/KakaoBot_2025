import requests
import re
from Lib import Helper
from io import BytesIO
from PIL import Image
import win32clipboard
import win32con
import instaloader
import time
import random
from datetime import datetime

def log_error(error_msg):
    """
    에러를 로그 파일에 기록합니다.
    """
    log_file = "saved/instagram_errors.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {error_msg}\n")

def extract_shortcode(url):
    """
    Instagram URL에서 shortcode 추출 (Post와 Reels 모두 지원)
    """
    match = re.search(r"(/(p|reel)/([^/?]+)/)", url)
    if match:
        return match.group(3)  # shortcode 반환
    else:
        error_msg = f"URL에서 shortcode를 추출할 수 없습니다: {url}"
        Helper.CustomPrint(f"❌ {error_msg}")
        raise ValueError(error_msg)

def ig_thumb(url, max_retries=3):
    """
    Instagram 썸네일 URL을 가져오는 함수
    max_retries: 최대 재시도 횟수
    """
    for attempt in range(max_retries):
        try:
            shortcode = extract_shortcode(url)
            L = instaloader.Instaloader(
                download_pictures=False,
                quiet=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            
            # 랜덤 딜레이 추가 (1-3초)
            time.sleep(random.uniform(1, 3))
            
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            return post.url  # 썸네일 URL
            
        except instaloader.exceptions.InstaloaderException as e:
            error_msg = f"Instagram API 접근 오류 (시도 {attempt + 1}/{max_retries}): {str(e)}"
            Helper.CustomPrint(f"❌ {error_msg}")
            
            if attempt < max_retries - 1:
                # 재시도 전 대기 시간 (점진적 증가)
                wait_time = (attempt + 1) * 5
                time.sleep(wait_time)
            else:
                return None
                
        except Exception as e:
            error_msg = f"예상치 못한 오류 발생: {str(e)}"
            Helper.CustomPrint(f"❌ {error_msg}")
            return None

def copy_image_to_clipboard(image_url):
    """
    주어진 이미지 URL에서 이미지를 다운로드하여 Windows 클립보드에 복사합니다.
    """
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            image_data = response.content
            image = Image.open(BytesIO(image_data))
            # BMP 포맷으로 변환
            output = BytesIO()
            image.convert("RGB").save(output, "BMP")
            data = output.getvalue()[14:]  # BMP 헤더 제거
            output.close()

            # 클립보드에 이미지 복사
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_DIB, data)
            win32clipboard.CloseClipboard()
            Helper.CustomPrint("✅ 이미지가 클립보드에 복사되었습니다.")
        else:
            error_msg = f"이미지 다운로드 실패 (상태 코드: {response.status_code})"
            Helper.CustomPrint(f"❌ {error_msg}")
    except Exception as e:
        error_msg = f"이미지 복사 중 오류 발생: {str(e)}"
        Helper.CustomPrint(f"❌ {error_msg}")

def GetData(opentalk_name, cheate_commnad, message):
    image_url = ig_thumb(cheate_commnad + message)

    if image_url is None:
        return "Not Found Image", "text"

    Helper.CustomPrint(f"✅ Instagram Post Image URL: {image_url}")
    copy_image_to_clipboard(image_url)

    return "", "image"

# 사용 예시
if __name__ == "__main__":
    url = "https://www.instagram.com/p/DIpzzT_TBor/?igsh=MWVsaWZpMXBweXk2Zw=="
    image_url = ig_thumb(url)
    if image_url:
        Helper.CustomPrint(f"✅ Instagram Post Image URL: {image_url}")
        copy_image_to_clipboard(image_url)
