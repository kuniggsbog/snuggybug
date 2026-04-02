"""
Competition tracking module for NEXUS.
Handles competition config, snapshot storage, FP projections and forecasting.
"""
import json
import pandas as pd
import datetime
import base64
import urllib.request
import io
from pathlib import Path

COMP_DIR = Path("data/competitions")


def _ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def _get_secrets():
    try:
        import streamlit as st
        return st.secrets.get("GITHUB_TOKEN"), st.secrets.get("GITHUB_REPO", "kuniggsbog/Nexus")
    except Exception:
        return None, None


def _gh_get(path_str: str, token: str, repo: str):
    url = f"https://api.github.com/repos/{repo}/contents/{path_str}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            content = base64.b64decode(data["content"]).decode("utf-8")
            return content, data["sha"]
    except Exception:
        return None, None


def _gh_put(path_str: str, content: str, sha, token: str, repo: str, msg: str = "competition update"):
    url = f"https://api.github.com/repos/{repo}/contents/{path_str}"
    payload = {"message": msg, "content": base64.b64encode(content.encode()).decode()}
    if sha:
        payload["sha"] = sha
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="PUT", headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status in (200, 201)
    except Exception:
        return False


def _write_file(path_str: str, content: str, msg: str = "competition update"):
    """Write to GitHub if token available, else write locally."""
    token, repo = _get_secrets()
    if token:
        _, sha = _gh_get(path_str, token, repo)
        return _gh_put(path_str, content, sha, token, repo, msg)
    else:
        local = Path(path_str)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(content)
        return True


def _read_file(path_str: str) -> str | None:
    """Read from GitHub if token available, else read locally."""
    token, repo = _get_secrets()
    if token:
        content, _ = _gh_get(path_str, token, repo)
        return content
    local = Path(path_str)
    if local.exists():
        return local.read_text()
    return None


# ── Competition CRUD ───────────────────────────────────────────────────────

def list_competitions() -> list[dict]:
    """Return all competition configs from local data/competitions/."""
    comps = []
    if not COMP_DIR.exists():
        return comps
    for comp_dir in sorted(COMP_DIR.iterdir()):
        if comp_dir.is_dir():
            cfg_path = comp_dir / "config.json"
            if cfg_path.exists():
                try:
                    cfg = json.loads(cfg_path.read_text())
                    cfg["_id"] = comp_dir.name
                    comps.append(cfg)
                except Exception:
                    pass
    return comps


def get_competition(comp_id: str) -> dict | None:
    cfg_path = COMP_DIR / comp_id / "config.json"
    if not cfg_path.exists():
        return None
    try:
        cfg = json.loads(cfg_path.read_text())
        cfg["_id"] = comp_id
        return cfg
    except Exception:
        return None


def save_competition(comp_id: str, config: dict) -> tuple[bool, str]:
    """Save competition config locally and to GitHub."""
    _ensure_dir(COMP_DIR / comp_id)
    path_str = f"data/competitions/{comp_id}/config.json"
    content = json.dumps(config, indent=2)
    # Always write locally
    (COMP_DIR / comp_id / "config.json").write_text(content)
    # Write to GitHub
    _write_file(path_str, content, f"competition: save config {comp_id}")
    return True, f"Competition '{config.get('name', comp_id)}' saved."


def delete_competition(comp_id: str) -> tuple[bool, str]:
    import shutil
    path = COMP_DIR / comp_id
    if path.exists():
        shutil.rmtree(path)
    return True, "Competition deleted."


# ── Snapshots ──────────────────────────────────────────────────────────────

def list_snapshots(comp_id: str) -> list[str]:
    """Return sorted list of snapshot filenames for a competition."""
    snap_dir = COMP_DIR / comp_id
    if not snap_dir.exists():
        return []
    return sorted([f.name for f in snap_dir.glob("snapshot_*.csv")])


def save_snapshot(comp_id: str, df: pd.DataFrame) -> tuple[bool, str]:
    """Save a new snapshot CSV for a competition."""
    _ensure_dir(COMP_DIR / comp_id)
    existing = list_snapshots(comp_id)
    next_num = len(existing) + 1
    filename = f"snapshot_{next_num:03d}.csv"
    path_str = f"data/competitions/{comp_id}/{filename}"
    content = df.to_csv(index=False)
    (COMP_DIR / comp_id / filename).write_text(content)
    _write_file(path_str, content, f"competition: add snapshot {filename} for {comp_id}")
    return True, f"Snapshot {next_num} saved ({len(df)} players)"


def load_snapshot(comp_id: str, filename: str) -> pd.DataFrame:
    path = COMP_DIR / comp_id / filename
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def load_latest_snapshot(comp_id: str) -> pd.DataFrame:
    snaps = list_snapshots(comp_id)
    if not snaps:
        return pd.DataFrame()
    return load_snapshot(comp_id, snaps[-1])


def load_previous_snapshot(comp_id: str) -> pd.DataFrame:
    snaps = list_snapshots(comp_id)
    if len(snaps) < 2:
        return pd.DataFrame()
    return load_snapshot(comp_id, snaps[-2])


# ── FP Calculation ─────────────────────────────────────────────────────────

