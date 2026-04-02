"""
Snuggy Bug — NEXUS AI assistant.
Builds guild data context and queries Claude Haiku for adaptive answers.
Tracks points and badges via GitHub activity CSV.
"""
import datetime
import base64
import pandas as pd
from pathlib import Path
from modules.comparisons import sort_seasons

BADGES_FILE = Path("data/activity/ai_badges.csv")
BADGES_COLS = ["player", "badge_id", "badge_name", "badge_icon", "earned_date"]

CONTEXT_VERSION = 5  # bump this whenever build_guild_context changes


def _badges_gh_init():
    try:
        import streamlit as st
        return st.secrets.get("GITHUB_TOKEN"), st.secrets.get("GITHUB_REPO", "kuniggsbog/Nexus")
    except Exception:
        return None, None


def _badges_gh_get(token, repo):
    import urllib.request, json
    url = f"https://api.github.com/repos/{repo}/contents/{BADGES_FILE}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            return base64.b64decode(data["content"]).decode("utf-8"), data["sha"]
    except Exception:
        return None, None


def _badges_gh_write(content, sha, token, repo):
    import urllib.request, json
    url = f"https://api.github.com/repos/{repo}/contents/{BADGES_FILE}"
    payload = {"message": "badges: update ai_badges", "content": base64.b64encode(content.encode()).decode()}
    if sha:
        payload["sha"] = sha
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="PUT", headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status in (200, 201)
    except Exception:
        return False


def load_player_badges(player: str) -> list[dict]:
    """Return list of BADGES dicts earned by this player."""
    import io
    token, repo = _badges_gh_init()
    content = None

    if token:
        content, _ = _badges_gh_get(token, repo)
    elif BADGES_FILE.exists():
        content = BADGES_FILE.read_text(encoding="utf-8")

    if not content:
        return []
    try:
        df = pd.read_csv(io.StringIO(content))
        player_rows = df[df["player"].str.strip().str.lower() == player.strip().lower()]
        earned_ids = set(player_rows["badge_id"].tolist())
        return [b for b in BADGES if b["id"] in earned_ids]
    except Exception:
        return []


def save_badges(player: str, earned_badges: list[dict]):
    """Persist any newly earned badges for this player to ai_badges.csv."""
    if not player or not earned_badges:
        return
    import io

    token, repo = _badges_gh_init()
    header = ",".join(BADGES_COLS) + "\n"
    today = datetime.date.today().isoformat()

    # Load existing
    existing_content, sha = None, None
    if token:
        existing_content, sha = _badges_gh_get(token, repo)
    elif BADGES_FILE.exists():
        existing_content = BADGES_FILE.read_text(encoding="utf-8")

    if existing_content:
        try:
            df = pd.read_csv(io.StringIO(existing_content))
            existing_ids = set(df[df["player"].str.strip().str.lower() == player.strip().lower()]["badge_id"].tolist())
        except Exception:
            df = pd.DataFrame(columns=BADGES_COLS)
            existing_ids = set()
            existing_content = header
    else:
        df = pd.DataFrame(columns=BADGES_COLS)
        existing_ids = set()
        existing_content = header

    new_rows = [
        f"{player},{b['id']},{b['name']},{b['icon']},{today}\n"
        for b in earned_badges if b["id"] not in existing_ids
    ]
    if not new_rows:
        return

    new_content = existing_content.rstrip("\n") + "\n" + "".join(new_rows)

    if token:
        _badges_gh_write(new_content, sha, token, repo)
    else:
        BADGES_FILE.parent.mkdir(parents=True, exist_ok=True)
        BADGES_FILE.write_text(new_content, encoding="utf-8")


# ── Data context builder ───────────────────────────────────────────────────

