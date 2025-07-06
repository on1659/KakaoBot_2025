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
        
        # Git 설정 개선
        git_env = os.environ.copy()
        git_env['GIT_TERMINAL_PROGRESS'] = '0'  # 진행률 표시 비활성화
        git_env['GIT_PAGER'] = 'cat'  # 페이저 비활성화
            
        # 현재 브랜치 이름 가져오기
        current_branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'], 
            env=git_env
        ).decode('utf-8').strip()
        
        # 현재 브랜치의 최신 커밋 해시 가져오기
        current_hash = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], 
            env=git_env
        ).decode('utf-8').strip()
        
        # 원격 저장소의 최신 커밋 해시 가져오기
        CustomPrint(f"🔄 원격 저장소에서 최신 정보를 가져오는 중... (브랜치: {current_branch})")
        subprocess.run(
            ['git', 'fetch', 'origin', current_branch], 
            check=True, 
            env=git_env,
            capture_output=True
        )
        
        remote_hash = subprocess.check_output(
            ['git', 'rev-parse', f"origin/{current_branch}"], 
            env=git_env
        ).decode('utf-8').strip()
        
        CustomPrint(f"📊 현재 커밋: {current_hash[:8]}...")
        CustomPrint(f"📊 원격 커밋: {remote_hash[:8]}...")
        
        if current_hash != remote_hash:
            CustomPrint("🔄 새로운 업데이트가 있습니다!")
            return True
        else:
            CustomPrint("✅ 이미 최신 버전입니다.")
            return False
            
    except subprocess.CalledProcessError as e:
        CustomPrint(f"❌ Git 명령어 실행 실패: {e}")
        if e.stderr:
            CustomPrint(f"❌ 오류 상세: {e.stderr.decode('utf-8', errors='ignore')}")
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
        
        # Git 설정 개선
        git_env = os.environ.copy()
        git_env['GIT_TERMINAL_PROGRESS'] = '0'  # 진행률 표시 비활성화
        git_env['GIT_PAGER'] = 'cat'  # 페이저 비활성화
        
        # 안전한 stash 처리
        stash_success, stash_created = safe_git_stash()
        if not stash_success:
            CustomPrint("❌ Stash 처리에 실패했습니다. 업데이트를 중단합니다.")
            return False
        
        # 원격 저장소에서 최신 변경사항 가져오기
        CustomPrint("🔄 원격 저장소에서 업데이트를 가져오는 중...")
        subprocess.run(
            ['git', 'fetch', 'origin', current_branch], 
            check=True, 
            env=git_env,
            capture_output=True
        )
        
        # Pull 실행
        pull_result = subprocess.run(
            ['git', 'pull', 'origin', current_branch], 
            capture_output=True, 
            text=True, 
            env=git_env,
            check=True
        )
        
        CustomPrint("✅ 원격 저장소에서 업데이트를 성공적으로 가져왔습니다.")
        
        # Stash가 생성되었다면 복원 시도
        if stash_created:
            try:
                CustomPrint("🔄 저장된 변경사항을 복원하는 중...")
                subprocess.run(
                    ['git', 'stash', 'pop'], 
                    check=True, 
                    env=git_env,
                    capture_output=True
                )
                CustomPrint("✅ 저장된 변경사항이 성공적으로 복원되었습니다.")
            except subprocess.CalledProcessError as e:
                CustomPrint(f"⚠️ Stash 복원 실패: {e}")
                CustomPrint("💡 수동으로 'git stash pop'을 실행하여 변경사항을 복원하세요.")
        
        CustomPrint("✅ GitHub 업데이트가 완료되었습니다.")
        return True
        
    except subprocess.CalledProcessError as e:
        CustomPrint(f"❌ Git 명령어 실행 실패: {e}")
        if e.stderr:
            CustomPrint(f"❌ 오류 상세: {e.stderr}")
        return False
    except Exception as e:
        CustomPrint(f"❌ GitHub 업데이트 중 예상치 못한 오류 발생: {str(e)}")
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

