"""
charts.py - Plotly chart builders for Guild Tracker
"""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from modules.comparisons import sort_seasons

# ── Colour palette ──────────────────────────────────────────────────────────
GOLD   = "#FFD700"
SILVER = "#C0C0C0"
BRONZE = "#CD7F32"
BLUE   = "#4A90D9"
GREEN  = "#2ECC71"
RED    = "#E74C3C"
PURPLE = "#9B59B6"
BG     = "#0E1117"
CARD   = "#1A1D27"
TEXT   = "#E8E8E8"

LAYOUT_BASE = dict(
    paper_bgcolor=BG,
    plot_bgcolor=CARD,
    font=dict(color=TEXT, family="Inter, sans-serif"),
    margin=dict(l=40, r=20, t=50, b=40),
    xaxis=dict(gridcolor="#2A2D3A", linecolor="#2A2D3A"),
    yaxis=dict(gridcolor="#2A2D3A", linecolor="#2A2D3A"),
)


def _medal_colors(n: int) -> list[str]:
    colors = [GOLD, SILVER, BRONZE]
    return colors[:min(n, 3)] + [BLUE] * max(0, n - 3)


# ── GBG Charts ────────────────────────────────────────────────────────────

def gbg_fights_leaderboard(df: pd.DataFrame, season: str = None, top_n: int = 20) -> go.Figure:
    if df.empty:
        return go.Figure()
    if season:
        data = df[df["season"] == season]
    else:
        seasons = sort_seasons(df["season"].unique().tolist())
        data = df[df["season"] == seasons[-1]] if seasons else df

    data = data.nlargest(top_n, "Fights").sort_values("Fights")
    colors = _medal_colors(len(data))[::-1]

    fig = go.Figure(go.Bar(
        x=data["Fights"],
        y=data["Player"],
        orientation="h",
        marker=dict(color=colors),
        text=data["Fights"].apply(lambda v: f"{v:,}"),
        textposition="outside",
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text=f"GBG Fights Leaderboard — {data['season'].iloc[-1] if not data.empty else ''}", font=dict(size=16)),
        height=max(400, top_n * 30),
        showlegend=False,
    )
    return fig


def gbg_total_contribution_chart(df: pd.DataFrame, season: str = None, top_n: int = 20) -> go.Figure:
    if df.empty:
        return go.Figure()
    if season:
        data = df[df["season"] == season]
    else:
        seasons = sort_seasons(df["season"].unique().tolist())
        data = df[df["season"] == seasons[-1]] if seasons else df

    data = data.nlargest(top_n, "Total").sort_values("Total", ascending=False)

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Fights", x=data["Player"], y=data["Fights"], marker_color=BLUE))
    fig.add_trace(go.Bar(name="Negotiations", x=data["Player"], y=data["Negotiations"], marker_color=PURPLE))
    fig.update_layout(
        **LAYOUT_BASE,
        barmode="stack",
        title=dict(text="🏆 GBG Total Contribution (Stacked)", font=dict(size=16)),
        height=450,
        legend=dict(bgcolor=CARD, bordercolor="#2A2D3A"),
    )
    return fig


def gbg_guild_trend(totals_df: pd.DataFrame) -> go.Figure:
    if totals_df.empty:
        return go.Figure()
    seasons = sort_seasons(totals_df["season"].unique().tolist())
    data = totals_df.set_index("season").loc[seasons].reset_index()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data["season"], y=data["total_fights"],
        mode="lines+markers+text",
        name="Total Fights",
        line=dict(color=BLUE, width=2),
        marker=dict(size=8),
        text=data["total_fights"].apply(lambda v: f"{v:,}"),
        textposition="top center",
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text="📈 Guild GBG Fights Over Seasons", font=dict(size=16)),
        height=380,
    )
    return fig