def build_guild_context(
    gbg_df: pd.DataFrame,
    qi_df: pd.DataFrame,
    members_df: pd.DataFrame,
    guild_stats_df: pd.DataFrame = None,
    activity_df: pd.DataFrame = None,
    current_user: str = None,
) -> str:
    """Build a rich text context string from all guild data sources."""
    lines = []
    lines.append("You are Snuggy Bug, a friendly and knowledgeable guild data assistant for the Forge of Empires guild .Nexus.")
    lines.append("You have access to the following guild data. Answer questions accurately using only this data.")
    lines.append("Be adaptive: short answers for simple questions, detailed breakdowns for complex ones.")
    lines.append("Always include specific numbers. Never make up data not present below.")
    lines.append("")

    # ── Personal context ──
    if current_user:
        lines.append(f"CURRENT USER: {current_user} (personalise answers for this player where relevant)")
        lines.append("")

    # ── Derive current player set from latest members snapshot ───────────
    current_player_ids: set[str] = set()
    current_player_names: set[str] = set()
    if not members_df.empty and "snapshot" in members_df.columns:
        _snaps = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
        if _snaps:
            _latest_mem = members_df[members_df["snapshot"] == _snaps[0]]
            if "Player_ID" in _latest_mem.columns:
                current_player_ids = set(_latest_mem["Player_ID"].dropna().astype(str).str.strip().tolist())
            _name_col = "Player" if "Player" in _latest_mem.columns else "member"
            if _name_col in _latest_mem.columns:
                current_player_names = set(_latest_mem[_name_col].dropna().astype(str).str.strip().tolist())

    def _filter_df(df: pd.DataFrame) -> pd.DataFrame:
        """Filter a GBG/QI DataFrame to current members using Player_ID (preferred) or Player name."""
        if df.empty:
            return df
        if current_player_ids and "Player_ID" in df.columns:
            return df[df["Player_ID"].astype(str).str.strip().isin(current_player_ids)]
        if current_player_names and "Player" in df.columns:
            return df[df["Player"].isin(current_player_names)]
        return df

    # Filter guild_stats_df to current members only
    if guild_stats_df is not None and not guild_stats_df.empty and current_player_names:
        guild_stats_df = guild_stats_df[
            guild_stats_df["player_name"].str.strip().isin(current_player_names)
        ].copy()

    # ── GBG summary ──
    if not gbg_df.empty and "season" in gbg_df.columns:
        seasons = sort_seasons(gbg_df["season"].unique().tolist())
        latest = seasons[-1] if seasons else None
        lines.append(f"GBG SEASONS TRACKED: {len(seasons)}")
        lines.append(f"LATEST GBG SEASON: {latest}")
        if latest:
            lat = _filter_df(gbg_df[gbg_df["season"] == latest]).sort_values("Fights", ascending=False)
            lines.append(f"LATEST GBG TOTAL FIGHTS: {int(lat['Fights'].sum()):,}")
            lines.append(f"LATEST GBG PLAYERS: {len(lat)}")
            lines.append("LATEST GBG TOP 10:")
            for i, (_, r) in enumerate(lat.head(10).iterrows()):
                lines.append(f"  {i+1}. {r['Player']} — {int(r['Fights']):,} fights, {int(r.get('Negotiations',0)):,} negs")
            lines.append("LATEST GBG BELOW 1000 FIGHTS:")
            below = lat[lat["Fights"] < 1000]
            for _, r in below.iterrows():
                lines.append(f"  {r['Player']} — {int(r['Fights']):,} fights")
        # All-time GBG records
        if len(gbg_df) > 0:
            best_row = gbg_df.loc[gbg_df["Fights"].idxmax()]
            lines.append(f"ALL-TIME GBG SINGLE SEASON RECORD: {best_row['Player']} with {int(best_row['Fights']):,} fights in {best_row['season']}")
        # Per-player lifetime totals (current members only)
        lines.append("LIFETIME GBG FIGHTS (top 15, current members):")
        lifetime = _filter_df(gbg_df).groupby("Player")["Fights"].sum().sort_values(ascending=False).head(15)
        for p, f in lifetime.items():
            lines.append(f"  {p}: {int(f):,}")
        # Season totals (all)
        lines.append("GBG SEASON TOTALS (all seasons):")
        for s in seasons:
            tot = int(gbg_df[gbg_df["season"]==s]["Fights"].sum())
            lines.append(f"  {s}: {tot:,}")
        # Full per-player per-season breakdown
        lines.append("GBG ALL SEASONS PER PLAYER (fights per season, current members):")
        _gbg_all = _filter_df(gbg_df).copy()
        _pivot = _gbg_all.pivot_table(index="Player", columns="season", values="Fights", aggfunc="sum").fillna(0)
        _pivot = _pivot[sort_seasons(_pivot.columns.tolist())]
        _header = "player | " + " | ".join(str(c) for c in _pivot.columns)
        lines.append(f"  {_header}")
        for player, row in _pivot.iterrows():
            vals = " | ".join(str(int(v)) for v in row.values)
            lines.append(f"  {player} | {vals}")
        lines.append("")

    # ── Personal GBG history ──
    if current_user and not gbg_df.empty:
        p_gbg = gbg_df[gbg_df["Player"] == current_user]
        if not p_gbg.empty:
            p_seasons = sort_seasons(p_gbg["season"].unique().tolist())
            p_avg = int(p_gbg["Fights"].mean())
            p_best = int(p_gbg["Fights"].max())
            lines.append(f"CURRENT USER GBG HISTORY ({current_user}):")
            lines.append(f"  Seasons played: {len(p_seasons)}")
            lines.append(f"  Average fights/season: {p_avg:,}")
            lines.append(f"  Personal best: {p_best:,}")
            _recent = [f"{s}: {int(p_gbg[p_gbg['season']==s]['Fights'].sum()):,}" for s in p_seasons[-3:]]
            lines.append(f"  Latest 3 seasons: {', '.join(_recent)}")
            lines.append("")

    # ── QI summary ──
    if not qi_df.empty and "season" in qi_df.columns:
        qi_seasons = sort_seasons(qi_df["season"].unique().tolist())
        qi_latest = qi_seasons[-1] if qi_seasons else None
        lines.append(f"QI SEASONS TRACKED: {len(qi_seasons)}")
        lines.append(f"LATEST QI SEASON: {qi_latest}")
        if qi_latest:
            qi_lat = _filter_df(qi_df[qi_df["season"] == qi_latest]).sort_values("Progress", ascending=False)
            lines.append(f"LATEST QI TOTAL PROGRESS: {int(qi_lat['Progress'].sum()):,}")
            lines.append("LATEST QI TOP 10:")
            for i, (_, r) in enumerate(qi_lat.head(10).iterrows()):
                lines.append(f"  {i+1}. {r['Player']} — {int(r['Progress']):,} progress")
            below_qi = qi_lat[qi_lat["Progress"] < 3500]
            if not below_qi.empty:
                lines.append("LATEST QI BELOW 3500 PROGRESS:")
                for _, r in below_qi.iterrows():
                    lines.append(f"  {r['Player']} — {int(r['Progress']):,}")
        # Full per-player per-season breakdown
        lines.append("QI ALL SEASONS PER PLAYER (progress per season, current members):")
        _qi_all = _filter_df(qi_df).copy()
        _qi_pivot = _qi_all.pivot_table(index="Player", columns="season", values="Progress", aggfunc="sum").fillna(0)
        _qi_pivot = _qi_pivot[sort_seasons(_qi_pivot.columns.tolist())]
        _qi_header = "player | " + " | ".join(str(c) for c in _qi_pivot.columns)
        lines.append(f"  {_qi_header}")
        for player, row in _qi_pivot.iterrows():
            vals = " | ".join(str(int(v)) for v in row.values)
            lines.append(f"  {player} | {vals}")
        lines.append("")

    # ── Members summary ──
    if not members_df.empty and "snapshot" in members_df.columns:
        snaps = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
        latest_snap = snaps[0] if snaps else None
        if latest_snap:
            mem = members_df[members_df["snapshot"] == latest_snap].copy()
            mem["points"] = pd.to_numeric(mem["points"], errors="coerce").fillna(0)
            mem = mem.sort_values("points", ascending=False)
            lines.append(f"MEMBERS SNAPSHOT: {latest_snap} ({len(mem)} members)")
            lines.append("TOP 10 BY POINTS:")
            for i, (_, r) in enumerate(mem.head(10).iterrows()):
                lines.append(f"  {i+1}. {r.get('Player', r.get('member','?'))} — {int(r['points']):,} pts, {r.get('eraName','?')}")
            era_counts = mem["eraName"].value_counts()
            lines.append("ERA DISTRIBUTION:")
            for era, count in era_counts.items():
                lines.append(f"  {era}: {count} players")
            total_goods = int(mem["guildgoods"].sum()) if "guildgoods" in mem.columns else 0
            lines.append(f"TOTAL GUILD GOODS: {total_goods:,}")
            lines.append("")

    # ── Guild minimums compliance ──
    if not gbg_df.empty:
        lines.append("GUILD MINIMUMS COMPLIANCE (GBG 1000 fights — players with 2+ violations):")
        for pid in gbg_df["Player_ID"].astype(str).unique():
            p_hist = gbg_df[gbg_df["Player_ID"].astype(str) == pid]
            violations = int((p_hist["Fights"] < 1000).sum())
            if violations >= 2:
                pname = p_hist["Player"].iloc[-1]
                lines.append(f"  {pname}: {violations} seasons below minimum of {len(p_hist)} total")
        lines.append("")

    # ── Streaks ──
    if not gbg_df.empty:
        lines.append("PLAYER SEASON COUNTS (top 10 veterans, current members):")
        veteran = _filter_df(gbg_df).groupby("Player")["season"].nunique().sort_values(ascending=False).head(10)
        for p, s in veteran.items():
            lines.append(f"  {p}: {s} seasons")
        lines.append("")

    # ── Hall of fame highlights ──
    from modules.player_profile import get_hall_of_fame
    hof = get_hall_of_fame(gbg_df, qi_df)
    if hof:
        lines.append("HALL OF FAME (current players, all-time season wins):")
        for entry in hof:
            lines.append(f"  {entry['player']}: {entry['gbg_wins']} GBG wins, {entry['qi_wins']} QI wins ({entry['total']} total)")
        lines.append("")

    # ── Guild stats (battle boosts + production) ──
    if guild_stats_df is not None and not guild_stats_df.empty:

        def _top(col, label, fmt="{:,.0f}", n=10, halve=False):
            if col not in guild_stats_df.columns:
                return
            s = guild_stats_df[["player_name", col]].copy()
            s[col] = pd.to_numeric(s[col], errors="coerce")
            if halve:
                s.loc[s["player_name"].str.strip().str.lower() != "kuniggsbog", col] /= 2
            s = s.dropna().sort_values(col, ascending=False).head(n)
            lines.append(f"{label} (top {n}):")
            for i, (_, r) in enumerate(s.iterrows()):
                lines.append(f"  {i+1}. {r['player_name']} — {fmt.format(int(r[col]))}")

        lines.append("BATTLE BOOSTS & PRODUCTION (from guild stats):")
        lines.append(f"Total players with stats: {len(guild_stats_df)}")
        lines.append("")

        _top("gbg_attack",                  "GBG ATTACK BOOST (attacker)")
        _top("gbg_defense",                 "GBG DEFENSE BOOST (attacker)")
        _top("gbg_defending_units_attack",  "GBG ATTACK BOOST (defender)")
        _top("gbg_defending_units_defense", "GBG DEFENSE BOOST (defender)")
        _top("main_attack",                 "MAIN ATTACK BOOST")
        _top("main_defense",                "MAIN DEFENSE BOOST")
        _top("ge_attack",                   "GE ATTACK BOOST")
        _top("ge_defense",                  "GE DEFENSE BOOST")
        _top("fp_production",               "FORGE POINTS PRODUCTION", halve=True)
        _top("goods_production",            "GOODS PRODUCTION")
        _top("guild_goods_production",      "GUILD GOODS PRODUCTION")
        _top("units_production",            "UNITS PRODUCTION")
        _top("critical_hit",                "CRITICAL HIT CHANCE", fmt="{:.2f}%")
        lines.append("")

        # Full player stat table so Snuggy Bug can answer specific player queries
        lines.append("FULL PLAYER STATS TABLE:")
        lines.append("player | gbg_atk | gbg_def | fp_prod | guild_goods | crit%")
        for _, r in guild_stats_df.iterrows():
            fp = pd.to_numeric(r.get("fp_production", 0), errors="coerce") or 0
            if str(r["player_name"]).strip().lower() != "kuniggsbog":
                fp = fp / 2
            lines.append(
                f"  {r['player_name']} | "
                f"gbg_atk:{int(pd.to_numeric(r.get('gbg_attack',0), errors='coerce') or 0):,}% | "
                f"gbg_def:{int(pd.to_numeric(r.get('gbg_defense',0), errors='coerce') or 0):,}% | "
                f"fp:{int(fp):,} | "
                f"guild_goods:{int(pd.to_numeric(r.get('guild_goods_production',0), errors='coerce') or 0):,} | "
                f"crit:{float(pd.to_numeric(r.get('critical_hit',0), errors='coerce') or 0):.2f}%"
            )
        lines.append("")

    # ── Guild health ──────────────────────────────────────────────────────────
    from modules.player_profile import (
        get_guild_health, get_active_streak, get_newcomers,
        get_most_improved, get_most_consistent_players,
        get_points_leaderboard, get_goods_leaderboard, get_battles_leaderboard,
    )
    from modules.comparisons import (
        gbg_season_comparison, qi_season_comparison,
        most_improved_gbg, most_improved_qi, detect_player_status,
    )

    health = get_guild_health(gbg_df, qi_df, members_df)
    if health:
        lines.append("GUILD HEALTH:")
        if "gbg_participation" in health:
            lines.append(f"  GBG participation rate: {health['gbg_participation']}% ({health['gbg_players']} of {health['total_members']} members, latest: {health['latest_gbg_season']})")
        if "inactive_count" in health:
            lines.append(f"  Zero-fight players latest GBG: {health['inactive_count']}")
            if health["inactive_players"]:
                lines.append(f"  Names: {', '.join(health['inactive_players'])}")
        if "total_goods_latest" in health:
            delta_str = f" (delta from prev snapshot: {health['goods_delta']:+,})" if health.get("goods_delta") is not None else ""
            lines.append(f"  Total guild goods (latest snapshot): {health['total_goods_latest']:,}{delta_str}")
        lines.append("")

    # ── Active streaks ────────────────────────────────────────────────────────
    streaks = get_active_streak(gbg_df, qi_df)
    if streaks:
        lines.append("CONSECUTIVE GBG SEASON STREAKS (current players, top 10):")
        for s in streaks:
            lines.append(f"  {s['player']}: {s['streak']} in a row ({s['total_seasons']} total seasons)")
        lines.append("")

    # ── Newcomers ─────────────────────────────────────────────────────────────
    newcomers = get_newcomers(gbg_df, qi_df)
    if newcomers:
        lines.append(f"NEWCOMERS THIS SEASON ({len(newcomers)}):")
        for n in newcomers:
            lines.append(f"  {n['player']} — first seen in: {', '.join(n['sections'])}")
        lines.append("")

    # ── Most improved / biggest drop ─────────────────────────────────────────
    improved = get_most_improved(gbg_df, qi_df)
    if improved.get("best"):
        b = improved["best"]
        lines.append(f"MOST IMPROVED GBG ({b['seasons']}): {b['player']} +{b['delta']:,} fights ({b['pct']:+.1f}%) → {b['curr']:,}")
    if improved.get("worst"):
        w = improved["worst"]
        lines.append(f"BIGGEST GBG DROP ({w['seasons']}): {w['player']} {w['delta']:,} fights ({w['pct']:+.1f}%) → {w['curr']:,}")
    if improved.get("best") or improved.get("worst"):
        lines.append("")

    # ── Consistency rankings ──────────────────────────────────────────────────
    gbg_cons = get_most_consistent_players(gbg_df, qi_df, section="GBG")
    if not gbg_cons.empty:
        lines.append("GBG CONSISTENCY RANKINGS (veteran-weighted, top 10):")
        for i, (_, r) in enumerate(gbg_cons.iterrows()):
            cols = list(r.index)
            avg_col = [c for c in cols if "Avg" in str(c)]
            avg_val = r[avg_col[0]] if avg_col else "?"
            lines.append(f"  {i+1}. {r['Player']}: {r['Seasons']} seasons, avg {avg_val} fights, score {r['⭐ Score']}")
        lines.append("")

    qi_cons = get_most_consistent_players(gbg_df, qi_df, section="QI")
    if not qi_cons.empty:
        lines.append("QI CONSISTENCY RANKINGS (veteran-weighted, top 10):")
        for i, (_, r) in enumerate(qi_cons.iterrows()):
            cols = list(r.index)
            avg_col = [c for c in cols if "Avg" in str(c)]
            avg_val = r[avg_col[0]] if avg_col else "?"
            lines.append(f"  {i+1}. {r['Player']}: {r['Seasons']} seasons, avg {avg_val} progress, score {r['⭐ Score']}")
        lines.append("")

    # ── Season-over-season comparisons (current members, all players, Fights only) ──
    from modules.comparisons import gbg_season_comparison, qi_season_comparison
    gbg_comp_full = gbg_season_comparison(_filter_df(gbg_df))
    if not gbg_comp_full.empty:
        # Only players present in BOTH seasons (previous>0 avoids division-from-zero inflation)
        _gbg_active = gbg_comp_full[gbg_comp_full["Fights_previous"] > 0].copy()
        _gbg_sorted = _gbg_active.sort_values("Fights_pct", ascending=False).reset_index(drop=True)
        if not _gbg_sorted.empty:
            _top = _gbg_sorted.iloc[0]
            _bot = _gbg_sorted.iloc[-1]
            lines.append(f"GBG LAST ROUND BIGGEST % INCREASE (fights, players in both seasons): {_top['Player']} {_top['Fights_pct']:+.1f}% ({int(_top['Fights_previous']):,} → {int(_top['Fights_current']):,})")
            lines.append(f"GBG LAST ROUND BIGGEST % DECREASE (fights, players in both seasons): {_bot['Player']} {_bot['Fights_pct']:+.1f}% ({int(_bot['Fights_previous']):,} → {int(_bot['Fights_current']):,})")
        lines.append("GBG LAST ROUND % CHANGE RANKING — ALL CURRENT MEMBERS (sorted best→worst, both seasons only):")
        lines.append("  rank | player | prev_fights | curr_fights | change%")
        for i, (_, r) in enumerate(_gbg_sorted.iterrows(), 1):
            lines.append(f"  {i}. {r['Player']} | {int(r['Fights_previous']):,} | {int(r['Fights_current']):,} | {r['Fights_pct']:+.1f}%")
        lines.append("")

    qi_comp_full = qi_season_comparison(_filter_df(qi_df))
    if not qi_comp_full.empty:
        _qi_active = qi_comp_full[qi_comp_full["Progress_previous"] > 0].copy()
        _qi_sorted = _qi_active.sort_values("Progress_pct", ascending=False).reset_index(drop=True)
        if not _qi_sorted.empty:
            _qi_top = _qi_sorted.iloc[0]
            _qi_bot = _qi_sorted.iloc[-1]
            lines.append(f"QI LAST ROUND BIGGEST % INCREASE: {_qi_top['Player']} {_qi_top['Progress_pct']:+.1f}% ({int(_qi_top['Progress_previous']):,} → {int(_qi_top['Progress_current']):,})")
            lines.append(f"QI LAST ROUND BIGGEST % DECREASE: {_qi_bot['Player']} {_qi_bot['Progress_pct']:+.1f}% ({int(_qi_bot['Progress_previous']):,} → {int(_qi_bot['Progress_current']):,})")
        lines.append("QI LAST ROUND % CHANGE RANKING — ALL CURRENT MEMBERS (sorted best→worst, both seasons only):")
        lines.append("  rank | player | prev_progress | curr_progress | change%")
        for i, (_, r) in enumerate(_qi_sorted.iterrows(), 1):
            lines.append(f"  {i}. {r['Player']} | {int(r['Progress_previous']):,} | {int(r['Progress_current']):,} | {r['Progress_pct']:+.1f}%")
        lines.append("")

    # ── Player status (latest season) ─────────────────────────────────────────
    status_df = detect_player_status(gbg_df, qi_df)
    if not status_df.empty and "season" in status_df.columns:
        from modules.comparisons import sort_seasons as _ss
        for section_label, section_key in [("GBG", "GBG"), ("QI", "QI")]:
            sec_df = status_df[status_df["section"] == section_key]
            if sec_df.empty:
                continue
            latest_s = _ss(sec_df["season"].unique().tolist())[-1]
            latest_status = sec_df[sec_df["season"] == latest_s]
            new_p     = latest_status[latest_status["status"] == "new"]["Player"].tolist()
            returning = latest_status[latest_status["status"] == "returning"]["Player"].tolist()
            missing   = latest_status[latest_status["status"] == "missing"]["Player"].tolist()
            lines.append(f"{section_key} PLAYER STATUS (season: {latest_s}):")
            if new_p:      lines.append(f"  New: {', '.join(new_p)}")
            if returning:  lines.append(f"  Returning: {', '.join(returning)}")
            if missing:    lines.append(f"  Missing (was in prev season): {', '.join(missing)}")
            lines.append("")

    # ── Leaderboards (points, goods, battles) ────────────────────────────────
    pts_lb = get_points_leaderboard(members_df, gbg_df, qi_df)
    if pts_lb:
        lines.append("POINTS LEADERBOARD (top 10 current players):")
        for i, r in enumerate(pts_lb):
            lines.append(f"  {i+1}. {r['player']}: {r['points']:,} pts ({r['eraName']})")
        lines.append("")

    goods_lb = get_goods_leaderboard(members_df, gbg_df, qi_df)
    if goods_lb:
        lines.append("GUILD GOODS LEADERBOARD (top 10 current players):")
        for i, r in enumerate(goods_lb):
            lines.append(f"  {i+1}. {r['player']}: {r['guildgoods']:,} ({r['eraName']})")
        lines.append("")

    battles_lb = get_battles_leaderboard(members_df, gbg_df, qi_df)
    if battles_lb:
        lines.append("WON BATTLES LEADERBOARD (top 10 current players):")
        for i, r in enumerate(battles_lb):
            lines.append(f"  {i+1}. {r['player']}: {r['won_battles']:,} ({r['eraName']})")
        lines.append("")

    # ── App activity (who has been online) ───────────────────────────────────
    if activity_df is not None and not activity_df.empty and "timestamp" in activity_df.columns:
        import datetime as _dt
        now = _dt.datetime.utcnow()
        last_seen = (
            activity_df.groupby("player")["timestamp"].max()
            .sort_values(ascending=False)
        )
        lines.append("APP ACTIVITY (last 30 days — when each player last used NEXUS):")
        for player, ts in last_seen.items():
            days_ago = (now - ts).days
            if days_ago == 0:
                when = "today"
            elif days_ago == 1:
                when = "yesterday"
            else:
                when = f"{days_ago}d ago"
            lines.append(f"  {player}: last seen {when} ({ts.strftime('%Y-%m-%d')})")
        lines.append("")

        # Page visit counts
        if "page" in activity_df.columns and "action" in activity_df.columns:
            visits = activity_df[activity_df["action"] == "visit"]
            if not visits.empty:
                page_counts = visits.groupby("player").size().sort_values(ascending=False).head(10)
                lines.append("MOST ACTIVE USERS (by page visits, last 30 days):")
                for player, count in page_counts.items():
                    lines.append(f"  {player}: {count} visits")
                lines.append("")

    return "\n".join(lines)


