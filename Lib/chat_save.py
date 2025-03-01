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

def makeLastSaveText(text):
    # Pattern for chat messages: [Name] [Time] Message
    chat_pattern = (re.
    compile(
        r'^\[(?P<name>[^\]]+)\]\s+\[(?P<time>[^\]]+)\]\s+(?P<msg>.+)$'
    ))

    # Pattern for date lines (e.g., "2025년 2월 24일 월요일")
    date_pattern = re.compile(r'^(?P<date>\d{4}년\s*\d+월\s*\d+일.*)$')

    records = []
    current_date = datetime.date.today()

    for line in text.splitlines():
        line = line.strip()
        # Check if the line is a date line.
        date_match = date_pattern.match(line)
        if date_match:
            raw_date = date_match.group("date")  # 예: "2025년 2월 24일 월요일"
            tokens = raw_date.split()
            if len(tokens) >= 3:
                date_str = " ".join(tokens[:3])  # "2025년 2월 24일"
                try:
                    date_obj = datetime.datetime.strptime(date_str, "%Y년 %m월 %d일")
                    current_date = date_obj.strftime("%Y-%m-%d")
                except Exception as e:
                    current_date = raw_date  # 변환 실패 시 원본 사용
            else:
                current_date = raw_date
            continue  # 날짜 라인은 채팅 메시지로 처리하지 않음.

        # Check if the line is a chat message.
        chat_match = chat_pattern.match(line)
        if chat_match:
            # If a current_date exists, combine it with the time.
            time_str = chat_match.group("time")
            full_datetime = f"{current_date} {time_str}" if current_date else time_str
            records.append({
                "사람이름": chat_match.group("name"),
                "메시지 날짜 및시간": full_datetime,
                "메시지내용": chat_match.group("msg").strip()
            })

        if not records:
            return ""

        last_record = records[-1]
        combined_str = f"{last_record['사람이름']}_{last_record['메시지 날짜 및시간']}_{last_record['메시지내용']}"
        return combined_str


# a = makeLastSaveText(text)
# print(a)