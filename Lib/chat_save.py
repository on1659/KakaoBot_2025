import re
import pandas as pd
import datetime

# Sample chat log string
text = """[김영태] [오후 11:19] bsjs
[김영태] [오후 11:19] #all
[김영태] [오후 11:19] @김민수 @이더 
[김영태] [오후 11:21] #all
[김영태] [오후 11:22] ':@
[김영태] [오후 11:22] #all
[김영태] [오후 11:22] @@@@@@
[김영태] [오후 11:22] #all
[김영태] [오후 11:23] None
[김영태] [오후 11:23] #all
[김영태] [오후 11:23] None
[김영태] [오후 11:23] sj
[김영태] [오후 11:24] #all
[김영태] [오후 11:24] None
[김영태] [오후 11:25] #all
[김영태] [오후 11:25] sd
[김영태] [오후 11:25] #all
[김영태] [오후 11:25] @이더 
[김영태] [오후 11:27] #all
[김영태] [오후 11:27] @김민수 @이더 
[김영태] [오후 11:28] #all
[김영태] [오후 11:29] Q#s
[김영태] [오후 11:29] #all
[김영태] [오후 11:29] @@@@@
[김영태] [오후 11:30] @김민수 @이더 
[김영태] [오후 11:31] Ns
[김영태] [오후 11:31] #all
[김영태] [오후 11:32] @김민수 @이더 
[김영태] [오후 11:32] aks
[김영태] [오후 11:32] #all
[김영태] [오후 11:33] sjkd
[김영태] [오후 11:33] #all
[김영태] [오후 11:33] @김민수 @이더 
[김영태] [오후 11:34] #all
[김영태] [오후 11:40] sns
[김영태] [오후 11:41] #all
[김영태] [오후 11:45] zjz
[김영태] [오후 11:45] #all
[김영태] [오후 11:45] @김민수 @이더 
[김영태] [오후 11:46] #all
2025년 2월 24일 월요일
[김영태] [오후 12:59] ㄱㄴㄷ"""


def makeLastSaveText(df):
    """
    DataFrame의 첫 번째 컬럼(각 행에 채팅 로그 문자열이 있음)을 파싱하여,
    마지막 채팅 메시지를 문자열로 반환합니다.

    각 행은 다음 형식이어야 합니다:
        [이름] [시간] 메시지내용
    예를 들어, 날짜 라인이 "2025년 2월 25일 화요일"과 같이 있으면
    현재 날짜를 해당 날짜로 업데이트합니다.

    반환 예시:
        "김영태_2025-02-25 오후 11:29_Q#s_IDX3"
    (여기서 IDX3는 마지막 메시지가 DataFrame의 인덱스 3번 행에 있음을 의미)
    """
    # 채팅 메시지 패턴: [이름] [시간] 메시지내용
    chat_pattern = re.compile(
        r'^\[(?P<name>[^\]]+)\]\s+\[(?P<time>[^\]]+)\]\s+(?P<msg>.+)$'
    )
    # 날짜 라인 패턴: 예: "2025년 2월 25일 화요일"
    date_pattern = re.compile(r'^(?P<date>\d{4}년\s*\d+월\s*\d+일.*)$')

    records = []
    current_date = datetime.date.today()  # 기본 날짜

    # DataFrame의 첫 번째 컬럼의 각 행을 순회 (각 행은 채팅 로그 문자열)
    for idx, line in df[0].iteritems():
        line = str(line).strip()
        # 날짜 라인 처리
        date_match = date_pattern.match(line)
        if date_match:
            raw_date = date_match.group("date")
            tokens = raw_date.split()
            if len(tokens) >= 3:
                date_str = " ".join(tokens[:3])  # 예: "2025년 2월 25일"
                try:
                    date_obj = datetime.datetime.strptime(date_str, "%Y년 %m월 %d일")
                    current_date = date_obj.strftime("%Y-%m-%d")
                except Exception as e:
                    current_date = raw_date  # 변환 실패 시 원본 사용
            else:
                current_date = raw_date
            continue  # 날짜 라인은 채팅 메시지로 처리하지 않음

        # 채팅 메시지 처리
        chat_match = chat_pattern.match(line)
        if chat_match:
            time_str = chat_match.group("time")
            full_datetime = f"{current_date} {time_str}" if current_date else time_str
            records.append({
                "line_idx": idx,
                "사람이름": chat_match.group("name"),
                "메시지 날짜 및시간": full_datetime,
                "메시지내용": chat_match.group("msg").strip()
            })

    if not records:
        return ""

    # 파싱된 결과를 DataFrame으로 변환
    result_df = pd.DataFrame(records)
    # 마지막 메시지 선택
    last_idx = result_df.iloc[-1]["line_idx"]
    last_record = result_df.iloc[-1]

    # 최종 문자열 생성 (예: "김영태_2025-02-25 오후 11:29_Q#s_IDX3")
    combined_str = (
        f"{last_record['사람이름']}_"
        f"{last_record['메시지 날짜 및시간']}_"
        f"{last_record['메시지내용']}_"
        f"IDX{last_idx}"
    )
    return combined_str

