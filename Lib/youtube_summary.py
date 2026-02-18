import re
import os
from google import genai
from youtube_transcript_api import YouTubeTranscriptApi


def extract_video_id(url):
    """YouTube URL에서 video ID를 추출합니다."""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_transcript(video_id):
    """YouTube 영상의 자막을 가져옵니다. 실패시 None 반환."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # 한국어 자막 우선, 없으면 영어
        for lang in ['ko', 'en']:
            try:
                transcript = transcript_list.find_transcript([lang])
                snippets = transcript.fetch()
                return " ".join(snippet.text for snippet in snippets)
            except Exception:
                continue

        # 아무 자막이나 가져와서 한국어로 번역 시도
        for transcript in transcript_list:
            try:
                translated = transcript.translate('ko')
                snippets = translated.fetch()
                return " ".join(snippet.text for snippet in snippets)
            except Exception:
                continue

        # 번역 실패시 원본 자막
        for transcript in transcript_list:
            snippets = transcript.fetch()
            return " ".join(snippet.text for snippet in snippets)

    except Exception:
        return None


def summarize_transcript(client, transcript_text):
    """자막 텍스트를 Gemini로 요약합니다. (저렴)"""
    max_chars = 12000
    if len(transcript_text) > max_chars:
        transcript_text = transcript_text[:max_chars] + "...(이하 생략)"

    prompt = (
        "다음 유튜브 영상 자막을 한국어로 요약해주세요.\n"
        "핵심 내용을 3~5개 포인트로 정리하고, 답변은 500자 이내로 해주세요.\n\n"
        f"{transcript_text}"
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    if response.text:
        return response.text.strip()
    return None


def summarize_video(client, video_url):
    """Gemini로 영상을 직접 분석/요약합니다. (비쌈 - 자막 없을 때만 사용)"""
    prompt = (
        "이 유튜브 영상의 내용을 한국어로 요약해주세요.\n"
        "핵심 내용을 3~5개 포인트로 정리하고, 답변은 500자 이내로 해주세요."
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=genai.types.Content(
            parts=[
                genai.types.Part(text=prompt),
                genai.types.Part(
                    file_data=genai.types.FileData(file_uri=video_url)
                ),
            ]
        ),
    )
    if response.text:
        return response.text.strip()
    return None


def GetData(opentalk_name, chat_command, message):
    """YouTube URL이 감지되면 영상을 요약합니다."""
    url = chat_command + message
    video_id = extract_video_id(url)

    if not video_id:
        return "유효한 YouTube URL이 아닙니다.", "text"

    video_url = f"https://www.youtube.com/watch?v={video_id}"
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    try:
        # 1차: 자막으로 요약 시도 (저렴)
        transcript = get_transcript(video_id)
        if transcript:
            summary = summarize_transcript(client, transcript)
            if summary:
                result = f"[YouTube 영상 요약]\n\n{summary}"
                return result, "text"

        # 2차: 자막 없으면 Gemini 영상 직접 분석 (비쌈)
        summary = summarize_video(client, video_url)
        if summary:
            result = f"[YouTube 영상 요약]\n\n{summary}"
            return result, "text"

        return "요약 생성에 실패했습니다.", "text"

    except Exception as e:
        return f"YouTube 요약 중 오류: {str(e)}", "text"
