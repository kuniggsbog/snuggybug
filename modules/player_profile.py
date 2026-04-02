"""
player_profile.py - Player profile aggregation with former-member detection
"""

import pandas as pd
from modules.comparisons import sort_seasons, compute_change, format_change
from modules.gbg_analysis import player_gbg_history
from modules.qi_analysis import player_qi_history


def get_latest_member_stats(members_df: pd.DataFrame, player_id: str) -> dict:
    """Return the most recent member snapshot stats for a player."""
    if members_df.empty:
        return {}
    pid_rows = members_df[members_df["Player_ID"].astype(str) == str(player_id)]
    if pid_rows.empty:
        return {}
    snaps = sort_seasons(pid_rows["snapshot"].unique().tolist(), descending=True)
    latest = pid_rows[pid_rows["snapshot"] == snaps[0]].iloc[0]
    return {
        "points":      int(latest.get("points", 0)),
        "eraName":     str(latest.get("eraName", "—")),
        "guildgoods":  int(latest.get("guildgoods", 0)),
        "won_battles": int(latest.get("won_battles", 0)),
        "rank":        int(latest.get("rank", 0)),
        "snapshot":    snaps[0],
    }


def get_player_wins(gbg_df: pd.DataFrame, qi_df: pd.DataFrame, player_id: str) -> dict:
    """
    Count how many seasons a player finished #1 on:
    - GBG: most Fights in that season
    - QI:  most Progress in that season
    Returns dict with gbg_wins and qi_wins counts.
    """
    pid = str(player_id)
    gbg_wins = 0
    qi_wins  = 0

    if not gbg_df.empty and "Fights" in gbg_df.columns:
        for season in gbg_df["season"].unique():
            sdf = gbg_df[gbg_df["season"] == season]
            if sdf.empty:
                continue
            top_pid = sdf.loc[sdf["Fights"].idxmax(), "Player_ID"]
            if str(top_pid) == pid:
                gbg_wins += 1

    if not qi_df.empty and "Progress" in qi_df.columns:
        for season in qi_df["season"].unique():
            sdf = qi_df[qi_df["season"] == season]
            if sdf.empty:
                continue
            top_pid = sdf.loc[sdf["Progress"].idxmax(), "Player_ID"]
            if str(top_pid) == pid:
                qi_wins += 1

    return {"gbg_wins": gbg_wins, "qi_wins": qi_wins}


def get_all_season_winners(gbg_df: pd.DataFrame, qi_df: pd.DataFrame) -> pd.DataFrame:
    """
    For every player, count GBG fight wins and QI progress wins across all seasons.
    Used to display medal counts on player cards.
    """
    rows = {}

    if not gbg_df.empty and "Fights" in gbg_df.columns:
        for season in gbg_df["season"].unique():
            sdf = gbg_df[gbg_df["season"] == season]
            if sdf.empty:
                continue
            top_pid = str(sdf.loc[sdf["Fights"].idxmax(), "Player_ID"])
            rows.setdefault(top_pid, {"gbg_wins": 0, "qi_wins": 0})
            rows[top_pid]["gbg_wins"] += 1

    if not qi_df.empty and "Progress" in qi_df.columns:
        for season in qi_df["season"].unique():
            sdf = qi_df[qi_df["season"] == season]
            if sdf.empty:
                continue
            top_pid = str(sdf.loc[sdf["Progress"].idxmax(), "Player_ID"])
            rows.setdefault(top_pid, {"gbg_wins": 0, "qi_wins": 0})
            rows[top_pid]["qi_wins"] += 1

    if not rows:
        return pd.DataFrame(columns=["Player_ID", "gbg_wins", "qi_wins"])

    result = pd.DataFrame([
        {"Player_ID": pid, **vals} for pid, vals in rows.items()
    ])
    return result


