import re, time
import pandas as pd # 가져온 채팅내용 DF로 쓸거라서
import KaKao_Util.kakao_openroom as OpenRoom
import KaKao_Util.kakao_coppaste as CopyPaste
import KaKao_Util.kakak_send as Send
import subprocess
import os

from Lib import youtube, convert_naver_map, every_mention, chatroom_data_manager

# # 카톡창 이름, (활성화 상태의 열려있는 창)
kakao_opentalk_name_List = [
   # '하트시그널 토론회장',
     '테스트방이야'
   # ,'이더'
]

chat_command_Map = [
    ['#유툽', youtube.GetData],
    ['[카카오맵]', convert_naver_map.GetData],
    ['#all', every_mention.GetData],
    ['#방인원',chatroom_data_manager.save_chatroom_info]
    ]

def CustomPrint(opentalk_name, *messages):
    full_message = " ".join(str(m) for m in messages)
    print(f"[{opentalk_name}] {full_message}")

# # 채팅내용 초기 저장 _ 마지막 채팅
def chat_last_save(opentalk_name):
    OpenRoom.chat_room(opentalk_name, 1)  # 채팅방 열기
    ttext = CopyPaste.copy_cheat(opentalk_name, 1)  # 채팅내용 가져오기

    a = ttext.split('\r\n')   # \r\n 으로 스플릿 __ 대화내용 인용의 경우 \r 때문에 해당안됨
    df = pd.DataFrame(a)    # DF 으로 바꾸기

    df_len_size = len(df)

    df[0] = df[0].str.replace(r'\[([\S\s]+)\] \[(오전|오후)([0-9:\s]+)\] ', '', regex=True)  # 정규식으로 채팅내용만 남기기
    if len(df) < 2:
        print("chat_last_save error")
        return "", ""

    return df_len_size, df.iloc[-2, 0] #hat_save.makeLastSaveText(df.iloc[-2, 0])

def split_command(chat_command, command_str):
    """
    #유툽 [key word] 형식의 문자열에서
    해시태그와 키워드를 분리합니다.
    예시: "#유툽 [Python tutorials]" -> ("#유툽", "Python tutorials")
    """
    # 정규식 패턴을 동적으로 생성
    pattern = r"^" + re.escape(chat_command) + r"\s*"
    return re.sub(pattern, "", command_str)


# # 채팅방 커멘드 체크
def chat_chek_command(opentalk_name, copy_message_size, last_message):

    OpenRoom.chat_room(opentalk_name)  # 채팅방 열기
    copy_text = CopyPaste.copy_cheat(opentalk_name)  # 채팅내용 가져오기

    copy_text = copy_text.split('\r\n')  # \r\n 으로 스플릿 __ 대화내용 인용의 경우 \r 때문에 해당안됨
    df = pd.DataFrame(copy_text)  # DF 으로 바꾸기

    df[0] = df[0].str.replace(r'\[([\S\s]+)\] \[(오전|오후)([0-9:\s]+)\] ', '', regex=True)    # 정규식으로 채팅내용만 남기기

    if len(df) < 2:
        CustomPrint(opentalk_name, "채팅 못 읽음")
        return "", ""

    df_len_size = len(df)

    if df.iloc[-2, 0] == last_message and df_len_size== copy_message_size:
        CustomPrint(opentalk_name, "방에 채팅 없었음.. ")
        return df.index[-2], df.iloc[-2, 0]
    else:
        CustomPrint(opentalk_name, "방에 채팅 있었음!")

        df1 = df.iloc[copy_message_size +1 : , 0]   # 최근 채팅내용만 남김

        for chat_command, chat_func in chat_command_Map:
            found = df1[ df1.str.contains(chat_command) ]    # 챗 카운트

            if 1 <= int(found.count()):
                message = split_command(chat_command, found.iloc[0])
                resultString = chat_func(opentalk_name, chat_command, message)
                CustomPrint(opentalk_name,  f"✅ -------커멘드 [{found.iloc[0]}] 확인")

                if resultString is not None:
                    Send.sendtext(opentalk_name, resultString)  # 메시지 전송
                    CustomPrint(opentalk_name, f"✅ Message sent to : {resultString}")

                # 명령어 여러개 쓸경우 리턴값으로 각각 빼서 쓰면 될듯. 일단 테스트용으로 위에 하드코딩 해둠
                return df_len_size, df.iloc[-2, 0]

        CustomPrint(opentalk_name, "커멘드 미확인")
        return df_len_size, df.iloc[-2, 0]

def main():
    num_chatrooms = len(kakao_opentalk_name_List)
    last_copy_size = ["" for _ in range(num_chatrooms)]
    last_stringList = ["" for _ in range(num_chatrooms)]

    for i, name in enumerate(kakao_opentalk_name_List):
        last_copy_size[i], last_stringList[i] = chat_last_save(name)  # 초기설정 _ 마지막채팅 저장

    while True:
        print("실행중.................")
        for i, name in enumerate(kakao_opentalk_name_List):
            last_copy_size[i], last_stringList[i] = chat_chek_command(name, last_copy_size[i], last_stringList[i])  # 초기설정 _ 마지막채팅 저장
        time.sleep(1)

if __name__ == '__main__':
  # batch_file_path = r"D:\Work\Python\KakaoBot_2025\regist_api.bat"
#
  # # 1) 배치 파일 실행 후, set 출력까지 받고, 파이썬에서 표준출력으로 수신
  # result = subprocess.run(
  #     ['cmd', '/c', batch_file_path],
  #     capture_output=True,  # stdout, stderr 캡처
  #     text=True  # 출력이 문자열(str)로 들어오도록
  # )
#
  # # 2) result.stdout에 'set' 명령의 결과가 들어있음
  # lines = result.stdout.splitlines()
#
  # for line in lines:
  #     # 예) line: 'MY_API_KEY=abcd1234' 꼴
  #     if '=' in line:
  #         key, val = line.split('=', 1)
  #         # 여기서 원하는 조건에 맞춰 필터할 수도 있음 (예: key.startswith('MY_'))
  #         os.environ[key] = val  # 파이썬 환경 변수에 반영
#
  # # 이제 os.environ['MY_API_KEY'] 값을 확인해보면
  # print("YOUTUBE_API_KEY =", os.environ.get('YOUTUBE_API_KEY'))
  # print("KAKAO_ACCESS_TOKEN =", os.environ.get('KAKAO_ACCESS_TOKEN'))

  # 이후 파이썬 내에서 os.environ에 접근하면
  # MY_API_KEY, MY_DEBUG 등을 사용할 수 있음
  main()
  # convert_naver_map.main()
  #every_mention.main(kakao_opentalk_name_List[1])
  # youtube.GetMusicList()