# ── Proactive briefing builder ─────────────────────────────────────────────

def build_proactive_briefing(
    gbg_df: pd.DataFrame,
    qi_df: pd.DataFrame,
    members_df: pd.DataFrame,
    current_user: str = None,
    last_visit_days: int = 7,
) -> list[dict]:
    """Build a list of proactive insight cards to show before first message."""
    cards = []

    # Guild state
    if not gbg_df.empty:
        seasons = sort_seasons(gbg_df["season"].unique().tolist())
        latest = seasons[-1]
        lat = gbg_df[gbg_df["season"] == latest]
        below = int((lat["Fights"] < 1000).sum())
        total = int(lat["Fights"].sum())
        if below > 0:
            cards.append({
                "type": "warning",
                "icon": "⚠️",
                "title": f"{below} players below minimum",
                "body": f"Latest season ({latest}): {below} players under 1,000 fights. Guild total: {total:,}.",
                "colour": "#E74C3C",
            })
        else:
            cards.append({
                "type": "success",
                "icon": "✅",
                "title": "All players met minimum",
                "body": f"Latest season ({latest}): every active player hit 1,000+ fights. Guild total: {total:,}.",
                "colour": "#2ECC71",
            })

    # Milestones since last visit
    milestone_events = []
    if not gbg_df.empty:
        seasons = sort_seasons(gbg_df["season"].unique().tolist())
        latest = seasons[-1]
        for pid in gbg_df["Player_ID"].astype(str).unique():
            p_hist = gbg_df[gbg_df["Player_ID"].astype(str) == pid]
            total_f = int(p_hist["Fights"].sum())
            pname = p_hist["Player"].iloc[-1]
            for thresh, label in [(1_000_000,"1M"),(500_000,"500K"),(100_000,"100K")]:
                prev = total_f - int(p_hist[p_hist["season"]==latest]["Fights"].sum()) if latest in p_hist["season"].values else total_f
                if prev < thresh <= total_f:
                    milestone_events.append(f"{pname} crossed {label} lifetime fights")
    if milestone_events:
        cards.append({
            "type": "milestone",
            "icon": "🎖️",
            "title": f"{len(milestone_events)} milestone{'s' if len(milestone_events)>1 else ''} this season",
            "body": " · ".join(milestone_events[:3]),
            "colour": "#FFD700",
        })

    # Personal briefing
    if current_user and not gbg_df.empty:
        p_gbg = gbg_df[gbg_df["Player"] == current_user]
        if not p_gbg.empty:
            seasons = sort_seasons(p_gbg["season"].unique().tolist())
            latest = seasons[-1]
            this = int(p_gbg[p_gbg["season"]==latest]["Fights"].sum()) if latest in p_gbg["season"].values else 0
            avg = int(p_gbg["Fights"].mean())
            pct = round((this - avg) / max(avg, 1) * 100, 1)
            direction = "above" if pct >= 0 else "below"
            col = "#2ECC71" if pct >= 0 else "#E74C3C"
            cards.append({
                "type": "personal",
                "icon": "👤",
                "title": f"Your latest season, {current_user}",
                "body": f"{this:,} fights — {abs(pct)}% {direction} your average of {avg:,}.",
                "colour": col,
            })

    return cards


