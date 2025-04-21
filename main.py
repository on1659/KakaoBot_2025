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
  # # 이제 os.environ['MY_API_KEY'] 값을 확인해보면
  # Helper.CustomPrint("YOUTUBE_API_KEY =", os.environ.get('YOUTUBE_API_KEY'))
  # Helper.CustomPrint("KAKAO_ACCESS_TOKEN =", os.environ.get('KAKAO_ACCESS_TOKEN'))

  # 이후 파이썬 내에서 os.environ에 접근하면
  # MY_API
  # _KEY, MY_DEBUG 등을 사용할 수 있

  # 사용 예

  Helper.CheckMode()

  resultList = json_data_manager.load_api_keys()
  if len(resultList) > 0:
      try:
          main()
      except Exception as e:
          # (원하시면 예외 처리 로깅)
          Helper.CustomPrint(e)
      finally:
          input("아무 키나 누르면 종료됩니다…")
  else:
     Helper.CustomPrint(f"❌ Error: JSON 로드 실패")
      # convert_naver_map.main()
  #every_mention.main(kakao_opentalk_name_List[1])
  # youtube.GetMusicList()