def get_all_players(gbg_df: pd.DataFrame, qi_df: pd.DataFrame, members_df: pd.DataFrame = None) -> dict:
    """
    Return current and former player lists.
    If members_df provided, current players are sorted by points descending.
    """
    latest_pids = set()

    for df in [gbg_df, qi_df]:
        if not df.empty:
            seasons = sort_seasons(df["season"].unique().tolist())
            latest_season = seasons[-1]
            pids = df[df["season"] == latest_season]["Player_ID"].astype(str).tolist()
            latest_pids.update(pids)

    # Also consider players in latest member snapshot as current
    if members_df is not None and not members_df.empty:
        snaps = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
        latest_snap_pids = members_df[members_df["snapshot"] == snaps[0]]["Player_ID"].astype(str).tolist()
        latest_pids.update(latest_snap_pids)

    all_rows = []
    for df in [gbg_df, qi_df]:
        if not df.empty:
            all_rows.append(df[["Player_ID", "Player"]].drop_duplicates())
    if members_df is not None and not members_df.empty:
        mem_cols = members_df[["Player_ID", "Player"]].drop_duplicates()
        all_rows.append(mem_cols)

    if not all_rows:
        return {"current": pd.DataFrame(columns=["Player_ID", "Player"]),
                "former":  pd.DataFrame(columns=["Player_ID", "Player"])}

    # Combine all sources, keep first occurrence per Player_ID
    combined = pd.concat(all_rows, ignore_index=True)
    combined["Player_ID"] = combined["Player_ID"].astype(str)
    combined["Player"]    = combined["Player"].astype(str).str.strip()

    # Build a name map: prefer member snapshot name as most up-to-date
    name_map = {}
    # First pass — GBG/QI names
    for df in [gbg_df, qi_df]:
        if not df.empty:
            for _, r in df[["Player_ID","Player"]].drop_duplicates().iterrows():
                name_map[str(r["Player_ID"])] = str(r["Player"]).strip()
    # Second pass — member snapshot overrides (most authoritative)
    if members_df is not None and not members_df.empty:
        snaps = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
        latest_mem_names = members_df[members_df["snapshot"] == snaps[0]][["Player_ID","Player"]].drop_duplicates()
        for _, r in latest_mem_names.iterrows():
            name_map[str(r["Player_ID"])] = str(r["Player"]).strip()

    # Apply name map
    all_pids = combined["Player_ID"].unique()
    combined = pd.DataFrame({
        "Player_ID": all_pids,
        "Player":    [name_map.get(str(pid), str(pid)) for pid in all_pids]
    })

    current = combined[combined["Player_ID"].isin(latest_pids)].copy()
    former  = combined[~combined["Player_ID"].isin(latest_pids)].copy()

    # Sort current players by points descending if member data available
    if members_df is not None and not members_df.empty and not current.empty:
        snaps = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
        latest_mem = members_df[members_df["snapshot"] == snaps[0]][["Player_ID", "points"]].copy()
        latest_mem["Player_ID"] = latest_mem["Player_ID"].astype(str)
        current = current.merge(latest_mem, on="Player_ID", how="left")
        current["points"] = pd.to_numeric(current["points"], errors="coerce").fillna(0)
        current = current.sort_values("points", ascending=False).drop(columns=["points"])
    else:
        current = current.sort_values("Player")

    former = former.sort_values("Player").reset_index(drop=True)
    current = current.reset_index(drop=True)

    return {"current": current, "former": former}