def makeLastSaveText_222(text):
    """z
    전체 텍스트를 파싱하여 마지막 채팅 메시지를 반환합니다.
    동일 시간, 동일 내용 메시지의 경우에도 고유 인덱스(idx)를 추가하여 구분합니다.

    예시:
      입력 텍스트:
        [김영태] [오후 11:29] Q#s
        [김영태] [오후 11:29] Q#s
      출력 예시:
        "김영태_2025-02-24 오후 11:29_Q#s_idx1"
        (마지막 메시지의 인덱스가 1이면)
    """
    # 채팅 메시지 정규표현식: [이름] [시간] 메시지
    chat_pattern = re.compile(
        r'^\[(?P<name>[^\]]+)\]\s+\[(?P<time>[^\]]+)\]\s+(?P<msg>.+)$'
    )
    # 날짜 라인 정규표현식 (예: "2025년 2월 24일 월요일")
    date_pattern = re.compile(r'^(?P<date>\d{4}년\s*\d+월\s*\d+일.*)$')

    records = []
    current_date = datetime.date.today()  # 기본값: 오늘 날짜

    for line in text.splitlines():
        line = line.strip()
        # 날짜 라인 확인
        date_match = date_pattern.match(line)
        if date_match:
            raw_date = date_match.group("date")  # 예: "2025년 2월 24일 월요일"
            tokens = raw_date.split()
            if len(tokens) >= 3:
                date_str = " ".join(tokens[:3])  # "2025년 2월 24일"
                try:
                    date_obj = datetime.datetime.strptime(date_str, "%Y년 %m월 %d일")
                    current_date = date_obj.strftime("%Y-%m-%d")
                except Exception:
                    current_date = raw_date  # 변환 실패 시 원본 사용
            else:
                current_date = raw_date
            continue  # 날짜 라인은 메시지로 처리하지 않음

        # 채팅 메시지 확인
        chat_match = chat_pattern.match(line)
        if chat_match:
            time_str = chat_match.group("time")
            full_datetime = f"{current_date} {time_str}" if current_date else time_str
            records.append({
                "사람이름": chat_match.group("name"),
                "메시지 날짜 및시간": full_datetime,
                "메시지내용": chat_match.group("msg").strip()
            })

    if not records:
        return ""

    # 마지막 메시지의 인덱스를 포함하여 구분합니다.
    last_index = len(records) - 1
    last_record = records[-1]
    combined_str = (
        f"{last_record['사람이름']}_"
        f"{last_record['메시지 날짜 및시간']}_"
        f"{last_record['메시지내용']}_"
        f"idx{last_index}"
    )
    return combined_str

# a = makeLastSaveText(text)
# print(a)