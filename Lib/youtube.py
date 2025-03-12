from googleapiclient.discovery import build
import re
import requests
import os

class YoutubeVideoapi:
    def __init__(self):
        self.api_key = os.environ['YOUTUBE_API_KEY']  # Make sure this is correct!
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
    Result = YoutubeVideoapi().videolist(message)  # 아이디, 제목, 조회수, 댓글수, 좋아요수 추출
    print(Result)
    return Result

def GetMusicList():

    # Replace with your OAuth 2.0 access token.
    ACCESS_TOKEN = API_KEY
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {
        "part": "id",
        "mine": "true"
    }
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        channel_id = data["items"][0]["id"]
        print("Your Channel ID:", channel_id)
    else:
        print("Error:", response.status_code, response.text)