def get_player_profile(player_id: str, gbg_df: pd.DataFrame, qi_df: pd.DataFrame,
                       members_df: pd.DataFrame = None) -> dict:
    """Build a full profile dict for a given player_id."""
    pid = str(player_id)

    gbg_hist = player_gbg_history(gbg_df, pid)
    qi_hist  = player_qi_history(qi_df, pid)

    player_name = "Unknown"
    if not gbg_hist.empty:
        player_name = gbg_hist["Player"].iloc[-1]
    elif not qi_hist.empty:
        player_name = qi_hist["Player"].iloc[-1]
    elif members_df is not None and not members_df.empty:
        _mem_row = members_df[members_df["Player_ID"].astype(str) == pid]
        if not _mem_row.empty:
            player_name = str(_mem_row["Player"].iloc[0])

    # Determine if former member
    is_former = True
    for df in [gbg_df, qi_df]:
        if not df.empty:
            seasons = sort_seasons(df["season"].unique().tolist())
            latest = seasons[-1]
            if pid in df[df["season"] == latest]["Player_ID"].astype(str).values:
                is_former = False
                break
    # Also check latest member snapshot — if present there, they are current
    if is_former and members_df is not None and not members_df.empty:
        snaps = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
        latest_snap_pids = members_df[members_df["snapshot"] == snaps[0]]["Player_ID"].astype(str).values
        if pid in latest_snap_pids:
            is_former = False

    profile = {
        "player_id":    pid,
        "player_name":  player_name,
        "is_former":    is_former,
        "gbg_history":  gbg_hist,
        "qi_history":   qi_hist,
        "gbg_changes":  {},
        "qi_changes":   {},
        "member_stats": get_latest_member_stats(members_df, pid) if members_df is not None else {},
        "wins":         get_player_wins(gbg_df, qi_df, pid),
    }

    if len(gbg_hist) >= 2:
        latest = gbg_hist.iloc[-1]
        prev   = gbg_hist.iloc[-2]
        for col in ["Fights", "Negotiations", "Total"]:
            delta, pct = compute_change(latest[col], prev[col])
            profile["gbg_changes"][col] = {
                "current": int(latest[col]),
                "previous": int(prev[col]),
                "delta": int(delta),
                "pct": pct,
                "formatted": format_change(delta, pct),
                "positive": delta >= 0,
            }
        profile["gbg_changes"]["season_current"]  = latest["season"]
        profile["gbg_changes"]["season_previous"] = prev["season"]

    if len(qi_hist) >= 2:
        latest = qi_hist.iloc[-1]
        prev   = qi_hist.iloc[-2]
        for col in ["Actions", "Progress"]:
            delta, pct = compute_change(latest[col], prev[col])
            profile["qi_changes"][col] = {
                "current": int(latest[col]),
                "previous": int(prev[col]),
                "delta": int(delta),
                "pct": pct,
                "formatted": format_change(delta, pct),
                "positive": delta >= 0,
            }
        profile["qi_changes"]["season_current"]  = latest["season"]
        profile["qi_changes"]["season_previous"] = prev["season"]

    return profile


def get_most_consistent_players(gbg_df: pd.DataFrame, qi_df: pd.DataFrame, section: str = "GBG") -> pd.DataFrame:
    """
    Rank CURRENT players by veteran-weighted score: avg_per_season × log(seasons).
    Former players (not in latest season of either GBG or QI) are excluded.
    """
    import math

    df     = gbg_df if section == "GBG" else qi_df
    metric = "Fights" if section == "GBG" else "Progress"
    label  = "Avg Fights / Season" if section == "GBG" else "Avg Progress / Season"

    if df.empty or metric not in df.columns:
        return pd.DataFrame()

    # ── Build set of current player IDs (in latest season of either section) ──
    current_pids = set()
    for src in [gbg_df, qi_df]:
        if not src.empty and "season" in src.columns:
            seasons = sort_seasons(src["season"].unique().tolist())
            latest  = seasons[-1]
            pids    = src[src["season"] == latest]["Player_ID"].astype(str).tolist()
            current_pids.update(pids)

    # Filter df to current players only
    df = df[df["Player_ID"].astype(str).isin(current_pids)]
    if df.empty:
        return pd.DataFrame()

    grouped = (
        df.groupby(["Player_ID", "Player"])[metric]
        .agg(seasons="count", total="sum")
        .reset_index()
    )
    grouped["avg_per_season"] = (grouped["total"] / grouped["seasons"]).round(0).astype(int)
    grouped["score"] = grouped.apply(
        lambda r: r["avg_per_season"] * math.log(max(r["seasons"], 1)), axis=1
    ).round(0).astype(int)

    grouped = grouped.sort_values("score", ascending=False).head(10).reset_index(drop=True)
    grouped.index = grouped.index + 1

    grouped["avg_per_season"] = grouped["avg_per_season"].apply(lambda v: f"{v:,}")
    grouped["score"]          = grouped["score"].apply(lambda v: f"{v:,}")

    return grouped[["Player", "seasons", "avg_per_season", "score"]].rename(columns={
        "seasons":        "Seasons",
        "avg_per_season": label,
        "score":          "⭐ Score",
    })

def _current_pids(gbg_df: pd.DataFrame, qi_df: pd.DataFrame) -> set:
    """Return set of Player_IDs present in the latest season of either GBG or QI."""
    pids = set()
    for df in [gbg_df, qi_df]:
        if not df.empty and "season" in df.columns:
            latest = sort_seasons(df["season"].unique().tolist())[-1]
            pids.update(df[df["season"] == latest]["Player_ID"].astype(str).tolist())
    return pids