def check_git_configuration():
    """
    Git 설정을 확인하고 필요한 경우 개선합니다.
    """
    try:
        CustomPrint("🔍 Git 설정을 확인하는 중...")
        
        # Git이 설치되어 있는지 확인
        try:
            subprocess.run(['git', '--version'], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            CustomPrint("❌ Git이 설치되어 있지 않습니다.")
            return False
        
        # Git 저장소인지 확인
        try:
            subprocess.run(['git', 'rev-parse', '--git-dir'], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            CustomPrint("❌ 현재 디렉토리가 Git 저장소가 아닙니다.")
            return False
        
        # 원격 저장소 설정 확인
        try:
            remote_result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'], 
                capture_output=True, 
                text=True, 
                check=True
            )
            remote_url = remote_result.stdout.strip()
            CustomPrint(f"✅ 원격 저장소: {remote_url}")
        except subprocess.CalledProcessError:
            CustomPrint("❌ 원격 저장소(origin)가 설정되어 있지 않습니다.")
            return False
        
        # Git 설정 개선
        git_configs = [
            ('core.autocrlf', 'false'),
            ('core.safecrlf', 'false'),
            ('core.quotepath', 'false'),
            ('color.ui', 'never'),
            ('color.branch', 'never'),
            ('color.status', 'never'),
            ('color.diff', 'never'),
            ('pager.branch', 'false'),
            ('pager.log', 'false'),
            ('pager.status', 'false')
        ]
        
        for key, value in git_configs:
            try:
                subprocess.run(
                    ['git', 'config', '--global', key, value], 
                    check=True, 
                    capture_output=True
                )
            except subprocess.CalledProcessError:
                CustomPrint(f"⚠️ Git 설정 실패: {key} = {value}")
        
        CustomPrint("✅ Git 설정 확인 및 개선 완료")
        return True
        
    except Exception as e:
        CustomPrint(f"❌ Git 설정 확인 중 오류 발생: {str(e)}")
        return False

def safe_git_stash():
    """
    안전한 Git stash를 수행합니다.
    """
    try:
        # Git 환경 설정
        git_env = os.environ.copy()
        git_env['GIT_TERMINAL_PROGRESS'] = '0'
        git_env['GIT_PAGER'] = 'cat'
        
        # 현재 상태 확인
        status_result = subprocess.run(
            ['git', 'status', '--porcelain'], 
            capture_output=True, 
            text=True, 
            env=git_env,
            check=True
        )
        
        if not status_result.stdout.strip():
            CustomPrint("✅ 변경사항이 없습니다.")
            return True, False  # (성공, stash 생성 안됨)
        
        # 변경사항이 있는 경우 stash 시도
        CustomPrint("📝 변경사항이 발견되었습니다. Stash를 시도합니다...")
        
        # 먼저 간단한 stash 시도
        try:
            stash_result = subprocess.run(
                ['git', 'stash', 'push', '-m', 'Auto-update stash'],
                capture_output=True,
                text=True,
                env=git_env,
                check=True
            )
            CustomPrint("✅ 변경사항이 성공적으로 저장되었습니다.")
            return True, True  # (성공, stash 생성됨)
            
        except subprocess.CalledProcessError as e:
            CustomPrint(f"⚠️ 일반 stash 실패: {e}")
            
            # 대안: 변경사항을 무시하고 진행
            try:
                # 변경사항을 강제로 제거 (주의: 데이터 손실 가능)
                subprocess.run(
                    ['git', 'reset', '--hard', 'HEAD'],
                    capture_output=True,
                    env=git_env,
                    check=True
                )
                CustomPrint("⚠️ 변경사항을 제거하고 진행합니다.")
                return True, False  # (성공, stash 생성 안됨)
                
            except subprocess.CalledProcessError as reset_error:
                CustomPrint(f"❌ 변경사항 제거도 실패: {reset_error}")
                return False, False  # (실패)
                
    except Exception as e:
        CustomPrint(f"❌ Stash 처리 중 예상치 못한 오류: {str(e)}")
        return False, False  # (실패)