# ── Points system ──────────────────────────────────────────────────────────

POINTS_RULES = {
    "question":          10,
    "daily_first":       20,
    "about_player":       5,
    "session_5":         25,
    "first_ever":        50,
}

BADGES = [
    {"id": "first_contact",  "name": "First Contact",  "icon": "🤖", "desc": "Asked your first question",          "bg": "#2A1A1A", "col": "#E74C3C", "req_questions": 1},
    {"id": "curious_mind",   "name": "Curious Mind",   "icon": "💬", "desc": "Asked 10 questions",                 "bg": "#1A2A1A", "col": "#2ECC71", "req_questions": 10},
    {"id": "data_analyst",   "name": "Data Analyst",   "icon": "🔍", "desc": "Asked 50 questions",                 "bg": "#1A2A2A", "col": "#4A90D9", "req_questions": 50},
    {"id": "ai_skilled",     "name": "AI Skilled",     "icon": "🧠", "desc": "Asked 100 questions",                "bg": "#1A1A2A", "col": "#9B59B6", "req_questions": 100},
    {"id": "ai_master",      "name": "AI Master",      "icon": "👑", "desc": "Asked 250 questions",                "bg": "#2A2010", "col": "#FFD700", "req_questions": 250},
    {"id": "stats_obsessed", "name": "Stats Obsessed", "icon": "📊", "desc": "Asked about 10 different players",   "bg": "#2A1A2A", "col": "#E67E22", "req_players": 10},
    {"id": "guild_scholar",  "name": "Guild Scholar",  "icon": "🏆", "desc": "Asked on 7 different days",          "bg": "#1A2A2A", "col": "#3498DB", "req_days": 7},
    {"id": "power_user",     "name": "Power User",     "icon": "⚡", "desc": "5 questions in one session",         "bg": "#2A2A1A", "col": "#F39C12", "req_session": 5},
]