def get_hall_of_fame(gbg_df: pd.DataFrame, qi_df: pd.DataFrame) -> list[dict]:
    """
    All-time #1 finishers — current players only — sorted by total medals.
    Returns list of dicts for card rendering.
    """
    current = _current_pids(gbg_df, qi_df)
    wins    = get_all_season_winners(gbg_df, qi_df)
    if wins.empty:
        return []

    names = {}
    for df in [gbg_df, qi_df]:
        if not df.empty:
            for _, r in df[["Player_ID", "Player"]].drop_duplicates().iterrows():
                names[str(r["Player_ID"])] = r["Player"]

    rows = []
    for _, r in wins.iterrows():
        pid = str(r["Player_ID"])
        if pid not in current:
            continue
        total = int(r["gbg_wins"]) + int(r["qi_wins"])
        if total == 0:
            continue
        rows.append({
            "pid":      pid,
            "player":   names.get(pid, "Unknown"),
            "gbg_wins": int(r["gbg_wins"]),
            "qi_wins":  int(r["qi_wins"]),
            "total":    total,
        })

    return sorted(rows, key=lambda x: x["total"], reverse=True)


def get_active_streak(gbg_df: pd.DataFrame, qi_df: pd.DataFrame) -> list[dict]:
    """
    Longest consecutive GBG season streak — current players only.
    Returns list of dicts for card rendering.
    """
    if gbg_df.empty:
        return []

    seasons      = sort_seasons(gbg_df["season"].unique().tolist())
    current      = _current_pids(gbg_df, qi_df)
    results      = []

    for pid in current:
        pid_rows = gbg_df[gbg_df["Player_ID"].astype(str) == pid]
        if pid_rows.empty:
            continue
        name           = pid_rows["Player"].iloc[0]
        player_seasons = set(pid_rows["season"].tolist())
        streak = 0
        for s in reversed(seasons):
            if s in player_seasons:
                streak += 1
            else:
                break
        results.append({
            "player":        name,
            "streak":        streak,
            "total_seasons": len(player_seasons),
        })

    return sorted(results, key=lambda x: x["streak"], reverse=True)[:10]


def get_newcomers(gbg_df: pd.DataFrame, qi_df: pd.DataFrame) -> list[dict]:
    """
    Players in their first ever season (latest season only) — returns list of dicts.
    """
    newcomers = {}
    for df, section in [(gbg_df, "GBG"), (qi_df, "QI")]:
        if df.empty:
            continue
        seasons = sort_seasons(df["season"].unique().tolist())
        if len(seasons) < 2:
            continue
        latest    = seasons[-1]
        prev_pids = set(df[df["season"] != latest]["Player_ID"].astype(str))
        for _, r in df[df["season"] == latest].iterrows():
            pid = str(r["Player_ID"])
            if pid not in prev_pids:
                if pid not in newcomers:
                    newcomers[pid] = {"player": r["Player"], "sections": []}
                newcomers[pid]["sections"].append(section)

    return list(newcomers.values())


def get_most_improved(gbg_df: pd.DataFrame, qi_df: pd.DataFrame) -> dict:
    """
    Most improved and biggest drop-off players between latest two GBG seasons.
    Current players only. Returns dict with 'best' and 'worst' entries.
    """
    result = {"best": None, "worst": None}
    if gbg_df.empty:
        return result

    seasons = sort_seasons(gbg_df["season"].unique().tolist())
    if len(seasons) < 2:
        return result

    current  = _current_pids(gbg_df, qi_df)
    curr_s   = seasons[-1]
    prev_s   = seasons[-2]
    curr_df  = gbg_df[gbg_df["season"] == curr_s][["Player_ID", "Player", "Fights"]]
    prev_df  = gbg_df[gbg_df["season"] == prev_s][["Player_ID", "Fights"]].rename(columns={"Fights": "prev_Fights"})
    merged   = curr_df.merge(prev_df, on="Player_ID")
    merged   = merged[merged["Player_ID"].astype(str).isin(current)]
    if merged.empty:
        return result

    merged["delta"] = merged["Fights"] - merged["prev_Fights"]
    merged["pct"]   = ((merged["delta"] / merged["prev_Fights"].replace(0, 1)) * 100).round(1)

    best  = merged.loc[merged["delta"].idxmax()]
    worst = merged.loc[merged["delta"].idxmin()]

    result["best"]  = {"player": best["Player"],  "delta": int(best["delta"]),  "pct": float(best["pct"]),  "curr": int(best["Fights"]),  "seasons": f"{prev_s} → {curr_s}"}
    result["worst"] = {"player": worst["Player"], "delta": int(worst["delta"]), "pct": float(worst["pct"]), "curr": int(worst["Fights"]), "seasons": f"{prev_s} → {curr_s}"}
    return result


