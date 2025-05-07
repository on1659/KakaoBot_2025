import time
from Lib import dataManager, Helper
from Lib import chat_process, json_data_manager

def main():
    # ChatProcess 인스턴스들을 저장할 리스트
    chatList = []

    # 각 오픈톡방 이름에 대해 ChatProcess 인스턴스를 생성하여 리스트에 추가
    for name in dataManager.kakao_opentalk_name_List:
        chatList.append(chat_process.ChatProcess(name))

    # 무한 루프: 주기적으로 각 ChatProcess의 run() 메서드를 호출
    while True:
        for chat in chatList:
            chat.run()
        time.sleep(0.5)

if __name__ == '__main__':
    Helper.CheckMode()

    resultList = json_data_manager.load_api_keys()
    if len(resultList) > 0:
        restart_count = 0  # 재시작 횟수를 추적하는 변수
        while True:  # 무한 루프로 감싸서 계속 실행
            try:
                main()
            except Exception as e:
                restart_count += 1  # 재시작 횟수 증가
                Helper.CustomPrint(f"❌ Error: {e}")
                Helper.CustomPrint(f"프로그램을 다시 시작합니다... (재시작 횟수: {restart_count}회)")
                time.sleep(3)  # 3초 대기 후 재시작
    else:
        Helper.CustomPrint(f"❌ Error: JSON 로드 실패")
      # convert_naver_map.main()
  #every_mention.main(kakao_opentalk_name_List[1])
  # youtube.GetMusicList()