def gbg_player_trend(history_df: pd.DataFrame, player_name: str) -> go.Figure:
    if history_df.empty:
        return go.Figure()
    seasons = sort_seasons(history_df["season"].unique().tolist())
    data = history_df.set_index("season").loc[seasons].reset_index()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data["season"], y=data["Fights"],
        mode="lines+markers", name="Fights",
        line=dict(color=BLUE, width=2), marker=dict(size=9),
    ))
    fig.add_trace(go.Scatter(
        x=data["season"], y=data["Total"],
        mode="lines+markers", name="Total",
        line=dict(color=GOLD, width=2, dash="dot"), marker=dict(size=7),
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text=f"{player_name} — GBG Performance", font=dict(size=15)),
        height=350,
        legend=dict(bgcolor=CARD),
    )
    return fig


# ── QI Charts ─────────────────────────────────────────────────────────────

def qi_progress_leaderboard(df: pd.DataFrame, season: str = None, top_n: int = 20) -> go.Figure:
    if df.empty:
        return go.Figure()
    if season:
        data = df[df["season"] == season]
    else:
        seasons = sort_seasons(df["season"].unique().tolist())
        data = df[df["season"] == seasons[-1]] if seasons else df

    data = data.nlargest(top_n, "Progress").sort_values("Progress")
    colors = _medal_colors(len(data))[::-1]

    fig = go.Figure(go.Bar(
        x=data["Progress"],
        y=data["Player"],
        orientation="h",
        marker=dict(color=colors),
        text=data["Progress"].apply(lambda v: f"{v:,}"),
        textposition="outside",
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text=f"QI Progress Leaderboard — {data['season'].iloc[-1] if not data.empty else ''}", font=dict(size=16)),
        height=max(400, top_n * 30),
        showlegend=False,
    )
    return fig


def qi_guild_trend(totals_df: pd.DataFrame) -> go.Figure:
    if totals_df.empty:
        return go.Figure()
    seasons = sort_seasons(totals_df["season"].unique().tolist())
    data = totals_df.set_index("season").loc[seasons].reset_index()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data["season"], y=data["total_progress"],
        mode="lines+markers+text", name="Total Progress",
        line=dict(color=PURPLE, width=2), marker=dict(size=8),
        text=data["total_progress"].apply(lambda v: f"{v:,}"),
        textposition="top center",
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text="📈 Guild QI Progress Over Seasons", font=dict(size=16)),
        height=380,
    )
    return fig


def qi_player_trend(history_df: pd.DataFrame, player_name: str) -> go.Figure:
    if history_df.empty:
        return go.Figure()
    seasons = sort_seasons(history_df["season"].unique().tolist())
    data = history_df.set_index("season").loc[seasons].reset_index()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data["season"], y=data["Progress"],
        mode="lines+markers", name="Progress",
        line=dict(color=PURPLE, width=2), marker=dict(size=9),
    ))
    fig.add_trace(go.Scatter(
        x=data["season"], y=data["Actions"],
        mode="lines+markers", name="Actions",
        line=dict(color=GREEN, width=2, dash="dot"), marker=dict(size=7),
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text=f"{player_name} — QI Performance", font=dict(size=15)),
        height=350,
        legend=dict(bgcolor=CARD),
    )
    return fig


# ── Comparison Charts ──────────────────────────────────────────────────────

def comparison_waterfall(comp_df: pd.DataFrame, metric: str, title: str) -> go.Figure:
    """Show top improvers and decliners as a waterfall/bar."""
    if comp_df.empty:
        return go.Figure()
    col = f"{metric}_change"
    if col not in comp_df.columns:
        return go.Figure()

    data = comp_df.sort_values(col, ascending=False)
    colors = [GREEN if v >= 0 else RED for v in data[col]]

    fig = go.Figure(go.Bar(
        x=data["Player"],
        y=data[col],
        marker=dict(color=colors),
        text=data[col].apply(lambda v: f"+{v:,}" if v >= 0 else f"{v:,}"),
        textposition="outside",
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text=title, font=dict(size=15)),
        height=420,
        showlegend=False,
    )
    return fig


