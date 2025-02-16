from googleapiclient.discovery import build
import pandas as pd
import datetime as dt
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

def GetData(keyword):
    Result = YoutubeVideoapi().videolist(keyword)  # 아이디, 제목, 조회수, 댓글수, 좋아요수 추출
    print(Result)
    return Result
