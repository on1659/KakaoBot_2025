"""Legacy console entry point backed by :class:`Lib.bot_engine.BotEngine`."""

from __future__ import annotations

import sys

from Lib.bot_engine import BotEngine
from Lib.runtime_paths import ensure_runtime_layout


def check_and_update() -> None:
    """Keep the existing source-checkout Git update flow.

    Packaged builds are updated as releases, not by modifying files with Git.
    """

    from Lib import Helper

    if getattr(sys, "frozen", False):
        Helper.CustomPrint("ℹ️ 실행파일에서는 Git 자동 업데이트를 건너뜁니다.")
        return

    Helper.CustomPrint("🔍 GitHub 업데이트 확인 중...")
    if not Helper.check_git_configuration():
        Helper.CustomPrint("⚠️ Git 설정에 문제가 있습니다. 업데이트를 건너뜁니다.")
        return

    if not Helper.check_github_updates():
        Helper.CustomPrint("✅ 최신 버전입니다.")
        return

    Helper.CustomPrint("🔄 새로운 업데이트가 있습니다. 업데이트를 시작합니다...")
    if not Helper.perform_git_update():
        Helper.CustomPrint("❌ 업데이트에 실패했습니다. 기존 버전으로 실행합니다.")
        return

    Helper.CustomPrint("✅ 업데이트가 완료되었습니다.")
    Helper.CustomPrint("✅ 프로그램을 재실행해주세요.")
    raise SystemExit(0)



def main() -> None:
    """Run the bot in the terminal exactly as ``python main.py`` did before."""

    ensure_runtime_layout()
    check_and_update()

    from Lib import Helper


    Helper.CustomPrint("📱 카카오톡이 실행되지 않은 경우 자동으로 실행됩니다")

    engine = BotEngine()
    try:
        engine.run()
    except KeyboardInterrupt:
        engine.stop()


if __name__ == "__main__":
    main()
