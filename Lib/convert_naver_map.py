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
    text = text.replace(" ","", True)
    pattern = r'^\[(?P<tag>[^\]]+)\]\s+(?P<name>\S+)\s+(?P<address>.+)\s+(?P<url>https?://\S+)$'
    match = re.match(pattern, text)
    if match:
        tag = match.group('tag')
        name = match.group('name')
        address = match.group('address')
        url = match.group('url')
        return name, address, url
    else:
        return None, None, None


def parse_kakaomap_string_test(text):
    """
    Example input:
    [카카오맵] 할머니가래떡볶이 광진자양점
    서울 광진구 뚝섬로 656 1층 102호 (자양동) https://kko.kakao.com/_eyNAV1XoK
    """
    # Remove trailing/leading whitespace, including newlines
    text = text.strip()
    # Replace any internal newlines with a space or some delimiter
    text = text.replace('\n', ' ')

    # Regex pattern:
    # 1) ^\[카카오맵\] : must start with [카카오맵]
    # 2) \s+ : one or more spaces
    # 3) (?P<name>\S+) : store name (first group of non-whitespace chars),
    #    or expand if you want to allow spaces in the name
    # 4) \s+(?P<address>.+) : the rest is address + URL
    # 5) Capture the last part as optional URL
    #    if you want to separate them out specifically.
    pattern = r'^\[카카오맵\]\s+(?P<name>\S+)\s+(?P<address>.+)$'

    match = re.match(pattern, text)
    if not match:
        return None, None, None

    # For example: "할머니가래떡볶이 광진자양점" or "다솜" = name
    place_name = match.group('name')
    address_url_part = match.group('address')

    # If you want to parse the URL out of address, you can do a final split:
    # e.g. "서울 광진구 ... (자양동) https://kko.kakao.com/LzVBdQoif4"
    # We can look for an http or https link at the end.
    url_pattern = r'(https?://\S+)$'
    url_match = re.search(url_pattern, address_url_part)

    if url_match:
        url = url_match.group(1)
        # The rest (minus the URL) is the actual address
        address = address_url_part[: url_match.start()].strip()
    else:
        url = None
        address = address_url_part.strip()

    return place_name, address, url


test_sample1 = "[카카오맵] 할머니가래떡볶이 광진자양점\n서울 광진구 뚝섬로 656 1층 102호 (자양동) https://kko.kakao.com/_eyNAV1XoK"
test_sample2 = "[카카오맵] 다솜 서울 광진구 뚝섬로57가길 27-4 (자양동) https://kko.kakao.com/LzVBdQoif4"
test_sample3 = "[카카오맵] 자양동명진센트라임 서울 광진구 아차산로46가길 15 (자양동) https://kko.kakao.com/-YGaamj4Mg"
def main():

    result = GetData( "nouse", "[카카오맵]",test_sample3)
    print(result)


def GetData(opentalk_name, cheate_commnad, message):
    name, address, url  = parse_kakaomap_string_test(cheate_commnad + " " + message)
    Result =  MakeURL(name, address)
    return Result