def calc_fp(fights: int, tiers: list[dict]) -> int:
    """Calculate FP earned for a given fight count based on tier rules."""
    for tier in sorted(tiers, key=lambda t: t["min_fights"], reverse=True):
        if fights >= tier["min_fights"]:
            base = tier["base_fp"]
            extra = 0
            if tier.get("per_100", 0) > 0:
                extra_fights = fights - tier["min_fights"]
                extra = (extra_fights // 100) * tier["per_100"]
                if tier.get("max_fp"):
                    extra = min(extra, tier["max_fp"] - base)
            return base + extra
    return 0


def get_fp_projections(comp_id: str, config: dict) -> pd.DataFrame:
    """Return DataFrame with FP projections for all players in latest snapshot."""
    df = load_latest_snapshot(comp_id)
    if df.empty:
        return pd.DataFrame()

    # Normalise columns
    if "Fights" not in df.columns and "fights" in df.columns:
        df = df.rename(columns={"fights": "Fights"})
    if "Player" not in df.columns and "player" in df.columns:
        df = df.rename(columns={"player": "Player"})

    win_tiers  = config.get("win",  {}).get("tiers", [])
    lose_tiers = config.get("lose", {}).get("tiers", [])

    rows = []
    for _, row in df.iterrows():
        fights   = int(row.get("Fights", 0))
        win_fp   = calc_fp(fights, win_tiers)
        lose_fp  = calc_fp(fights, lose_tiers)

        # Next tier info
        next_tier_gap = None
        all_mins = sorted(set(t["min_fights"] for t in win_tiers))
        for m in all_mins:
            if fights < m:
                next_tier_gap = m - fights
                break

        rows.append({
            "Player":        str(row.get("Player", "?")),
            "Fights":        fights,
            "Win FP":        win_fp,
            "Lose FP":       lose_fp,
            "To Next Tier":  next_tier_gap,
        })

    result = pd.DataFrame(rows).sort_values("Fights", ascending=False).reset_index(drop=True)
    return result


# ── Momentum ───────────────────────────────────────────────────────────────

def get_momentum(comp_id: str) -> pd.DataFrame:
    """Return delta and % change between latest and previous snapshot."""
    curr = load_latest_snapshot(comp_id)
    prev = load_previous_snapshot(comp_id)

    if curr.empty:
        return pd.DataFrame()

    for df in [curr, prev]:
        if "Fights" not in df.columns and "fights" in df.columns:
            df.rename(columns={"fights": "Fights"}, inplace=True)
        if "Player" not in df.columns and "player" in df.columns:
            df.rename(columns={"player": "Player"}, inplace=True)
        if "Player_ID" not in df.columns and "player_id" in df.columns:
            df.rename(columns={"player_id": "Player_ID"}, inplace=True)

    if prev.empty:
        curr["Delta"]  = 0
        curr["Pct"]    = 0.0
        return curr[["Player", "Fights", "Delta", "Pct"]].sort_values("Fights", ascending=False)

    merged = curr.merge(
        prev[["Player", "Fights"]].rename(columns={"Fights": "Fights_prev"}),
        on="Player", how="left"
    )
    merged["Fights_prev"] = merged["Fights_prev"].fillna(0)
    merged["Delta"] = merged["Fights"].astype(int) - merged["Fights_prev"].astype(int)
    merged["Pct"]   = merged.apply(
        lambda r: round(r["Delta"] / r["Fights_prev"] * 100, 1) if r["Fights_prev"] > 0 else 0.0, axis=1
    )
    return merged[["Player", "Fights", "Delta", "Pct"]].sort_values("Fights", ascending=False).reset_index(drop=True)


# ── Forecast ───────────────────────────────────────────────────────────────

def get_forecast(comp_id: str, config: dict) -> pd.DataFrame:
    """Project final fight counts based on average fights per snapshot."""
    snaps = list_snapshots(comp_id)
    if not snaps:
        return pd.DataFrame()

    all_dfs = []
    for i, snap in enumerate(snaps):
        df = load_snapshot(comp_id, snap)
        if "Fights" not in df.columns and "fights" in df.columns:
            df = df.rename(columns={"fights": "Fights"})
        if "Player" not in df.columns and "player" in df.columns:
            df = df.rename(columns={"player": "Player"})
        df["_snap"] = i + 1
        all_dfs.append(df[["Player", "Fights", "_snap"]])

    combined = pd.concat(all_dfs, ignore_index=True)
    n_snaps  = len(snaps)

    # Estimate total snapshots in the round — assume round has ~8 snapshots if unknown
    total_snaps = config.get("total_snapshots", 8)

    rows = []
    latest_df = load_latest_snapshot(comp_id)
    if "Fights" not in latest_df.columns and "fights" in latest_df.columns:
        latest_df = latest_df.rename(columns={"fights": "Fights"})
    if "Player" not in latest_df.columns and "player" in latest_df.columns:
        latest_df = latest_df.rename(columns={"player": "Player"})

    win_tiers  = config.get("win",  {}).get("tiers", [])
    lose_tiers = config.get("lose", {}).get("tiers", [])
    tier_mins  = sorted(set(t["min_fights"] for t in win_tiers), reverse=True)

    for _, row in latest_df.iterrows():
        player  = str(row.get("Player", "?"))
        current = int(row.get("Fights", 0))
        history = combined[combined["Player"] == player]["Fights"].tolist()

        if len(history) >= 2:
            diffs = [history[i] - history[i-1] for i in range(1, len(history))]
            avg_per_snap = sum(diffs) / len(diffs)
        elif len(history) == 1:
            avg_per_snap = history[0] / n_snaps
        else:
            avg_per_snap = 0

        remaining   = total_snaps - n_snaps
        projected   = int(current + avg_per_snap * remaining)

        # Determine projected tier
        proj_tier = "Below 3k"
        for m in tier_mins:
            if projected >= m:
                proj_tier = f"{m:,}+ tier"
                break

        rows.append({
            "Player":       player,
            "Current":      current,
            "Avg/Snap":     round(avg_per_snap),
            "Projected":    projected,
            "Tier":         proj_tier,
            "Win FP":       calc_fp(projected, win_tiers),
            "Lose FP":      calc_fp(projected, lose_tiers),
        })

    return pd.DataFrame(rows).sort_values("Projected", ascending=False).reset_index(drop=True)
