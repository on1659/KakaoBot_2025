import re
import urllib.parse


def MakeURL(location_name, address):
    query = f"{location_name} {address}"
    encoded_query = urllib.parse.quote(query)
    url = f"https://map.naver.com/v5/search/{encoded_query}"
    return url

def parse_kakaomap_string(text):
    """
    하나의 문자열에서 태그, 업체명, 주소, URL을 추출합니다.
    예시 입력:
        "[카카오맵] 다솜 서울 광진구 뚝섬로57가길 27-4 (자양동) https://kko.kakao.com/LzVBdQoif4"
    """
    # 정규식 패턴:
    #   ^\[(?P<tag>[^\]]+)\]      -> 문자열 시작에 [와 ] 사이의 태그 (예: 카카오맵)
    #   \s+(?P<name>\S+)          -> 공백 뒤 첫 단어를 업체명으로 처리
    #   \s+(?P<address>.+)        -> 나머지 부분 중 마지막 공백 전까지를 주소로 (주소에 공백 포함)
    #   \s+(?P<url>https?://\S+)$  -> 마지막에 있는 URL (http:// 또는 https://로 시작하는 부분)
    pattern = r'^\[(?P<tag>[^\]]+)\]\s+(?P<name>\S+)\s+(?P<address>.+)\s+(?P<url>https?://\S+)$'
    match = re.match(pattern, text)
    if match:
        tag = match.group('tag')
        name = match.group('name')
        address = match.group('address')
        url = match.group('url')
        return tag, name, address, url
    else:
        return None, None, None, None

def main():
    result = GetData( "[카카오맵] 다솜 서울 광진구 뚝섬로57가길 27-4 (자양동) https://kko.kakao.com/LzVBdQoif4")
    print(result)


def GetData(opentalk_name, cheate_commnad, message):
    tag, name, address, url  = parse_kakaomap_string(message)
    Result =  MakeURL(name, address)
    return Result
