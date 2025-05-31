import sys, os
from datetime import datetime
import atexit
import shutil

IS_DEBUG_MODE = 'pydevd' in sys.modules
log_file = None

def ensure_saved_directory():
    """saved 디렉토리가 없으면 생성"""
    if not os.path.exists("saved"):
        os.makedirs("saved")

def rotate_log_file():
    """기존 로그 파일이 있으면 백업"""
    log_path = os.path.join("saved", "log.txt")
    if os.path.exists(log_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join("saved", f"log_{timestamp}.txt")
        try:
            shutil.move(log_path, backup_path)
        except Exception as e:
            print(f"로그 파일 백업 중 오류 발생: {e}")

def init_log_file():
    global log_file
    try:
        ensure_saved_directory()
        rotate_log_file()
        log_file = open(os.path.join("saved", "log.log"), "a", encoding="utf-8")
        atexit.register(close_log_file)  # 프로그램 종료 시 파일 닫기
    except Exception as e:
        print(f"로그 파일 초기화 중 오류 발생: {e}")

def close_log_file():
    global log_file
    if log_file:
        try:
            log_file.close()
        except Exception as e:
            print(f"로그 파일 닫기 중 오류 발생: {e}")

def CustomPrint(messages, saveLog = 0):
    global log_file
    full_message = "".join(str(m) for m in messages)
    ts = datetime.now().strftime("%m-%d-%H:%M:%S")
    log_message = f"{ts} // {full_message}"
    print(log_message)
    
    # 로그 파일에 기록
    if log_file is None:
        init_log_file()
    
    try:
        if log_file:
            log_file.write(log_message + "\n")
            log_file.flush()  # 버퍼를 즉시 디스크에 기록
    except Exception as e:
        print(f"로그 파일 기록 중 오류 발생: {e}")

def is_debug_mode() -> bool:
    # PyCharm(또는 다른 IDE) 디버거가 붙어 있을 때만 True
    return (IS_DEBUG_MODE == 1)

def CheckMode():
    if is_debug_mode():
        CustomPrint("🐞 DEBUG 모드입니다.")
    else:
        CustomPrint("🔖 RELEASE 모드입니다.")