import time
from Lib import dataManager, Helper
from Lib import chat_process, json_data_manager
from Lib import log_monitor
import sys
import os
import subprocess
import json


def check_and_update():
    """
    GitHub 업데이트를 확인하고 필요한 경우 업데이트를 수행합니다.
    """
    Helper.CustomPrint("🔍 GitHub 업데이트 확인 중...")
    
    # Git 설정 확인
    if not Helper.check_git_configuration():
        Helper.CustomPrint("⚠️ Git 설정에 문제가 있습니다. 업데이트를 건너뜁니다.")
        return
    
    if Helper.check_github_updates():
        Helper.CustomPrint("🔄 새로운 업데이트가 있습니다. 업데이트를 시작합니다...")
        if Helper.perform_git_update():
            Helper.CustomPrint("✅ 업데이트가 완료되었습니다.")
            Helper.CustomPrint("✅ 프로그램을 재실행해주세요.")
            sys.exit(0)
            
            Helper.CustomPrint("🔄 프로그램을 재시작합니다... (3초 후)")
            time.sleep(3)  # 사용자가 메시지를 읽을 수 있도록 잠시 대기
            
            # Windows에서 프로그램 재시작
            python = sys.executable
            
            script = os.path.abspath(sys.argv[0])
            # 현재 작업 디렉토리 저장
            cwd = os.getcwd()
            
            # 새 프로세스 시작
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.Popen([python, script], 
                           cwd=cwd,
                           startupinfo=startupinfo,
                           creationflags=subprocess.CREATE_NEW_CONSOLE)
            
            # 현재 프로세스 종료
            sys.exit(0)
        else:
            Helper.CustomPrint("❌ 업데이트에 실패했습니다. 기존 버전으로 실행합니다.")
    else:
        Helper.CustomPrint("✅ 최신 버전입니다.")

def main():
    # API 키 로드
    json_data_manager.load_api_keys()
    
    # GitHub 업데이트 확인
    check_and_update()
    
    # 카카오톡 자동 실행 안내
    Helper.CustomPrint("🚀 KakaoBot 2025 시작")
    Helper.CustomPrint("📱 카카오톡이 실행되지 않은 경우 자동으로 실행됩니다")
    
    # ChatProcess 인스턴스들을 저장할 리스트 (전역 변수로 설정)
    global chatList
    chatList = []

    # 각 오픈톡방 이름에 대해 ChatProcess 인스턴스를 생성하여 리스트에 추가
    for name in dataManager.kakao_opentalk_name_List:
        chatList.append(chat_process.ChatProcess(name))
    
    # Feather 로그 모니터링을 위한 chatList 설정
    log_monitor.set_global_chat_list(chatList)
    
    # DefaultSetting.ini의 enabled 값이 true면 자동으로 모니터링 시작
    feather_monitor = log_monitor.start_feather_monitoring_from_config()

    # 무한 루프: 주기적으로 각 ChatProcess의 run() 메서드를 호출
    while True:
        
        for chat in chatList:
            chat.run()
        time.sleep(0.1)  # 0.5초에서 0.1초로 감소

if __name__ == '__main__':
    main()