def get_guild_health(gbg_df: pd.DataFrame, qi_df: pd.DataFrame, members_df: pd.DataFrame) -> dict:
    """Compute guild health indicators for the latest season."""
    health = {}

    if not gbg_df.empty and not members_df.empty:
        seasons = sort_seasons(gbg_df["season"].unique().tolist())
        latest  = seasons[-1]
        gbg_players   = gbg_df[gbg_df["season"] == latest]["Player_ID"].nunique()
        mem_snaps     = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
        total_members = members_df[members_df["snapshot"] == mem_snaps[0]]["Player_ID"].nunique()
        health["gbg_participation"] = round(gbg_players / total_members * 100) if total_members else 0
        health["gbg_players"]       = gbg_players
        health["total_members"]     = total_members
        health["latest_gbg_season"] = latest

    if not gbg_df.empty:
        seasons   = sort_seasons(gbg_df["season"].unique().tolist())
        latest    = seasons[-1]
        latest_df = gbg_df[gbg_df["season"] == latest]
        zero      = latest_df[latest_df["Fights"] == 0]
        health["inactive_count"]   = len(zero)
        health["inactive_players"] = zero["Player"].tolist()

    if not members_df.empty and "guildgoods" in members_df.columns:
        snaps        = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
        latest_goods = int(members_df[members_df["snapshot"] == snaps[0]]["guildgoods"].sum())
        health["total_goods_latest"] = latest_goods
        if len(snaps) >= 2:
            prev_goods = int(members_df[members_df["snapshot"] == snaps[1]]["guildgoods"].sum())
            health["goods_delta"] = latest_goods - prev_goods
        else:
            health["goods_delta"] = None

    return health


def get_points_leaderboard(members_df: pd.DataFrame, gbg_df: pd.DataFrame, qi_df: pd.DataFrame) -> list[dict]:
    """Top current players ranked by points from latest member snapshot."""
    if members_df.empty or "points" not in members_df.columns:
        return []
    current = _current_pids(gbg_df, qi_df)
    snaps   = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
    latest  = members_df[members_df["snapshot"] == snaps[0]]
    rows = []
    for _, r in latest.iterrows():
        pid = str(r["Player_ID"])
        if pid not in current:
            continue
        rows.append({
            "pid":      pid,
            "player":   r["Player"],
            "points":   int(r.get("points", 0)),
            "eraName":  str(r.get("eraName", "—")),
            "rank":     int(r.get("rank", 0)),
        })
    return sorted(rows, key=lambda x: x["points"], reverse=True)[:10]


def get_goods_leaderboard(members_df: pd.DataFrame, gbg_df: pd.DataFrame, qi_df: pd.DataFrame) -> list[dict]:
    """Top current players by daily guild goods donation from latest snapshot."""
    if members_df.empty or "guildgoods" not in members_df.columns:
        return []
    current = _current_pids(gbg_df, qi_df)
    snaps   = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
    latest  = members_df[members_df["snapshot"] == snaps[0]]
    rows = []
    for _, r in latest.iterrows():
        pid = str(r["Player_ID"])
        if pid not in current:
            continue
        rows.append({
            "pid":       pid,
            "player":    r["Player"],
            "guildgoods": int(r.get("guildgoods", 0)),
            "eraName":   str(r.get("eraName", "—")),
        })
    return sorted(rows, key=lambda x: x["guildgoods"], reverse=True)[:10]


def get_battles_leaderboard(members_df: pd.DataFrame, gbg_df: pd.DataFrame, qi_df: pd.DataFrame) -> list[dict]:
    """Top current players by all-time won battles from latest snapshot."""
    if members_df.empty or "won_battles" not in members_df.columns:
        return []
    current = _current_pids(gbg_df, qi_df)
    snaps   = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
    latest  = members_df[members_df["snapshot"] == snaps[0]]
    rows = []
    for _, r in latest.iterrows():
        pid = str(r["Player_ID"])
        if pid not in current:
            continue
        rows.append({
            "pid":         pid,
            "player":      r["Player"],
            "won_battles": int(r.get("won_battles", 0)),
            "eraName":     str(r.get("eraName", "—")),
        })
    return sorted(rows, key=lambda x: x["won_battles"], reverse=True)[:10]
