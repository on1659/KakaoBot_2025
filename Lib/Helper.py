import sys, os
from datetime import datetime
import atexit
import shutil
import subprocess
import requests
import json
import configparser

IS_DEBUG_MODE = 'pydevd' in sys.modules
log_file = None

def read_github_settings():
    """
    DefaultSetting.ini에서 GitHub 관련 설정을 읽어옵니다.
    """
    try:
        config = configparser.ConfigParser(allow_no_value=True)
        config_path = 'config/DefaultSetting.ini'
        CustomPrint(f"🔍 설정 파일 경로: {os.path.abspath(config_path)}")
        
        if not os.path.exists(config_path):
            CustomPrint(f"❌ 설정 파일이 존재하지 않습니다: {config_path}")
            return {
                'auto_update': False,
                'branch': 'main'
            }
            
        config.read(config_path, encoding='utf-8')
        
        # 설정 파일의 모든 섹션과 값 출력
        CustomPrint("📋 설정 파일 내용:")
        for section in config.sections():
            CustomPrint(f"  [{section}]")
            for key, value in config[section].items():
                CustomPrint(f"    {key} = {value}")
        
        auto_update = config.getboolean('GitHub', 'autoUpdate', fallback=False)
        branch = config.get('GitHub', 'branch', fallback='main')
        
        CustomPrint(f"✅ GitHub 설정 읽기 성공 - autoUpdate: {auto_update}, branch: {branch}")
        
        return {
            'auto_update': auto_update,
            'branch': branch
        }
    except Exception as e:
        CustomPrint(f"❌ GitHub 설정 읽기 실패: {str(e)}")
        return {
            'auto_update': False,
            'branch': 'main'
        }

def check_github_updates():
    """
    GitHub에서 최신 버전을 확인하고 업데이트가 필요한지 반환합니다.
    """
    try:
        settings = read_github_settings()
        if not settings['auto_update']:
            CustomPrint("ℹ️ GitHub 자동 업데이트가 비활성화되어 있습니다.")
            return False
            
        # 현재 브랜치 이름 가져오기
        current_branch = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).decode('utf-8').strip()
        
        # 현재 브랜치의 최신 커밋 해시 가져오기
        current_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode('utf-8').strip()
        
        # 원격 저장소의 최신 커밋 해시 가져오기 (일반 메시지 색상 비활성화)
        subprocess.run(['git', '-c', 'color.branch=never', '-c', 'color.status=never', 'fetch', 'origin'], check=True)
        remote_hash = subprocess.check_output(['git', 'rev-parse', f"origin/{current_branch}"]).decode('utf-8').strip()
        
        if current_hash != remote_hash:
            return True
        return False
    except Exception as e:
        CustomPrint(f"❌ GitHub 업데이트 확인 중 오류 발생: {str(e)}")
        return False

def perform_git_update():
    """
    GitHub에서 최신 버전으로 업데이트를 수행합니다.
    """
    try:
        settings = read_github_settings()
        if not settings['auto_update']:
            return False
            
        # 현재 브랜치 이름 가져오기
        current_branch = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).decode('utf-8').strip()
            
        # 현재 변경사항 저장
        subprocess.run(['git', '-c', 'color.branch=never', '-c', 'color.status=never', 'stash'], check=True)
        
        # 원격 저장소에서 최신 변경사항 가져오기
        subprocess.run(['git', '-c', 'color.branch=never', '-c', 'color.status=never', 'pull', 'origin', current_branch], check=True)
        
        # 저장된 변경사항 복원
        subprocess.run(['git', '-c', 'color.branch=never', '-c', 'color.status=never', 'stash', 'pop'], check=True)
        
        CustomPrint("✅ GitHub 업데이트가 완료되었습니다.")
        return True
    except Exception as e:
        CustomPrint(f"❌ GitHub 업데이트 중 오류 발생: {str(e)}")
        return False

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

def CustomPrint(messages, saveLog = True):
    global log_file
    full_message = "".join(str(m) for m in messages)
    ts = datetime.now().strftime("%m-%d-%H:%M:%S")
    log_message = f"{ts} // {full_message}"
    print(log_message)
    
    # saveLog가 True일 때만 로그 파일에 기록
    if saveLog:
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