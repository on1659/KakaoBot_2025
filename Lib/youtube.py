from googleapiclient.discovery import build
import re
import urllib.parse

def split_youtube_command(chat_command, command_str):
    """
    #유툽 [key word] 형식의 문자열에서
    해시태그와 키워드를 분리합니다.
    예시: "#유툽 [Python tutorials]" -> ("#유툽", "Python tutorials")
    """
    # 정규식 패턴을 동적으로 생성
    pattern = r"^" + re.escape(chat_command) + r"\s*"
    return re.sub(pattern, "", command_str)

class YoutubeVideoapi:
    def __init__(self):
        self.api_key = "AIzaSyArFIWSjhEw7HpJp4mDwCVlPSHs3Kahqv4"  # Make sure this is correct!
        self.youtube = build("youtube", "v3", developerKey=self.api_key)

    def videolist(self, keyword):
        request = self.youtube.search().list(
            q=keyword,
            order="viewCount",
            part="snippet",
            maxResults=20
        )
        response =  request.execute()

        if "items" in response and len(response["items"]) > 0:
            video_id = response["items"][0]["id"]["videoId"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            return video_url
        else:
            return "No video found."

def GetData(opentalk_name, cheate_commnad, message):
    keyword = split_youtube_command(cheate_commnad, message)
    Result = YoutubeVideoapi().videolist(keyword)  # 아이디, 제목, 조회수, 댓글수, 좋아요수 추출
    print(Result)
    return Result
