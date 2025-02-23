import time
import pandas as pd # 가져온 채팅내용 DF로 쓸거라서
import KaKao_Util.kakao_openroom as OpenRoom
import KaKao_Util.kakao_coppaste as CopyPaste
import KaKao_Util.kakak_send as Send


from Lib import youtube, convert_naver_map, every_mention

# # 카톡창 이름, (활성화 상태의 열려있는 창)
kakao_opentalk_name_List = [
    '하트시그널 토론회장'
    , '테스트방이야'
    , '이더']
chat_command_Map = [
    ['#유툽', youtube.GetData],
    ['[카카오맵]', convert_naver_map.GetData],
    ['#all', every_mention.GetData]
]

# # 채팅내용 초기 저장 _ 마지막 채팅
def chat_last_save(opentalk_name):
    OpenRoom.chat_room(opentalk_name, 1)  # 채팅방 열기
    ttext = CopyPaste.copy_cheat(opentalk_name, 1)  # 채팅내용 가져오기

    a = ttext.split('\r\n')   # \r\n 으로 스플릿 __ 대화내용 인용의 경우 \r 때문에 해당안됨
    df = pd.DataFrame(a)    # DF 으로 바꾸기

    df[0] = df[0].str.replace(r'\[([\S\s]+)\] \[(오전|오후)([0-9:\s]+)\] ', '', regex=True)  # 정규식으로 채팅내용만 남기기
    if len(df) < 2:
        print("chat_last_save error")
        return "", ""
    return df.index[-2], df.iloc[-2, 0]

# # 채팅방 커멘드 체크
def chat_chek_command(opentalk_name, cls, clst):
    OpenRoom.chat_room(opentalk_name)  # 채팅방 열기
    copy_text = CopyPaste.copy_cheat(opentalk_name)  # 채팅내용 가져오기

    copy_text = copy_text.split('\r\n')  # \r\n 으로 스플릿 __ 대화내용 인용의 경우 \r 때문에 해당안됨
    df = pd.DataFrame(copy_text)  # DF 으로 바꾸기

    df[0] = df[0].str.replace(r'\[([\S\s]+)\] \[(오전|오후)([0-9:\s]+)\] ', '', regex=True)    # 정규식으로 채팅내용만 남기기

    if len(df) < 2:
        print("채팅 못 읽음")

        return "", ""
    if df.iloc  [-2, 0] == clst:
        print("채팅 없었음.. ")
        return df.index[-2], df.iloc[-2, 0]
    else:
        print("채팅 있었음")

        df1 = df.iloc[cls +1 : , 0]   # 최근 채팅내용만 남김

        for chat_command, chat_func in chat_command_Map:
            found = df1[ df1.str.contains(chat_command) ]    # 챗 카운트

            if 1 <= int(found.count()):
                print("-------커멘드 확인!")
                resultString = chat_func(opentalk_name, chat_command, found.iloc[0])
                Send.sendtext(opentalk_name, resultString)  # 메시지 전송

                # 명령어 여러개 쓸경우 리턴값으로 각각 빼서 쓰면 될듯. 일단 테스트용으로 위에 하드코딩 해둠
                return df.index[-2], df.iloc[-2, 0]

        print("커멘드 미확인")
        return df.index[-2], df.iloc[-2, 0]

def main():

    # sched = BackgroundScheduler()
    # sched.start()

    num_chatrooms = len(kakao_opentalk_name_List)
    cls = ["" for _ in range(num_chatrooms)]
    clst = ["" for _ in range(num_chatrooms)]

    for i, name in enumerate(kakao_opentalk_name_List):
        cls[i], clst[i] = chat_last_save(name)  # 초기설정 _ 마지막채팅 저장

    # # 매 분 5초마다 job_1 실행
    # sched.add_job(job_1, 'cron', second='*/5', id="test_1")

    while True:
        print("실행중.................")

        for i, name in enumerate(kakao_opentalk_name_List):
            cls[i], clst[i] = chat_chek_command(name, cls[i], clst[i])  # 초기설정 _ 마지막채팅 저장
        time.sleep(1)

if __name__ == '__main__':
  main()
   #convert_naver_map.main()
  #every_mention.main(kakao_opentalk_name_List[1])





