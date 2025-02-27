from ytmusicapi import YTMusic

# 인증 없이도 공개 플레이리스트를 조회할 수 있음
ytmusic = YTMusic()

# 플레이리스트 ID (YouTube Music URL에서 확인 가능)
playlist_id = "PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI"  # 예시 ID

# 플레이리스트 정보 가져오기
playlist = ytmusic.get_playlist(playlist_id)

# 결과 출력 (딕셔너리 형태)
print(playlist)