def get_earned_badges(total_questions: int, unique_players: int, unique_days: int, session_count: int) -> list[dict]:
    earned = []
    for b in BADGES:
        if b.get("req_questions") and total_questions >= b["req_questions"]:
            earned.append(b)
        elif b.get("req_players") and unique_players >= b["req_players"]:
            earned.append(b)
        elif b.get("req_days") and unique_days >= b["req_days"]:
            earned.append(b)
        elif b.get("req_session") and session_count >= b["req_session"]:
            earned.append(b)
    return earned

def get_next_badge(total_questions: int, unique_players: int, unique_days: int) -> dict | None:
    for b in BADGES:
        if b.get("req_questions") and total_questions < b["req_questions"]:
            return {**b, "progress": total_questions, "target": b["req_questions"], "label": f"{total_questions}/{b['req_questions']} questions"}
        elif b.get("req_players") and unique_players < b["req_players"]:
            return {**b, "progress": unique_players, "target": b["req_players"], "label": f"{unique_players}/{b['req_players']} players asked about"}
        elif b.get("req_days") and unique_days < b["req_days"]:
            return {**b, "progress": unique_days, "target": b["req_days"], "label": f"{unique_days}/{b['req_days']} days"}
    return None


# ── API call ───────────────────────────────────────────────────────────────

def ask_snuggy_bug(
    question: str,
    context: str,
    history: list[dict],
    current_user: str = None,
) -> str:
    """Send question + context to Claude Haiku and return the answer."""
    try:
        import anthropic
        client = anthropic.Anthropic()

        messages = []
        for h in history[-6:]:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": question})

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=context,
            messages=messages,
        )
        return response.content[0].text if response.content else "Sorry, I couldn't find an answer in the guild data."
    except Exception as e:
        return f"Snuggy Bug hit a snag: {str(e)}"
