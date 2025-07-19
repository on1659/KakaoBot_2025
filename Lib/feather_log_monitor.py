import os
import time
import re
import threading
from pathlib import Path
from datetime import datetime
from Lib import Helper

class FeatherLogMonitor:
    def __init__(self, server_paths, notification_room_name):
        """
        Feather Launcher 마크서버 로그 모니터링 클래스
        
        Args:
            server_paths (list): 서버 로그 경로 리스트
            notification_room_name (str): 알림을 보낼 카카오톡 방 이름
        """
        self.server_paths = server_paths
        self.notification_room_name = notification_room_name
        self.monitoring = False
        self.monitor_thread = None
        self.last_positions = {}
        self.start_time = None  # 모니터링 시작 시간
        
        # 접속 감지 패턴들
        self.join_patterns = [
            r'\[.*?\] \[Server thread/INFO\]: (\w+) joined the game',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) logged in',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) connected',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) 접속',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) 로그인'
        ]
        
        # 퇴장 감지 패턴들
        self.leave_patterns = [
            r'\[.*?\] \[Server thread/INFO\]: (\w+) left the game',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) disconnected',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) 퇴장',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) logged out',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) has left the server',
            r'\[.*?\] \[Server thread/INFO\]: UUID of player (\w+) is',
            r'\[.*?\] \[Server thread/INFO\]: (\w+) lost connection'
        ]
        
        Helper.CustomPrint(f"🔍 Feather 로그 모니터링 초기화 완료")
        Helper.CustomPrint(f"📁 모니터링 서버: {len(server_paths)}개")
        Helper.CustomPrint(f"💬 알림 방: {notification_room_name}")
    
    def start_monitoring(self):
        """로그 모니터링 시작"""
        if self.monitoring:
            Helper.CustomPrint("⚠️ 이미 모니터링 중입니다.")
            return
        
        self.monitoring = True
        self.start_time = datetime.now()  # 모니터링 시작 시간 기록
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        Helper.CustomPrint("✅ Feather 로그 모니터링 시작")
    
    def stop_monitoring(self):
        """로그 모니터링 중지"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
        Helper.CustomPrint("⏹️ Feather 로그 모니터링 중지")
    
    def _monitor_loop(self):
        """모니터링 메인 루프"""
        while self.monitoring:
            try:
                for server_path in self.server_paths:
                    self._check_server_log(server_path)
                time.sleep(1)  # 1초마다 체크
            except Exception as e:
                Helper.CustomPrint(f"❌ 로그 모니터링 오류: {str(e)}")
                time.sleep(5)  # 오류 시 5초 대기
    
    def _check_server_log(self, server_path):
        """개별 서버 로그 체크"""
        log_file = Path(server_path) / "logs" / "latest.log"
        
        if not log_file.exists():
            return
        
        try:
            # 파일 크기 확인
            current_size = log_file.stat().st_size
            last_position = self.last_positions.get(str(log_file), 0)
            
            # 파일이 새로 생성되었거나 크기가 줄어든 경우 (로그 로테이션)
            if current_size < last_position:
                last_position = 0
            
            # 새로운 내용이 있는 경우
            if current_size > last_position:
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(last_position)
                    new_lines = f.readlines()
                    
                    for line in new_lines:
                        self._process_log_line(line.strip(), server_path)
                
                self.last_positions[str(log_file)] = current_size
                
        except Exception as e:
            Helper.CustomPrint(f"❌ 로그 파일 읽기 오류 ({server_path}): {str(e)}")
    
    def _process_log_line(self, line, server_path):
        """로그 라인 처리"""
        if not line:
            return
        
        # 로그 라인의 타임스탬프 추출 및 모니터링 시작 시간과 비교
        if not self._is_log_after_start_time(line):
            return  # 모니터링 시작 이전의 로그는 무시
        
        # 접속 감지
        for pattern in self.join_patterns:
            match = re.search(pattern, line)
            if match:
                player_name = match.group(1)
                server_name = Path(server_path).name
                self._send_join_notification(player_name, server_name)
                return
        
        # 퇴장 감지 (선택사항)
        for pattern in self.leave_patterns:
            match = re.search(pattern, line)
            if match:
                player_name = match.group(1)
                server_name = Path(server_path).name
                self._send_leave_notification(player_name, server_name)
                return
    
    def _is_log_after_start_time(self, log_line):
        """로그 라인이 모니터링 시작 시간 이후인지 확인"""
        if not self.start_time:
            return True
        
        # 로그 라인에서 타임스탬프 추출 (예: [12:34:56])
        timestamp_match = re.search(r'\[(\d{2}:\d{2}:\d{2})\]', log_line)
        if not timestamp_match:
            return True  # 타임스탬프가 없으면 처리
        
        try:
            log_time_str = timestamp_match.group(1)
            log_time = datetime.strptime(log_time_str, "%H:%M:%S").time()
            start_time = self.start_time.time()
            
            # 같은 날의 시간 비교
            return log_time >= start_time
        except:
            return True  # 파싱 오류 시 처리
    
    def _send_join_notification(self, player_name, server_name):
        """접속 알림 전송"""
        message = f"[{player_name}]님이 로그인하셨습니다."
        
        Helper.CustomPrint(f"🎮 {player_name}님이 {server_name} 서버에 접속했습니다!")
        
        # 카카오톡 알림 전송 (chat_process를 통해)
        self._send_kakao_message(message)
    
    def _send_leave_notification(self, player_name, server_name):
        """퇴장 알림 전송"""
        message = f"[{player_name}]님이 로그아웃하셨습니다."
        
        Helper.CustomPrint(f"🚪 {player_name}님이 {server_name} 서버에서 퇴장했습니다.")
        
        # 카카오톡 알림 전송
        self._send_kakao_message(message)
    
    def _send_kakao_message(self, message):
        """카카오톡 메시지 전송"""
        try:
            # 전역 chatList 사용
            if global_chat_list:
                # 알림 방을 찾아서 메시지 전송
                for chat in global_chat_list:
                    if chat.chatroom_name == self.notification_room_name:
                        # ChatProcess.send 메서드 사용 (더 안정적)
                        try:
                            chat.send(message, "text")
                            Helper.CustomPrint(f"✅ 카카오톡 알림 전송 완료: {self.notification_room_name}")
                            return
                        except Exception as e:
                            Helper.CustomPrint(f"❌ 메시지 전송 실패: {str(e)}")
                
                Helper.CustomPrint(f"⚠️ 알림 방을 찾을 수 없습니다: {self.notification_room_name}")
            else:
                # chatList가 아직 초기화되지 않았을 때는 나중에 다시 시도
                Helper.CustomPrint(f"⏳ chatList가 아직 초기화되지 않았습니다. 잠시 후 다시 시도합니다.")
                
        except Exception as e:
            Helper.CustomPrint(f"❌ 카카오톡 메시지 전송 오류: {str(e)}")

# 전역 변수들
feather_monitor = None
global_chat_list = None

def set_global_chat_list(chat_list):
    """전역 chatList 설정"""
    global global_chat_list
    global_chat_list = chat_list

def start_feather_monitoring(server_paths, notification_room_name):
    """Feather 로그 모니터링 시작"""
    global feather_monitor
    
    if feather_monitor:
        feather_monitor.stop_monitoring()
    
    feather_monitor = FeatherLogMonitor(server_paths, notification_room_name)
    feather_monitor.start_monitoring()
    return feather_monitor

def start_feather_monitoring_from_config():
    """설정 파일에서 Feather 모니터링 정보를 읽어 모니터링 시작"""
    try:
        from Lib import dataManager
        
        # 설정에서 Feather 모니터링 정보 읽기
        enabled = dataManager.DefaultSettingConfig.getboolean('FeatherMonitor', 'enabled', fallback=False)
        if not enabled:
            Helper.CustomPrint("ℹ️ Feather 모니터링이 비활성화되어 있습니다.")
            return None
        
        notification_room = dataManager.DefaultSettingConfig.get('FeatherMonitor', 'notification_room', fallback='이더')
        server_paths_str = dataManager.DefaultSettingConfig.get('FeatherMonitor', 'server_paths', fallback='')
        
        if not server_paths_str:
            Helper.CustomPrint("⚠️ Feather 서버 경로가 설정되지 않았습니다.")
            return None
        
        server_paths = [path.strip() for path in server_paths_str.split(',')]
        
        Helper.CustomPrint(f"🎮 Feather 모니터링 설정:")
        Helper.CustomPrint(f"   📁 서버 경로: {len(server_paths)}개")
        Helper.CustomPrint(f"   💬 알림 방: {notification_room}")
        
        # 모니터링 시작
        monitor = start_feather_monitoring(server_paths, notification_room)
        return monitor
        
    except Exception as e:
        Helper.CustomPrint(f"❌ Feather 모니터링 시작 실패: {str(e)}")
        return None

def stop_feather_monitoring():
    """Feather 로그 모니터링 중지"""
    global feather_monitor
    
    if feather_monitor:
        feather_monitor.stop_monitoring()
        feather_monitor = None

def start_feather_monitoring_command(chatroom_name, chat_command, message):
    """#마크노티시작 명령어 처리"""
    global feather_monitor
    
    if feather_monitor and feather_monitor.monitoring:
        return "⚠️ 이미 Feather 로그 모니터링이 실행 중입니다.", "text"
    
    # 설정에서 모니터링 시작
    monitor = start_feather_monitoring_from_config()
    if monitor:
        return "✅ Feather 로그 모니터링이 시작되었습니다! 🎮", "text"
    else:
        return "❌ Feather 로그 모니터링 시작에 실패했습니다. 설정을 확인해주세요.", "text"

def stop_feather_monitoring_command(chatroom_name, chat_command, message):
    """#마크노티종료 명령어 처리"""
    global feather_monitor
    
    if not feather_monitor or not feather_monitor.monitoring:
        return "⚠️ 현재 Feather 로그 모니터링이 실행되고 있지 않습니다.", "text"
    
    stop_feather_monitoring()
    return "⏹️ Feather 로그 모니터링이 중지되었습니다.", "text" 