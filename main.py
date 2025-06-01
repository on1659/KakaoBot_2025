import time
from Lib import dataManager, Helper
from Lib import chat_process, json_data_manager
import sys
import os

def check_and_update():
    """
    GitHub 업데이트를 확인하고 필요한 경우 업데이트를 수행합니다.
    """
    Helper.CustomPrint("🔍 GitHub 업데이트 확인 중...")
    if Helper.check_github_updates():
        Helper.CustomPrint("🔄 새로운 업데이트가 있습니다. 업데이트를 시작합니다...")
        if Helper.perform_git_update():
            Helper.CustomPrint("✅ 업데이트가 완료되었습니다. 프로그램을 재시작합니다...")
            python = sys.executable
            os.execl(python, python, *sys.argv)
        else:
            Helper.CustomPrint("❌ 업데이트에 실패했습니다. 기존 버전으로 실행합니다.")
    else:
        Helper.CustomPrint("✅ 최신 버전입니다.")

def main():
    # GitHub 업데이트 확인
    check_and_update()
    
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
    main()







