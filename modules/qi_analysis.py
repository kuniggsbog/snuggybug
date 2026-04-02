"""
qi_analysis.py - QI-specific analytics
"""

import pandas as pd
from modules.comparisons import sort_seasons


def get_leaderboard(df: pd.DataFrame, season: str = None, sort_by: str = "Progress") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    if season:
        data = df[df["season"] == season].copy()
    else:
        seasons = sort_seasons(df["season"].unique().tolist())
        data = df[df["season"] == seasons[-1]].copy() if seasons else df.copy()

    data = data.sort_values(sort_by, ascending=False).reset_index(drop=True)
    data.index = data.index + 1
    return data[["Player", "Actions", "Progress", "season"]]


def get_guild_totals_by_season(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    seasons = sort_seasons(df["season"].unique().tolist())
    rows = []
    for s in seasons:
        sdf = df[df["season"] == s]
        rows.append({
            "season": s,
            "total_actions": int(sdf["Actions"].sum()),
            "total_progress": int(sdf["Progress"].sum()),
            "player_count": len(sdf),
        })
    return pd.DataFrame(rows)


def get_top_contributors(df: pd.DataFrame, season: str = None, n: int = 10) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    if season:
        data = df[df["season"] == season]
    else:
        seasons = sort_seasons(df["season"].unique().tolist())
        data = df[df["season"] == seasons[-1]] if seasons else df
    return data.nlargest(n, "Progress")[["Player", "Progress", "Actions"]].reset_index(drop=True)


def get_cumulative_progress(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return (df.groupby(["Player_ID", "Player"])["Progress"]
              .sum()
              .reset_index()
              .rename(columns={"Progress": "cumulative_progress"})
              .sort_values("cumulative_progress", ascending=False))


def player_qi_history(df: pd.DataFrame, player_id: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    pdata = df[df["Player_ID"].astype(str) == str(player_id)].copy()
    if pdata.empty:
        return pd.DataFrame()
    seasons = sort_seasons(pdata["season"].unique().tolist())
    pdata["season_order"] = pdata["season"].map({s: i for i, s in enumerate(seasons)})
    return pdata.sort_values("season_order").drop("season_order", axis=1)
