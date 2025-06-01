import os
import re
from pathlib import Path

# 로그 디렉토리를 saved로 변경
LOG_DIR = Path(__file__).parent / 'saved'
OUTPUT_FILE = LOG_DIR / 'logMerge.log'

# 에러 로그 패턴 정의
ERROR_PATTERNS = [
    re.compile(r'❌'),
    re.compile(r'Error:'),
    re.compile(r'예외 발생'),
    re.compile(r'Traceback'),
    re.compile(r'프로그램을 다시 시작합니다'),
]

# 무시할 정상 로그 패턴
IGNORE_PATTERNS = [
    re.compile(r'\[INFO\]'),
    re.compile(r'사진'),
    re.compile(r'os\.environ'),
]

def is_error_line(line):
    if any(p.search(line) for p in ERROR_PATTERNS):
        if not any(p.search(line) for p in IGNORE_PATTERNS):
            return True
    return False

def extract_error_logs(log_dir, output_file):
    def get_log_body(line):
        # 날짜/시간 및 재시작 횟수 등 가변 부분 제거
        body = re.sub(r'^\d{2}-\d{2}-\d{2}:\d{2}:\d{2} // ', '', line)
        # 재시작 횟수 등 숫자만 바뀌는 부분도 제거
        body = re.sub(r'\(재시작 횟수: \d+회\)', '(재시작 횟수: N회)', body)
        return body.strip()

    # saved 디렉토리가 없으면 생성
    log_dir.mkdir(parents=True, exist_ok=True)
    
    unique_bodies = set()
    with open(output_file, 'w', encoding='utf-8') as fout:
        for fname in sorted(os.listdir(log_dir)):
            # 모든 .txt와 .log 파일 처리 (logMerge.log 제외)
            if fname.endswith(('.txt', '.log')) and fname != 'logMerge.log':
                fpath = log_dir / fname
                print(f"Processing file: {fname}")  # 디버깅용 출력
                try:
                    with open(fpath, 'r', encoding='utf-8') as fin:
                        for line in fin:
                            if is_error_line(line):
                                body = get_log_body(line)
                                if body not in unique_bodies:
                                    # 날짜/시간 제거 후 저장
                                    fout.write(body + '\n')
                                    unique_bodies.add(body)
                except Exception as e:
                    print(f"Error processing {fname}: {e}")

if __name__ == '__main__':
    extract_error_logs(LOG_DIR, OUTPUT_FILE)
    print(f'에러 로그가 {OUTPUT_FILE}에 저장되었습니다.')
