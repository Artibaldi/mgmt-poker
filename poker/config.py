"""Общая конфигурация: корень проекта, .env с кредами Jira, маппинг полей, папка сессии."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSIONS = ROOT / "sessions"


def load_env(path=None):
    """Креды: --env > $POKER_ENV > ./.env; переменные окружения перекрывают файл."""
    candidates = [path, os.environ.get("POKER_ENV"), ROOT / ".env"]
    env = {}
    for c in candidates:
        if c and Path(c).is_file():
            for line in Path(c).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
            break
    for k in ("JIRA_URL", "JIRA_PROJECT_KEY", "JIRA_USERNAME", "JIRA_PASSWORD", "POKER_DAILY_DIR"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def load_jira_config():
    """config/jira.json, если есть, иначе config/jira.example.json."""
    for name in ("jira.json", "jira.example.json"):
        p = ROOT / "config" / name
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError("нет config/jira.json и config/jira.example.json")


def session_dir(login, period):
    """sessions/<login>_<YYYY-MM> — всё про одного человека за один период."""
    d = SESSIONS / f"{login}_{period}"
    d.mkdir(parents=True, exist_ok=True)
    return d
