import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


logger = logging.getLogger(__name__)

# 通知済みの実行キーを覚えておく件数。重なり時間内の再通知を防げれば十分。
MAX_NOTIFIED_RUNS = 200


@dataclass
class State:
    # 次に読むタスクイベントのカーソル。None なら未購読（初回は「今から」を始点にする）。
    event_cursor: int | None = None
    # 失敗した実行を最後に確認した時刻（ISO 8601）。
    runs_checked_at: str | None = None
    notified_runs: list[str] = field(default_factory=list)
    # 朝のまとめを最後に送った日付（YYYY-MM-DD）。再起動時の二重送信を防ぐ。
    last_summary_date: str | None = None
    # 最後に処理した「テスト送信」の依頼（設定画面の test_requested_at）。
    last_test_request: str | None = None

    def remember_run(self, run_key):
        if run_key in self.notified_runs:
            return
        self.notified_runs.append(run_key)
        del self.notified_runs[:-MAX_NOTIFIED_RUNS]


class StateStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return State()
        except (OSError, ValueError):
            logger.warning("状態ファイルを読めないため、最初から購読し直します: %s", self.path)
            return State()
        known = {name: raw[name] for name in State.__dataclass_fields__ if name in raw}
        return State(**known)

    def save(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(asdict(state), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
