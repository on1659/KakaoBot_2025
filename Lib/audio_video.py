# -*- coding: utf-8 -*-
"""
음성(mp3)을 '커버 이미지 + 소리' 동영상(mp4)으로 바꾼다.

카카오톡에 mp3를 보내면 첨부파일로 가서 받는 사람이 열어야 들을 수 있다. mp4로 보내면
채팅에 재생 버튼이 달린 말풍선으로 떠서 바로 재생된다 (2026-11 실측).

변환은 Windows 10/11에 들어 있는 동영상 편집 기능(Windows.Media.Editing)을 Windows PowerShell로
불러서 한다 — ffmpeg 같은 추가 프로그램이 필요 없다. 실패하면 None을 돌려주고, 호출한 쪽은
원래 mp3를 파일로 보낸다.
"""
import os
import subprocess
from pathlib import Path

from Lib import Helper, runtime_paths

COVER_SIZE = 480
CONVERT_TIMEOUT_SEC = 90
FONT_BOLD = r"C:\Windows\Fonts\malgunbd.ttf"
FONT_REGULAR = r"C:\Windows\Fonts\malgun.ttf"
BACKGROUND = (254, 229, 0)
INK = (40, 40, 40)
MAX_TEXT_LINES = 3

# PowerShell 5.1은 WinRT 컬렉션 메서드를 직접 못 불러서 인터페이스 리플렉션으로 Add를 호출한다.
_SCRIPT = r"""param(
    [Parameter(Mandatory = $true)][string]$Audio,
    [Parameter(Mandatory = $true)][string]$Image,
    [Parameter(Mandatory = $true)][string]$Out,
    [int]$Size = 480
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$extensions = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 }
$asTaskOperation = ($extensions | Where-Object { $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
$asTaskProgress = ($extensions | Where-Object { $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperationWithProgress`2' })[0]

function Await($Operation, [Type]$ResultType) {
    $task = $asTaskOperation.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait() | Out-Null
    $task.Result
}

[void][Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
[void][Windows.Storage.StorageFolder, Windows.Storage, ContentType = WindowsRuntime]
[void][Windows.Media.Editing.MediaComposition, Windows.Media.Editing, ContentType = WindowsRuntime]
[void][Windows.Media.Editing.MediaClip, Windows.Media.Editing, ContentType = WindowsRuntime]
[void][Windows.Media.Editing.BackgroundAudioTrack, Windows.Media.Editing, ContentType = WindowsRuntime]
[void][Windows.Media.MediaProperties.MediaEncodingProfile, Windows.Media.MediaProperties, ContentType = WindowsRuntime]
[void][Windows.Media.Transcoding.TranscodeFailureReason, Windows.Media.Transcoding, ContentType = WindowsRuntime]

$audioFile = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Audio)) ([Windows.Storage.StorageFile])
$imageFile = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Image)) ([Windows.Storage.StorageFile])
$track = Await ([Windows.Media.Editing.BackgroundAudioTrack]::CreateFromFileAsync($audioFile)) ([Windows.Media.Editing.BackgroundAudioTrack])
$clip = Await ([Windows.Media.Editing.MediaClip]::CreateFromImageFileAsync($imageFile, $track.OriginalDuration)) ([Windows.Media.Editing.MediaClip])

$composition = [Windows.Media.Editing.MediaComposition]::new()
[System.Collections.Generic.ICollection[Windows.Media.Editing.MediaClip]].GetMethod('Add').Invoke($composition.Clips, @($clip)) | Out-Null
[System.Collections.Generic.ICollection[Windows.Media.Editing.BackgroundAudioTrack]].GetMethod('Add').Invoke($composition.BackgroundAudioTracks, @($track)) | Out-Null

$folder = Await ([Windows.Storage.StorageFolder]::GetFolderFromPathAsync((Split-Path -Parent $Out))) ([Windows.Storage.StorageFolder])
$outFile = Await ($folder.CreateFileAsync((Split-Path -Leaf $Out), [Windows.Storage.CreationCollisionOption]::ReplaceExisting)) ([Windows.Storage.StorageFile])

$profile = [Windows.Media.MediaProperties.MediaEncodingProfile]::CreateMp4([Windows.Media.MediaProperties.VideoEncodingQuality]::Vga)
$profile.Video.Width = $Size
$profile.Video.Height = $Size
$profile.Video.Bitrate = 300000

$render = $composition.RenderToFileAsync($outFile, [Windows.Media.Editing.MediaTrimmingPreference]::Precise, $profile)
$renderTask = $asTaskProgress.MakeGenericMethod([Windows.Media.Transcoding.TranscodeFailureReason], [double]).Invoke($null, @($render))
$renderTask.Wait() | Out-Null
if ($renderTask.Result -ne [Windows.Media.Transcoding.TranscodeFailureReason]::None) {
    Write-Error "render failed: $($renderTask.Result)"
    exit 2
}
Write-Output 'OK'
"""


