"""
gbg_analysis.py - GBG-specific analytics
"""

import pandas as pd
from modules.comparisons import sort_seasons


def get_leaderboard(df: pd.DataFrame, season: str = None, sort_by: str = "Total") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    if season:
        data = df[df["season"] == season].copy()
    else:
        seasons = sort_seasons(df["season"].unique().tolist())
        data = df[df["season"] == seasons[-1]].copy() if seasons else df.copy()

    data = data.sort_values(sort_by, ascending=False).reset_index(drop=True)
    data.index = data.index + 1
    return data[["Player", "Fights", "Negotiations", "Total", "season"]]


def get_guild_totals_by_season(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    seasons = sort_seasons(df["season"].unique().tolist())
    rows = []
    for s in seasons:
        sdf = df[df["season"] == s]
        rows.append({
            "season": s,
            "total_fights": int(sdf["Fights"].sum()),
            "total_negotiations": int(sdf["Negotiations"].sum()),
            "total_contribution": int(sdf["Total"].sum()),
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
    return data.nlargest(n, "Total")[["Player", "Total", "Fights", "Negotiations"]].reset_index(drop=True)


def get_cumulative_fights(df: pd.DataFrame) -> pd.DataFrame:
    """Cumulative fights per player across all seasons."""
    if df.empty:
        return pd.DataFrame()
    return (df.groupby(["Player_ID", "Player"])["Fights"]
              .sum()
              .reset_index()
              .rename(columns={"Fights": "cumulative_fights"})
              .sort_values("cumulative_fights", ascending=False))


def player_gbg_history(df: pd.DataFrame, player_id: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    pdata = df[df["Player_ID"].astype(str) == str(player_id)].copy()
    if pdata.empty:
        return pd.DataFrame()
    seasons = sort_seasons(pdata["season"].unique().tolist())
    pdata["season_order"] = pdata["season"].map({s: i for i, s in enumerate(seasons)})
    return pdata.sort_values("season_order").drop("season_order", axis=1)
