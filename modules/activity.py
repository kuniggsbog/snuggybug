"""
Activity tracking — reads/writes data/activity/activity_log.csv via GitHub API.
Falls back to local file if no GitHub token is configured.
"""
import pandas as pd
import datetime
import os
import base64
from pathlib import Path

ACTIVITY_FILE = Path("data/activity/activity_log.csv")
COLS = ["timestamp", "player", "page", "action"]
GITHUB_REPO = None
GITHUB_TOKEN = None

def _init_github():
    global GITHUB_REPO, GITHUB_TOKEN
    try:
        import streamlit as st
        GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
        GITHUB_REPO  = st.secrets.get("GITHUB_REPO", "kuniggsbog/Nexus")
    except Exception:
        pass

def _gh_get_file():
    """Fetch current file content + SHA from GitHub."""
    import urllib.request, json
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{ACTIVITY_FILE}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    })
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            content = base64.b64decode(data["content"]).decode("utf-8")
            return content, data["sha"]
    except Exception:
        return None, None

def _gh_write_file(content: str, sha: str = None):
    """Write file to GitHub."""
    import urllib.request, json
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{ACTIVITY_FILE}"
    payload = {
        "message": "activity: update log",
        "content": base64.b64encode(content.encode()).decode(),
    }
    if sha:
        payload["sha"] = sha
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="PUT", headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status in (200, 201)
    except Exception:
        return False

def load_log(days: int = 30) -> pd.DataFrame:
    """Load activity log, filtered to last N days."""
    _init_github()
    df = pd.DataFrame(columns=COLS)

    if GITHUB_TOKEN:
        content, _ = _gh_get_file()
        if content:
            import io
            try:
                df = pd.read_csv(io.StringIO(content), on_bad_lines="skip")
            except Exception:
                pass
    elif ACTIVITY_FILE.exists():
        try:
            df = pd.read_csv(ACTIVITY_FILE, on_bad_lines="skip")
        except Exception:
            pass

    if df.empty or "timestamp" not in df.columns:
        return pd.DataFrame(columns=COLS)

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    return df[df["timestamp"] >= cutoff].reset_index(drop=True)

def log_event(player: str, page: str, action: str):
    """Append one event. Writes to GitHub (or local fallback). Non-blocking best-effort."""
    if not player or player == "— Select your name —":
        return
    _init_github()
    import csv, io as _io
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    buf = _io.StringIO()
    csv.writer(buf).writerow([now, player, page, action])
    new_row = buf.getvalue()

    if GITHUB_TOKEN:
        content, sha = _gh_get_file()
        if content is None:
            content = ",".join(COLS) + "\n"
            sha = None
        content += new_row
        # Keep only last 5000 rows to avoid bloat
        lines = content.strip().split("\n")
        if len(lines) > 5001:
            lines = [lines[0]] + lines[-5000:]
            content = "\n".join(lines) + "\n"
        _gh_write_file(content, sha)
    else:
        # Local fallback
        ACTIVITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not ACTIVITY_FILE.exists():
            with open(ACTIVITY_FILE, "w", newline="") as f:
                f.write(",".join(COLS) + "\n")
        with open(ACTIVITY_FILE, "a", newline="") as f:
            f.write(new_row)

def get_last_seen(days: int = 30) -> dict:
    """Return {player: last_seen_datetime} for all players seen in last N days."""
    df = load_log(days)
    if df.empty:
        return {}
    return (df.groupby("player")["timestamp"]
              .max()
              .sort_values(ascending=False)
              .to_dict())

def get_page_stats(days: int = 30) -> pd.DataFrame:
    """Return page visit counts per player."""
    df = load_log(days)
    if df.empty:
        return pd.DataFrame()
    visits = df[df["action"] == "visit"].copy()
    return visits.groupby(["player","page"]).size().reset_index(name="visits")

def get_profile_views(days: int = 30) -> pd.DataFrame:
    """Return profile view counts — who viewed whom."""
    df = load_log(days)
    if df.empty:
        return pd.DataFrame()
    pv = df[df["action"].str.startswith("viewed:", na=False)].copy()
    pv["viewed"] = pv["action"].str.replace("viewed:", "", regex=False)
    return pv.groupby(["player","viewed"]).size().reset_index(name="views")

def get_h2h_stats(days: int = 30) -> pd.DataFrame:
    """Return head to head matchup counts."""
    df = load_log(days)
    if df.empty:
        return pd.DataFrame()
    h2h = df[df["action"].str.startswith("h2h:", na=False)].copy()
    h2h["matchup"] = h2h["action"].str.replace("h2h:", "", regex=False)
    return h2h.groupby("matchup").size().reset_index(name="count").sort_values("count", ascending=False)