def _font(path, size):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _wrap(text, font, max_width, max_lines):
    """글자 단위로 줄을 나눈다 (한글은 띄어쓰기 없이 길게 이어질 수 있다). 넘치면 …로 줄인다."""
    lines, current = [], ""
    for char in " ".join((text or "").split()):
        if font.getlength(current + char) <= max_width:
            current += char
            continue
        lines.append(current.rstrip())
        current = char.lstrip()
        if len(lines) == max_lines:
            break
    else:
        if current:
            lines.append(current)
        return lines
    last = lines[-1]
    while last and font.getlength(last + "…") > max_width:
        last = last[:-1]
    lines[-1] = last + "…"
    return lines


def make_cover(label, text, out_path):
    """
    동영상에 깔 정사각형 커버 이미지를 만든다: 위쪽에 제목(label), 아래쪽에 내용(text).
    가운데는 비워 둔다 — 카카오톡이 그 자리에 재생 버튼과 길이를 덮어 그린다.
    """
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (COVER_SIZE, COVER_SIZE), BACKGROUND)
    draw = ImageDraw.Draw(image)
    center = COVER_SIZE // 2
    draw.text((center, 92), label, font=_font(FONT_BOLD, 72), fill=INK, anchor="mm")

    body_font = _font(FONT_REGULAR, 28)
    for index, line in enumerate(_wrap(text, body_font, COVER_SIZE - 64, MAX_TEXT_LINES)):
        draw.text((center, 348 + index * 38), line, font=body_font, fill=INK, anchor="mm")
    image.save(out_path, "PNG")
    return out_path


def _powershell_path():
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def _script_path():
    path = runtime_paths.SAVED_DIR / "audio_to_video.ps1"
    try:
        if path.read_text(encoding="utf-8-sig") == _SCRIPT:
            return path
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_SCRIPT, encoding="utf-8-sig")  # BOM이 있어야 PowerShell 5.1이 한글을 제대로 읽는다
    return path


def audio_to_video(audio_path, label, text):
    """
    audio_path 옆에 같은 이름의 .mp4를 만들고 그 경로(str)를 돌려준다. 실패하면 None.
    label/text는 커버 이미지에 들어갈 제목과 내용이다.
    """
    powershell = _powershell_path()
    if os.name != "nt" or not os.path.isfile(powershell):
        return None

    audio = Path(audio_path).resolve()
    video = audio.with_suffix(".mp4")
    cover = audio.with_suffix(".cover.png")
    try:
        make_cover(label, text, cover)
        result = subprocess.run(
            [
                powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(_script_path()),
                "-Audio", str(audio), "-Image", str(cover), "-Out", str(video),
                "-Size", str(COVER_SIZE),
            ],
            stdin=subprocess.DEVNULL,   # UI→워커 제어 파이프를 물려받으면 하위 프로세스가 멈춘다
            capture_output=True,
            timeout=CONVERT_TIMEOUT_SEC,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0 or not video.is_file() or video.stat().st_size == 0:
            detail = (result.stderr or result.stdout or b"").decode("mbcs", errors="replace").strip()
            Helper.CustomPrint(f"⚠️ [audio_video] 동영상 변환 실패 (code={result.returncode}): {detail[:300]}")
            return None
        return str(video)
    except Exception as e:
        Helper.CustomPrint(f"⚠️ [audio_video] 동영상 변환 실패 ({type(e).__name__}): {e}")
        return None
    finally:
        try:
            cover.unlink()
        except OSError:
            pass