def points_trend_chart(members_df: pd.DataFrame) -> go.Figure:
    """Guild total points across member snapshots."""
    if members_df.empty or "snapshot" not in members_df.columns:
        return go.Figure()
    from modules.comparisons import sort_seasons
    snaps = sort_seasons(members_df["snapshot"].unique().tolist())
    totals = [
        {"snapshot": s, "total_points": int(members_df[members_df["snapshot"] == s]["points"].sum())}
        for s in snaps
    ]
    import pandas as _pd
    data = _pd.DataFrame(totals)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data["snapshot"], y=data["total_points"],
        mode="lines+markers+text", name="Guild Points",
        line=dict(color=GOLD, width=3), marker=dict(size=10),
        text=data["total_points"].apply(lambda v: f"{v/1e9:.2f}B"),
        textposition="top center",
        fill="tozeroy", fillcolor="rgba(255,215,0,0.08)",
    ))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(color=TEXT, family="Inter, sans-serif"),
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis=dict(gridcolor="#2A2D3A", linecolor="#2A2D3A"),
        yaxis=dict(gridcolor="#2A2D3A", linecolor="#2A2D3A", tickformat=".2s"),
        title=dict(text="📈 Guild Total Points Over Time", font=dict(size=16)),
        height=360,
    )
    return fig


def era_distribution_chart(members_df: pd.DataFrame) -> go.Figure:
    """Pie/donut chart of player era distribution from latest snapshot."""
    if members_df.empty or "eraName" not in members_df.columns:
        return go.Figure()
    from modules.comparisons import sort_seasons
    snaps  = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
    latest = members_df[members_df["snapshot"] == snaps[0]]
    counts = latest["eraName"].value_counts().reset_index()
    counts.columns = ["Era", "Count"]
    colors = [GOLD, BLUE, PURPLE, GREEN, RED, SILVER, BRONZE, "#E67E22", "#1ABC9C", "#F39C12"]
    fig = go.Figure(go.Pie(
        labels=counts["Era"], values=counts["Count"],
        hole=0.55,
        marker=dict(colors=colors[:len(counts)], line=dict(color=BG, width=2)),
        textinfo="label+percent",
        textfont=dict(size=12),
    ))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(color=TEXT, family="Inter, sans-serif"),
        margin=dict(l=20, r=20, t=50, b=20),
        title=dict(text="🌍 Player Era Distribution", font=dict(size=16)),
        height=360,
        showlegend=True,
        legend=dict(bgcolor=CARD, bordercolor="#2A2D3A", font=dict(size=11)),
    )
    return fig


def activity_heatmap(gbg_df: pd.DataFrame) -> go.Figure:
    """Grid heatmap: players (y) × seasons (x), coloured by fights (0 = absent)."""
    if gbg_df.empty:
        return go.Figure()
    from modules.comparisons import sort_seasons
    seasons = sort_seasons(gbg_df["season"].unique().tolist())
    latest_pids = set(gbg_df[gbg_df["season"] == seasons[-1]]["Player_ID"].astype(str))
    df = gbg_df[gbg_df["Player_ID"].astype(str).isin(latest_pids)].copy()

    pivot = df.pivot_table(index="Player", columns="season", values="Fights", aggfunc="sum", fill_value=0)
    pivot = pivot.reindex(columns=seasons, fill_value=0)
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]

    z    = pivot.values.tolist()
    text = [[f"{int(v):,}" if v > 0 else "—" for v in row] for row in pivot.values]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[s[:10] for s in seasons],
        y=pivot.index.tolist(),
        text=text,
        texttemplate="%{text}",
        textfont=dict(size=10),
        colorscale=[[0,"#0E1117"],[0.01,"#1A2A3A"],[0.3,BLUE],[0.7,PURPLE],[1.0,GOLD]],
        showscale=False,
        hoverongaps=False,
        xgap=3, ygap=3,
    ))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(color=TEXT, family="Inter, sans-serif"),
        title=dict(text="🗓️ Player Activity Heatmap (GBG Fights)", font=dict(size=16)),
        height=max(300, len(pivot) * 28 + 80),
        xaxis=dict(side="top", tickangle=-30, gridcolor="rgba(0,0,0,0)", linecolor="#2A2D3A"),
        yaxis=dict(gridcolor="rgba(0,0,0,0)", linecolor="#2A2D3A"),
        margin=dict(l=120, r=20, t=80, b=20),
    )
    return fig
