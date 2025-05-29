from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import re
import requests
import os
import pickle

# from Lib import Helper

class Helper:
    def CustomPrint(self, message, saveLog = 0, abc = 0):
        print(message)

class YoutubeVideoapi:
    def __init__(self):
        self.api_key = os.environ['YOUTUBE_API_KEY']
        self.youtube = build("youtube", "v3", developerKey=self.api_key)
        self.oauth_youtube = None
        self.credentials = None
        self.setup_oauth()

    def setup_oauth(self):
        """OAuth2 인증을 설정합니다."""
        SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']
        creds = None

        # 토큰 파일이 있으면 로드
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)

        # 유효한 인증 정보가 없으면 새로 인증
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # 현재 스크립트의 디렉토리를 기준으로 상대 경로 계산
                current_dir = os.path.dirname(os.path.abspath(__file__))
                client_secrets_path = os.path.join(os.path.dirname(current_dir), 'config', 'youtube_client_secrets.json')
                flow = InstalledAppFlow.from_client_secrets_file(
                    client_secrets_path, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # 토큰 저장
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        self.credentials = creds
        self.oauth_youtube = build("youtube", "v3", credentials=creds)

    def get_subscriptions(self):
        """구독 중인 채널 목록을 가져옵니다."""
        if not self.oauth_youtube:
            print("OAuth 인증이 필요합니다. client_secrets.json 파일을 확인해주세요.")
            return []

        try:
            # 구독 목록 가져오기
            subscriptions = self.oauth_youtube.subscriptions().list(
                part="snippet",
                mine=True,
                maxResults=50  # 최대 50개 채널 정보 가져오기
            ).execute()

            # 채널 정보 정리
            channels = []
            for item in subscriptions.get("items", []):
                channel = {
                    'id': item['snippet']['resourceId']['channelId'],
                    'title': item['snippet']['title'],
                    'description': item['snippet']['description']
                }
                channels.append(channel)
            
            return channels
        except Exception as e:
            print(f"구독 정보를 가져오는 중 오류 발생: {str(e)}")
            return []

    def best_video_by_score(self, keyword):
        # 1. 검색 결과 videoId 목록 얻기
        search_request = self.youtube.search().list(
            q=keyword,
            order="relevance",  # 관련도 순으로 정렬
            part="snippet",
            maxResults=10
        )
        search_response = search_request.execute()
        video_ids = [
            item["id"]["videoId"]
            for item in search_response.get("items", [])
            if item["id"]["kind"] == "youtube#video"
        ]
        if not video_ids:
            return "No video found."

        # 2. videoId별 상세정보 얻기
        videos_request = self.youtube.videos().list(
            id=",".join(video_ids),
            part="statistics,snippet"
        )
        videos_response = videos_request.execute()

        # 3. 각 영상에 대해 커스텀 점수 계산
        video_scores = []
        for item in videos_response.get("items", []):
            stats = item.get("statistics", {})
            view_count = int(stats.get("viewCount", 0))
            like_count = int(stats.get("likeCount", 0))
            comment_count = int(stats.get("commentCount", 0))
            channel_id = item['snippet']['channelId']
            
            # 구독 상태 확인
            try:
                subscription_status = self.oauth_youtube.subscriptions().list(
                    part="snippet",
                    forChannelId=channel_id,
                    mine=True
                ).execute()
                is_subscribed = len(subscription_status.get("items", [])) > 0
            except:
                is_subscribed = False
            
            # 커스텀 가중치 계산: 조회수*1 + 좋아요*3 + 댓글*5
            base_score = view_count * 1 + like_count * 3 + comment_count * 5
            
            # 구독 중인 채널의 영상은 가중치 2배 적용
            if is_subscribed:
                score = base_score * 2
            else:
                score = base_score
                
            video_scores.append({
                'url': f"https://www.youtube.com/watch?v={item['id']}",
                'title': item['snippet']['title'],
                'channel_title': item['snippet']['channelTitle'],
                'views': view_count,
                'likes': like_count,
                'comments': comment_count,
                'score': score,
                'is_subscribed': is_subscribed,
                'base_score': base_score  # 기본 점수도 저장
            })

        # 구독 채널 우선, 그 다음 점수순으로 정렬
        video_scores.sort(key=lambda x: (-x['is_subscribed'], -x['score']))
        
        # 상위 5개 영상 정보 출력
        print(f"\n=== '{keyword}' 검색 결과 상위 5개 영상 ===")
        print("(구독 채널 우선 정렬)")
        for i, video in enumerate(video_scores[:5], 1):
            subscription_status = "✅ 구독중" if video['is_subscribed'] else "❌ 구독안함"
            print(f"\n{i}위 영상:")
            print(f"제목: {video['title']}")
            print(f"채널: {video['channel_title']} ({subscription_status})")
            print(f"조회수: {video['views']:,}")
            print(f"좋아요: {video['likes']:,}")
            print(f"댓글수: {video['comments']:,}")
            print(f"기본점수: {video['base_score']:,}")
            print(f"최종점수: {video['score']:,} {'(구독채널 2배 가중치 적용)' if video['is_subscribed'] else ''}")
            print(f"링크: {video['url']}")
        print("\n===============================\n")

        # 가장 높은 점수의 영상 URL 반환
        return video_scores[0]['url'] if video_scores else "No video found."

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

    def GetMusicList(self):
        # Replace with your OAuth 2.0 access token.
        ACCESS_TOKEN = self.api_key
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
            Helper.CustomPrint("Your Channel ID:", channel_id)
            return channel_id
        else:
            Helper.CustomPrint("Error:", response.status_code, response.text)
            return None

def GetData(opentalk_name, cheate_commnad, message):
    Result = YoutubeVideoapi().best_video_by_score(message)  # 커스텀 가중치 기반 영상 선 택
    return Result, "text"

# ----------------------
# GetData 함수 테스트 코드
# ----------------------
if __name__ == "__main__":
    opentalk_name = "테스트오픈톡"
    cheate_commnad = "!유튜브"
    message = "일루전"  # 검색어

    result, result_type = GetData(opentalk_name, cheate_commnad, message)
    print("GetData 결과:", result)
    print("타입:", result_type)
    assert result.startswith("https://www.youtube.com/watch?v=") or result == "No video found."
    assert result_type == "text"
