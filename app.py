"""
app.py - Guild Statistics Tracker for Forge of Empires
"""

import streamlit as st
import streamlit.components.v1 as _components
import pandas as pd
import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from modules.importer import (
    import_gbg, import_qi, import_members,
    get_gbg_df, get_qi_df, get_members_df, get_member_snapshots,
    get_all_seasons, delete_season, get_guild_stats_df,
)
from modules.gbg_analysis import (
    get_leaderboard as gbg_leaderboard,
    get_guild_totals_by_season as gbg_totals,
    get_top_contributors as gbg_top,
    get_cumulative_fights,
)
from modules.qi_analysis import (
    get_leaderboard as qi_leaderboard,
    get_guild_totals_by_season as qi_totals,
    get_top_contributors as qi_top,
    get_cumulative_progress,
)
from modules.player_profile import (
    get_all_players, get_player_profile, get_most_consistent_players,
    get_latest_member_stats, get_all_season_winners,
    get_hall_of_fame, get_guild_health, get_active_streak, get_newcomers, get_most_improved,
    get_points_leaderboard, get_goods_leaderboard, get_battles_leaderboard,
)
from modules.comparisons import (
    gbg_season_comparison, qi_season_comparison,
    detect_player_status, most_improved_gbg, most_improved_qi, sort_seasons,
)
from modules.charts import (
    gbg_fights_leaderboard, gbg_total_contribution_chart, gbg_guild_trend, gbg_player_trend,
    qi_progress_leaderboard, qi_guild_trend, qi_player_trend, comparison_waterfall,
    points_trend_chart, era_distribution_chart, activity_heatmap,
)
from modules.activity import log_event, load_log, get_last_seen, get_page_stats, get_h2h_stats, get_profile_views
from modules.competitions import (
    list_competitions, get_competition, save_competition, delete_competition,
    list_snapshots, save_snapshot, load_latest_snapshot, load_previous_snapshot,
    get_fp_projections, get_momentum, get_forecast, calc_fp, COMP_DIR
)
from modules.snuggy_bug import (
    build_guild_context, build_proactive_briefing,
    ask_snuggy_bug, get_earned_badges, get_next_badge,
    save_badges, load_player_badges, CONTEXT_VERSION,
    BADGES, POINTS_RULES
)

# ── Constants ──────────────────────────────────────────────────────────────
AVATAR_DIR  = Path("assets/avatars")
ICON_DIR    = Path("assets/icons")
IMPORT_PASS = os.environ.get("IMPORT_PASSWORD", "guild2024")  # set via Streamlit secrets or env


# ── Page config ────────────────────────────────────────────────────────────
from PIL import Image as _PIL_Image
_favicon_path = Path("assets/icons/flag_icon.png")
_favicon = _PIL_Image.open(_favicon_path) if _favicon_path.exists() else "🏴"
st.set_page_config(
    page_title="NEXUS GI (v1.1)",
    page_icon=_favicon,
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Landing-page gate ────────────────────────────────────────────────────
if not st.session_state.get("unlocked", False):
    try:
        _landing_pw = st.secrets["PASSWORD"]
    except (KeyError, FileNotFoundError):
        st.error('Missing secret **PASSWORD**. Add `PASSWORD = "your-password"` to `.streamlit/secrets.toml`.')
        st.stop()

    st.markdown(
        """
        <style>
            [data-testid="stSidebar"] {display:none}
            [data-testid="stSidebarCollapsedControl"] {display:none}
            header {display:none}
            #MainMenu {display:none}
            footer {display:none}
            [data-testid="stDecoration"] {display:none}
            .block-container {
                display:flex; flex-direction:column;
                align-items:center; justify-content:center;
                min-height:100vh; padding-top:0; padding-bottom:0;
            }
            /* invisible password input covering the viewport */
            div[data-testid="stTextInput"] {
                position:fixed !important;
                top:0; left:0;
                width:100vw !important;
                height:100vh !important;
                z-index:9999;
                opacity:0;
            }
            div[data-testid="stTextInput"] input {
                width:100% !important;
                height:100% !important;
                position:absolute !important;
                top:0; left:0;
                cursor:default !important;
                -webkit-user-select:none !important;
                user-select:none !important;
            }
            body { -webkit-user-select:none; user-select:none; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _landing_img_path = Path("wondering_kun.png")

    if _landing_img_path.exists():
        _li_b64 = base64.b64encode(_landing_img_path.read_bytes()).decode()
        st.markdown(
            f'<div style="text-align:center"><img src="data:image/png;base64,{_li_b64}" style="max-width:500px;width:100%"></div>',
            unsafe_allow_html=True,
        )

    _pw_attempt = st.text_input(" ", label_visibility="collapsed", key="_q")
    if _pw_attempt == _landing_pw:
        st.session_state.unlocked = True
        st.rerun()

    _components.html("""<script>
    window.parent.document.addEventListener("contextmenu", function(e){ e.preventDefault(); });
    </script>""", height=0)

    st.stop()


# ── Icon helpers ───────────────────────────────────────────────────────────
def _img_to_b64(path: Path) -> str:
    if path.exists():
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""

def icon_html(filename: str, size: int = 22) -> str:
    b64 = _img_to_b64(ICON_DIR / filename)
    if b64:
        ext  = filename.rsplit(".", 1)[-1].lower()
        mime = "image/webp" if ext == "webp" else "image/svg+xml" if ext == "svg" else "image/png"
        return f'<img src="data:{mime};base64,{b64}" width="{size}" height="{size}" style="vertical-align:middle;">'
    return ""

def gbg_icon(size=22):  return icon_html("GBG_flag.png", size)
def qi_icon(size=22):   return icon_html("QI_fist.png", size)
def flag_icon(size=22): return icon_html("flag_icon.png", size)


# ── Avatar helper ──────────────────────────────────────────────────────────
def get_avatar_html(player_name, size: int = 56) -> str:
    """Return <img> if player_name.jpg exists, else styled initials div. Rectangular shape."""
    player_name = str(player_name) if player_name and str(player_name) != "nan" else "?"
    safe_name = player_name.strip() or "?"
    jpg_path = AVATAR_DIR / f"{safe_name}.jpg"
    png_path = AVATAR_DIR / f"{safe_name}.png"

    # Rectangular dimensions — slightly wider than tall, like a game card
    w = int(size * 1.0)
    h = int(size * 1.2)

    for path in [jpg_path, png_path]:
        if path.exists():
            ext = "jpeg" if path.suffix == ".jpg" else "png"
            b64 = _img_to_b64(path)
            return (f'<img src="data:image/{ext};base64,{b64}" '
                    f'width="{w}" height="{h}" '
                    f'style="border-radius:6px;object-fit:cover;object-position:top;">')

    initials = "".join(w[0].upper() for w in safe_name.split()[:2]) or "?"
    return (f'<div style="width:{w}px;height:{h}px;border-radius:6px;'
            f'background:linear-gradient(160deg,#4A90D9 0%,#9B59B6 100%);'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-size:{int(size*0.32)}px;font-weight:700;color:white;">'
            f'{initials}</div>')


# ── CSS ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0E1117; }
[data-testid="stSidebar"] { background: #12151E; border-right: 1px solid #2A2D3A; }

.metric-card {
    background: #1A1D27; border: 1px solid #2A2D3A;
    border-radius: 12px; padding: 18px 22px; margin-bottom: 12px;
}
.metric-label { color: #C8CBD8; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }
.metric-value { color: #E8E8E8; font-size: 1.9rem; font-weight: 700; margin: 4px 0; }
.metric-change-pos { color: #2ECC71; font-size: 0.88rem; font-weight: 600; }
.metric-change-neg { color: #E74C3C; font-size: 0.88rem; font-weight: 600; }

.player-card {
    background: #1A1D27; border: 1px solid #2A2D3A;
    border-radius: 14px; padding: 18px 20px; margin-bottom: 12px;
}
.player-card-former {
    background: #161820; border: 1px solid #3A2A2A;
    border-radius: 14px; padding: 18px 20px; margin-bottom: 12px;
    opacity: 0.75;
}
.player-name  { color: #E8E8E8; font-size: 1.05rem; font-weight: 700; }
.player-name-former { color: #C8CBD8; font-size: 1.05rem; font-weight: 700; }
.former-badge {
    display:inline-block; background:#3A1A1A; color:#E74C3C;
    padding:2px 10px; border-radius:20px; font-size:0.72rem; font-weight:700;
    margin-left:6px; vertical-align:middle;
}

.badge-gbg { background:#1A3A5C; color:#4A90D9; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:700; }
.badge-qi  { background:#3A1A5C; color:#9B59B6; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:700; }

.profile-hero {
    background: linear-gradient(135deg,#1A1D27 0%,#12151E 100%);
    border: 1px solid #2A2D3A; border-radius:16px; padding:28px; margin-bottom:20px;
}
.profile-name        { color:#E8E8E8; font-size:1.6rem; font-weight:800; margin:0; }
.profile-name-former { color:#C8CBD8; font-size:1.6rem; font-weight:800; margin:0; }

.section-title {
    color:#4A90D9; font-size:1.05rem; font-weight:700;
    border-left:3px solid #4A90D9; padding-left:10px; margin:18px 0 10px;
}
.former-section-header {
    color:#E74C3C; font-size:1rem; font-weight:700; margin:28px 0 10px;
    border-left:3px solid #E74C3C; padding-left:10px;
}

.pill-new       { background:#1A3A1A; color:#2ECC71; padding:2px 10px; border-radius:20px; font-size:0.75rem; }
.pill-returning { background:#3A2A1A; color:#F39C12; padding:2px 10px; border-radius:20px; font-size:0.75rem; }
.pill-missing   { background:#3A1A1A; color:#E74C3C;  padding:2px 10px; border-radius:20px; font-size:0.75rem; }
.pill-active    { background:#1A1D27; color:#C8CBD8;  padding:2px 10px; border-radius:20px; font-size:0.75rem; }

.stButton button {
    background:#4A90D9 !important; color:white !important;
    border:none !important; border-radius:8px !important; font-weight:600 !important;
}

/* Left-align sidebar nav radio buttons */
section[data-testid="stSidebar"] .stRadio > div {
    gap: 2px !important;
}
section[data-testid="stSidebar"] .stRadio label {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    text-align: left !important;
    width: 100% !important;
    padding: 6px 12px !important;
    border-radius: 8px !important;
    cursor: pointer !important;
}
section[data-testid="stSidebar"] .stRadio label > div:first-child {
    display: none !important;
}
section[data-testid="stSidebar"] .stRadio label p {
    text-align: left !important;
    margin: 0 !important;
    font-size: 0.9rem !important;
}
section[data-testid="stSidebar"] .stRadio label:hover {
    background: #2A2D3A !important;
}

/* ── Sidebar nav buttons ────────────────────────────────────────────────── */
[data-testid="stSidebar"] .stButton button {
    background: transparent !important;
    color: #D0D3E0 !important;
    border: 1px solid transparent !important;
    border-radius: 8px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    padding: 9px 14px !important;
    width: 100% !important;
    margin: 1px 0 !important;
    transition: background 0.12s, color 0.12s, border-color 0.12s !important;
}
[data-testid="stSidebar"] .stButton button p {
    text-align: left !important;
    margin: 0 !important;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: #1A1D27 !important;
    color: #E8E8E8 !important;
    border-color: #2A2D3A !important;
}
/* Active state: button immediately after .nav-active-marker div */
[data-testid="stSidebar"] div:has(.nav-active-marker) + div button {
    background: #1E2235 !important;
    color: #E8E8E8 !important;
    border-color: #4A90D9 !important;
    font-weight: 700 !important;
}
/* Hide nav button text — icon and label shown via markdown instead */
section[data-testid="stSidebar"] .stButton button p {
    display: none !important;
}
section[data-testid="stSidebar"] .stButton button {
    position: absolute !important;
    opacity: 0 !important;
    height: 44px !important;
    width: 100% !important;
    top: -44px !important;
    left: 0 !important;
    cursor: pointer !important;
    z-index: 10 !important;
    margin: 0 !important;
    padding: 0 !important;
}
section[data-testid="stSidebar"] .stButton {
    position: relative !important;
    margin-top: -2px !important;
    margin-bottom: 0 !important;
}
</style>
""", unsafe_allow_html=True)


# ── Footer ─────────────────────────────────────────────────────────────────
def _render_footer():
    st.markdown("---")
    st.markdown(
        '<div style="text-align:center;color:#FFFFFF;font-size:0.72rem;padding:8px 0 16px;">'
        '© 2026 Kuniggsbog · NEXUS Guild Intelligence · '
        '<span style="color:#FFFFFF;">nexus-stats.streamlit.app</span>'
        '</div>',
        unsafe_allow_html=True,
    )


# ── Session state ──────────────────────────────────────────────────────────
if "selected_player" not in st.session_state:
    st.session_state.selected_player = None
if "import_authenticated" not in st.session_state:
    st.session_state.import_authenticated = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "name_picker_shown" not in st.session_state:
    st.session_state.name_picker_shown = False

# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    flag_b64        = _img_to_b64(ICON_DIR / "flag_icon.png")
    gbg_b64         = _img_to_b64(ICON_DIR / "GBG_flag.png")
    qi_b64          = _img_to_b64(ICON_DIR / "QI_fist.png")
    profiles_b64    = _img_to_b64(ICON_DIR / "nav_bar_player_profiles_icon.svg")
    h2h_b64         = _img_to_b64(ICON_DIR / "nav_bar_head_to_head_icon.svg")
    metrics_b64     = _img_to_b64(ICON_DIR / "nav_bar_metrics_icon.svg")
    hof_b64         = _img_to_b64(ICON_DIR / "nav_bar_hall_of_fame_crown.svg")
    minimums_b64    = _img_to_b64(ICON_DIR / "nav_bar_guild_minimums_icon.svg")
    import_b64      = _img_to_b64(ICON_DIR / "nav_bar_import_icon.svg")

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">'
        f'{"<img src=data:image/png;base64," + flag_b64 + " width=28 height=28>" if flag_b64 else "🏴"}'
        f'<span style="font-size:1.2rem;font-weight:800;color:#E8E8E8;">NEXUS</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # ── Custom HTML nav ───────────────────────────────────────────────────
    if "page" not in st.session_state:
        st.session_state.page = "🏴 Dashboard"

    _nav_items = [
        ("🏴 Dashboard",       flag_icon(28)),
        ("⚔️ GBG",             gbg_icon(28)),
        ("🌀 QI",              qi_icon(28)),
        ("👤 Player Profiles", "👤"),
        ("⚔️ Head to Head",    "⚔️"),
        ("🏅 Competitions",    "🏅"),
        ("📊 Metrics",         "📊"),
        ("🏆 Hall of Fame",    "🏆"),
        ("⚠️ Guild Minimums",  "⚠️"),
        ("🐛 Snuggy Bug",      "🐛"),
        ("📥 Data Import",     "📥"),
    ]

    for _nav_label, _nav_icon in _nav_items:
        _is_active = st.session_state.page == _nav_label
        _bg     = "background:#2A2D3A;" if _is_active else "background:transparent;"
        _col    = "color:#E8E8E8;"      if _is_active else "color:#C8CBD8;"
        _border = "border-left:3px solid #FFD700;" if _is_active else "border-left:3px solid transparent;"
        _icon_html = (
            f'<div style="width:28px;height:28px;display:flex;align-items:center;'
            f'justify-content:center;flex-shrink:0;font-size:18px;">{_nav_icon}</div>'
        )
        st.markdown(
            f'<div style="{_bg}{_border}border-radius:8px;padding:8px 12px;'
            f'margin-bottom:2px;display:flex;align-items:center;gap:10px;cursor:pointer;">'
            f'{_icon_html}'
            f'<span style="{_col}font-size:0.88rem;font-weight:{"600" if _is_active else "400"};">'
            f'{" ".join(_nav_label.split(" ")[1:])}'
            f'</span></div>',
            unsafe_allow_html=True,
        )
        if st.button(_nav_label, key=f"nav_{_nav_label}",
                     use_container_width=True):
            st.session_state.page = _nav_label
            st.rerun()

    page = st.session_state.page
    st.markdown("---")

    # ── Last updated indicator ────────────────────────────────────────────
    seasons = get_all_seasons()
    all_season_names = (
        sort_seasons(seasons["gbg"], descending=True)[:1] +
        sort_seasons(seasons["qi"], descending=True)[:1]
    )
    if all_season_names:
        st.markdown(
            f'<div style="color:#C8CBD8;font-size:0.72rem;text-transform:uppercase;'
            f'letter-spacing:1px;margin-bottom:4px;">Latest Data</div>',
            unsafe_allow_html=True,
        )
        if seasons["gbg"]:
            st.markdown(
                f'<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:8px;'
                f'padding:8px 10px;margin-bottom:4px;font-size:0.78rem;">'
                f'{gbg_icon(16)} <b>{sort_seasons(seasons["gbg"], descending=True)[0]}</b></div>',
                unsafe_allow_html=True,
            )
        if seasons["qi"]:
            st.markdown(
                f'<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:8px;'
                f'padding:8px 10px;margin-bottom:4px;font-size:0.78rem;">'
                f'{qi_icon(16)} <b>{sort_seasons(seasons["qi"], descending=True)[0]}</b></div>',
                unsafe_allow_html=True,
            )
        st.markdown("---")

    # ── Participation Tracker ─────────────────────────────────────────────
    _gbg_tmp     = get_gbg_df()
    _qi_tmp      = get_qi_df()
    _members_tmp = get_members_df()

    _show_tracker = not _gbg_tmp.empty
    if _show_tracker:
        _gbg_seasons = sort_seasons(_gbg_tmp["season"].unique().tolist())
        _latest_s    = _gbg_seasons[-1]

        # New players this season (first ever appearance in GBG)
        _new_players = []
        if len(_gbg_seasons) >= 2:
            _prev_pids  = set(_gbg_tmp[_gbg_tmp["season"] != _latest_s]["Player_ID"].astype(str))
            _latest_rows = _gbg_tmp[_gbg_tmp["season"] == _latest_s]
            for _, _r in _latest_rows.iterrows():
                if str(_r["Player_ID"]) not in _prev_pids:
                    _new_players.append(_r["Player"])

        # Left the guild (was in previous season, not in latest)
        _left_players = []
        if len(_gbg_seasons) >= 2:
            _prev_s    = _gbg_seasons[-2]
            _prev_pids2 = set(_gbg_tmp[_gbg_tmp["season"] == _prev_s]["Player_ID"].astype(str))
            _curr_pids2 = set(_gbg_tmp[_gbg_tmp["season"] == _latest_s]["Player_ID"].astype(str))
            _left_pids  = _prev_pids2 - _curr_pids2
            for _pid in _left_pids:
                _rows = _gbg_tmp[_gbg_tmp["Player_ID"].astype(str) == _pid]
                if not _rows.empty:
                    _left_players.append(_rows["Player"].iloc[0])

        # Inactive — in latest season but 0 fights
        _inactive_players = []
        _below_min_players = []
        _latest_gbg = _gbg_tmp[_gbg_tmp["season"] == _latest_s]
        for _, _r in _latest_gbg.iterrows():
            _fights = int(_r.get("Fights", 0))
            if _fights == 0:
                _inactive_players.append(_r["Player"])
            elif _fights < 1000:
                _pid_str     = str(_r["Player_ID"])
                _all_games   = _gbg_tmp[_gbg_tmp["Player_ID"].astype(str) == _pid_str]
                _times_under = int((_all_games["Fights"] < 1000).sum())
                _below_min_players.append((_r["Player"], _fights, _times_under))

        # QI below minimum (3,000 progress)
        _below_qi_players = []
        if not _qi_tmp.empty:
            _qi_seasons_s = sort_seasons(_qi_tmp["season"].unique().tolist())
            _latest_qi_s  = _qi_seasons_s[-1]
            _latest_qi    = _qi_tmp[_qi_tmp["season"] == _latest_qi_s]
            for _, _r in _latest_qi.iterrows():
                _prog = int(_r.get("Progress", 0))
                if 0 < _prog < 3000:
                    _pid_str     = str(_r["Player_ID"])
                    _all_qi      = _qi_tmp[_qi_tmp["Player_ID"].astype(str) == _pid_str]
                    _times_under = int((_all_qi["Progress"] < 3000).sum())
                    _below_qi_players.append((_r["Player"], _prog, _times_under))

        st.markdown(
            '<div style="color:#C8CBD8;font-size:0.72rem;text-transform:uppercase;'
            'letter-spacing:1px;margin-bottom:6px;">Participation Tracker</div>',
            unsafe_allow_html=True,
        )

        if not (_new_players or _left_players or _inactive_players or _below_min_players or _below_qi_players):
            st.markdown(
                '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:8px;'
                'padding:10px 12px;margin-bottom:6px;color:#2ECC71;font-size:0.78rem;">✅ All members on track</div>',
                unsafe_allow_html=True,
            )
        else:

            def _sidebar_pill_list(emoji, label, colour, names_with_sub=None, names=None):
                items = ""
                if names_with_sub:
                    items = "".join(
                        f'<div style="color:#C8C8C8;font-size:0.75rem;padding:1px 0;">'
                        f'• {n} <span style="color:#C8CBD8;">({v:,})</span>'
                        + (f' <span style="color:#A8ABB8;font-size:0.7rem;">({t}× total)</span>' if len(item) > 2 else '')
                        + '</div>'
                        for item in names_with_sub
                        for n, v, *rest in [item]
                        for t in [rest[0] if rest else None]
                    )
                elif names:
                    items = "".join(
                        f'<div style="color:#C8C8C8;font-size:0.75rem;padding:1px 0;">• {n}</div>'
                        for n in names
                    )
                if not items:
                    return
                st.markdown(
                    f'<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:8px;'
                    f'padding:10px 12px;margin-bottom:6px;">'
                    f'<div style="color:{colour};font-size:0.72rem;font-weight:700;'
                    f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:5px;">'
                    f'{emoji} {label}</div>'
                    f'{items}</div>',
                    unsafe_allow_html=True,
                )

            _sidebar_pill_list("🌟", "New This Season",             "#2ECC71", names=_new_players)
            _sidebar_pill_list("⚠️", "Below GBG Minimum (1,000)",   "#F39C12",
                               names_with_sub=sorted(_below_min_players, key=lambda x: x[1]))
            _sidebar_pill_list("⚠️", "Below QI Minimum (3,000)",    "#E67E22",
                               names_with_sub=sorted(_below_qi_players, key=lambda x: x[1]))
            _sidebar_pill_list("👋", "Left the Guild",               "#E74C3C", names=_left_players)
            _sidebar_pill_list("💤", "Inactive (0 Fights)",          "#C8CBD8", names=_inactive_players)
        st.markdown("---")

    # ── Activity Feed (last 30 days) ──────────────────────────────────────
    try:
        _last_seen = get_last_seen(days=30)
        if _last_seen:
            st.markdown(
                '<div style="color:#C8CBD8;font-size:0.72rem;text-transform:uppercase;'
                'letter-spacing:1px;margin-bottom:6px;">Guild Activity</div>',
                unsafe_allow_html=True,
            )
            import datetime as _dt_act
            _now = _dt_act.datetime.utcnow()
            _act_items = ""
            for _pname, _ts in list(_last_seen.items())[:8]:
                _delta = _now - _ts
                if _delta.days == 0:
                    _when = "today"
                    _wc   = "#2ECC71"
                elif _delta.days == 1:
                    _when = "yesterday"
                    _wc   = "#F39C12"
                else:
                    _when = f"{_delta.days}d ago"
                    _wc   = "#A8ABB8"
                _act_items += (
                    '<div style="display:flex;justify-content:space-between;'
                    'align-items:center;padding:3px 0;">'
                    '<div style="color:#C8C8C8;font-size:0.75rem;">' + str(_pname) + '</div>'
                    '<div style="color:' + _wc + ';font-size:0.7rem;">' + _when + '</div>'
                    '</div>'
                )
            st.markdown(
                '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:8px;'
                'padding:10px 12px;margin-bottom:6px;">' + _act_items + '</div>',
                unsafe_allow_html=True,
            )

            # Most active page this week
            _page_stats = get_page_stats(days=7)
            if not _page_stats.empty:
                _top_page = _page_stats.groupby("page")["visits"].sum().idxmax()
                st.markdown(
                    '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:8px;'
                    'padding:8px 12px;margin-bottom:6px;font-size:0.75rem;">'
                    '<span style="color:#C8CBD8;">🔥 Most visited: </span>'
                    '<span style="color:#4A90D9;font-weight:700;">' + str(_top_page) + '</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )

            # Top head to head this month
            _h2h_stats = get_h2h_stats(days=30)
            if not _h2h_stats.empty:
                _top_h2h = _h2h_stats.iloc[0]
                st.markdown(
                    '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:8px;'
                    'padding:8px 12px;margin-bottom:6px;font-size:0.75rem;">'
                    '<span style="color:#C8CBD8;">⚔️ Top rivalry: </span>'
                    '<span style="color:#FFD700;font-weight:700;">' + str(_top_h2h["matchup"]) + '</span>'
                    '<span style="color:#A8ABB8;"> (' + str(int(_top_h2h["count"])) + 'x)</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            st.markdown("---")
    except Exception:
        pass


# ── Cached data loaders ────────────────────────────────────────────────────
# TTL=300 means data refreshes every 5 minutes automatically.
# Calling st.cache_data.clear() after any import forces immediate refresh.

@st.cache_data(ttl=300)
def _load_gbg_df():
    return get_gbg_df()

@st.cache_data(ttl=300)
def _load_qi_df():
    return get_qi_df()

@st.cache_data(ttl=300)
def _load_members_df():
    return get_members_df()

@st.cache_data(ttl=300)
def _load_wins_df(gbg_df, qi_df):
    return get_all_season_winners(gbg_df, qi_df)

@st.cache_data(ttl=300)
def _load_all_players(gbg_df, qi_df, members_df):
    return get_all_players(gbg_df, qi_df, members_df)

@st.cache_data(ttl=300)
def _load_most_consistent(gbg_df, qi_df, mode="gbg"):
    return get_most_consistent_players(gbg_df, qi_df, mode)

@st.cache_data(ttl=300)
def _load_guild_health(gbg_df, qi_df, members_df):
    return get_guild_health(gbg_df, qi_df, members_df)

@st.cache_data(ttl=300)
def _load_hall_of_fame(gbg_df, qi_df):
    return get_hall_of_fame(gbg_df, qi_df)

@st.cache_data(ttl=300)
def _load_gbg_totals(gbg_df):
    return gbg_totals(gbg_df)

@st.cache_data(ttl=300)
def _load_qi_totals(qi_df):
    return qi_totals(qi_df)

@st.cache_data(ttl=300)
def _load_gbg_top(gbg_df, n=20):
    return gbg_top(gbg_df, n=n)

@st.cache_data(ttl=300)
def _load_qi_top(qi_df, n=20):
    return qi_top(qi_df, n=n)

# ── Load data ──────────────────────────────────────────────────────────────
gbg_df     = _load_gbg_df()
qi_df      = _load_qi_df()
members_df = _load_members_df()
wins_df    = _load_wins_df(gbg_df, qi_df)
guild_stats_df  = get_guild_stats_df()


# ── Name picker — show once per session ────────────────────────────────────
if not st.session_state.name_picker_shown:
    _all_p = _load_all_players(gbg_df, qi_df, members_df)
    _curr_names = sorted(_all_p["current"]["Player"].dropna().tolist()) if not _all_p["current"].empty else []
    if _curr_names:
        st.markdown("---")
        st.markdown(
            '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:14px;'
            'padding:24px 28px;margin-bottom:24px;">'
            '<div style="color:#E8E8E8;font-size:1.2rem;font-weight:800;margin-bottom:6px;">👋 Welcome to NEXUS</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        _pick_col1, _pick_col2 = st.columns([3, 1])
        with _pick_col1:
            _picked = st.selectbox("Who are you?", ["— Select your name —"] + _curr_names,
                                   label_visibility="collapsed", key="name_picker_select")
        with _pick_col2:
            if st.button("Continue →", key="name_picker_confirm"):
                if _picked != "— Select your name —":
                    st.session_state.current_user = _picked
                    st.session_state.name_picker_shown = True
                    st.rerun()
        st.stop()
    else:
        st.session_state.name_picker_shown = True


# ── Strip Player_ID from any display dataframe ─────────────────────────────
def hide_pid(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=[c for c in ["Player_ID", "player_id"] if c in df.columns])


# ══════════════════════════════════════════════════════════════════════════
# PAGE: OVERVIEW
# ══════════════════════════════════════════════════════════════════════════
if page == "🏴 Dashboard":
    log_event(st.session_state.get("current_user",""), "Dashboard", "visit")
    st.markdown(f'<h1>{flag_icon(32)} Guild Dashboard</h1>', unsafe_allow_html=True)

    # ── Personal dashboard banner ─────────────────────────────────────────
    _cu = st.session_state.get("current_user")
    if _cu:
        _all_p_cu = _load_all_players(gbg_df, qi_df, members_df)
        _cu_row   = _all_p_cu["current"][_all_p_cu["current"]["Player"] == _cu]
        _cu_pid   = str(_cu_row["Player_ID"].iloc[0]) if not _cu_row.empty else None
        _cu_mem   = get_latest_member_stats(members_df, _cu_pid) if _cu_pid else {}
        _cu_gbg_s = sort_seasons(gbg_df["season"].unique().tolist())[-1] if not gbg_df.empty else None
        _cu_qi_s  = sort_seasons(qi_df["season"].unique().tolist())[-1]  if not qi_df.empty  else None
        _cu_fights = int(gbg_df[(gbg_df["Player_ID"].astype(str)==_cu_pid) & (gbg_df["season"]==_cu_gbg_s)]["Fights"].sum()) if _cu_pid and _cu_gbg_s else 0
        _cu_prog   = int(qi_df[(qi_df["Player_ID"].astype(str)==_cu_pid) & (qi_df["season"]==_cu_qi_s)]["Progress"].sum()) if _cu_pid and _cu_qi_s else 0
        _cu_gbg_rank = 0
        if _cu_pid and _cu_gbg_s:
            _sf = gbg_df[gbg_df["season"]==_cu_gbg_s].sort_values("Fights", ascending=False).reset_index(drop=True)
            _sf.index = _sf.index + 1
            _cm = _sf[_sf["Player_ID"].astype(str)==_cu_pid]
            _cu_gbg_rank = int(_cm.index[0]) if not _cm.empty else 0
        _fc = "#2ECC71" if _cu_fights >= 1000 else "#E74C3C"
        _qc = "#9B59B6" if _cu_prog >= 3000 else "#E74C3C"
        _cu_pts = _cu_mem.get("points", 0)
        _cu_era = _cu_mem.get("eraName", "")

        # ── 1. Minimums status ────────────────────────────────────────────
        _gbg_ok_cu = _cu_fights >= 1000
        _qi_ok_cu  = _cu_prog  >= 3000

        # ── 2. Guild rank by points + vs avg ─────────────────────────────
        _cu_guild_rank    = 0
        _cu_pts_delta     = 0
        _guild_avg_pts_cu = 0
        if _cu_pid and not members_df.empty and "points" in members_df.columns and "snapshot" in members_df.columns:
            _lsnap_cu = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)[0]
            _sncu = members_df[members_df["snapshot"]==_lsnap_cu].copy()
            _sncu["points"] = pd.to_numeric(_sncu["points"], errors="coerce").fillna(0)
            _sncu_s = _sncu.sort_values("points", ascending=False).reset_index(drop=True)
            _sncu_s.index += 1
            _cu_rr = _sncu_s[_sncu_s["Player_ID"].astype(str)==_cu_pid]
            _cu_guild_rank    = int(_cu_rr.index[0]) if not _cu_rr.empty else 0
            _guild_avg_pts_cu = int(_sncu["points"].mean()) if not _sncu.empty else 0
            _cu_pts_delta     = (_cu_pts - _guild_avg_pts_cu) if _cu_pts and _guild_avg_pts_cu else 0

        # ── 3. vs personal GBG avg + all-time best ────────────────────────
        _cu_gbg_avg    = 0
        _cu_gbg_vs_avg = 0
        _cu_pb_gbg     = 0
        if _cu_pid and not gbg_df.empty:
            _pb_val = gbg_df[gbg_df["Player_ID"].astype(str)==_cu_pid]["Fights"].max()
            _cu_pb_gbg = int(_pb_val) if pd.notna(_pb_val) else 0
            if _cu_gbg_s:
                _cu_gbg_hist = gbg_df[(gbg_df["Player_ID"].astype(str)==_cu_pid) & (gbg_df["season"]!=_cu_gbg_s)]
                if not _cu_gbg_hist.empty:
                    _cu_gbg_avg    = int(_cu_gbg_hist["Fights"].mean())
                    _cu_gbg_vs_avg = _cu_fights - _cu_gbg_avg

        # ── 4. Consecutive minimums streak ───────────────────────────────
        _cu_streak = 0
        if _cu_pid and not gbg_df.empty and not qi_df.empty:
            import datetime as _dt_sk
            _gbg_pid = gbg_df[gbg_df["Player_ID"].astype(str) == _cu_pid]
            _qi_pid  = qi_df[qi_df["Player_ID"].astype(str) == _cu_pid]
            def _parse_sk(s):
                try: return _dt_sk.datetime.strptime(str(s).strip(), "%Y-%m-%d")
                except: return None
            _qi_dated = [(s, _parse_sk(s)) for s in _qi_pid["season"].unique() if _parse_sk(s)]
            for _ss in sort_seasons(_gbg_pid["season"].unique().tolist(), descending=True):
                _sd = _parse_sk(_ss)
                if _sd is None:
                    break
                _closest_qi = min(_qi_dated, key=lambda x: abs((x[1] - _sd).days)) if _qi_dated else None
                if _closest_qi is None or abs((_closest_qi[1] - _sd).days) > 10:
                    break
                _sf_s = int(_gbg_pid[_gbg_pid["season"] == _ss]["Fights"].sum())
                _sq_s = int(_qi_pid[_qi_pid["season"] == _closest_qi[0]]["Progress"].sum())
                if _sf_s >= 1000 and _sq_s >= 3000:
                    _cu_streak += 1
                else:
                    break

        # ── Last seen pill ────────────────────────────────────────────────
        _cu_last_seen_pill = ""
        import datetime as _dt_wc
        _ls_map_wc = get_last_seen(days=365)
        _ls_dt_wc  = _ls_map_wc.get(_cu)
        if _ls_dt_wc:
            _ls_delta_wc = _dt_wc.datetime.utcnow() - _ls_dt_wc
            _ls_days_wc  = _ls_delta_wc.days
            if _ls_days_wc == 0:
                _ls_label_wc = "👁 today"
                _ls_bg_wc, _ls_col_wc = "#1A3A1A", "#2ECC71"
            elif _ls_days_wc <= 3:
                _ls_label_wc = f"👁 {_ls_days_wc}d ago"
                _ls_bg_wc, _ls_col_wc = "#3A2A1A", "#F39C12"
            else:
                _ls_label_wc = f"👁 {_ls_days_wc}d ago"
                _ls_bg_wc, _ls_col_wc = "#1A1D27", "#A8ABB8"
            _cu_last_seen_pill = (
                f'<span style="background:{_ls_bg_wc};color:{_ls_col_wc};border:1px solid {_ls_col_wc}55;'
                f'padding:2px 9px;border-radius:20px;font-size:0.72rem;font-weight:600;">'
                f'{_ls_label_wc}</span>'
            )

        # ── Points delta vs previous snapshot ────────────────────────────
        _cu_pts_snap_delta = None
        if _cu_pid and not members_df.empty and "snapshot" in members_df.columns:
            _snaps_cu = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
            if len(_snaps_cu) >= 2:
                _snap_prev = members_df[members_df["snapshot"] == _snaps_cu[1]]
                _prev_row  = _snap_prev[_snap_prev["Player_ID"].astype(str) == _cu_pid]
                if not _prev_row.empty:
                    _prev_pts = pd.to_numeric(_prev_row["points"].iloc[0], errors="coerce")
                    if pd.notna(_prev_pts) and _cu_pts:
                        _cu_pts_snap_delta = int(_cu_pts) - int(_prev_pts)

        # ── Top % attack from guild stats ─────────────────────────────────
        _cu_top_pct_badge = ""
        if guild_stats_df is not None and not guild_stats_df.empty and "gbg_attack" in guild_stats_df.columns:
            _gs_cu = guild_stats_df[guild_stats_df["player_name"].str.strip().str.lower() == _cu.strip().lower()]
            if not _gs_cu.empty:
                _cu_atk_val = pd.to_numeric(_gs_cu["gbg_attack"].iloc[0], errors="coerce")
                _all_atk_cu = pd.to_numeric(guild_stats_df["gbg_attack"], errors="coerce").dropna()
                if pd.notna(_cu_atk_val) and len(_all_atk_cu) > 1:
                    _cu_pct_rank = int((_all_atk_cu < _cu_atk_val).sum() / len(_all_atk_cu) * 100)
                    _cu_top_pct  = 100 - _cu_pct_rank
                    _cu_atk_col  = "#2ECC71" if _cu_top_pct <= 25 else "#F39C12" if _cu_top_pct <= 60 else "#C8CBD8"
                    _cu_top_pct_badge = (
                        f'<span style="background:{_cu_atk_col}22;color:{_cu_atk_col};'
                        f'border:1px solid {_cu_atk_col}55;padding:2px 9px;border-radius:20px;'
                        f'font-size:0.72rem;font-weight:700;">⚔️ Top {_cu_top_pct}% Atk</span>'
                    )

        # ── GBG / QI medals ───────────────────────────────────────────────
        _cu_medals_html = ""
        if _cu_pid and not wins_df.empty:
            _cu_wins_row = wins_df[wins_df["Player_ID"] == _cu_pid]
            if not _cu_wins_row.empty:
                _cu_gbg_w = int(_cu_wins_row["gbg_wins"].iloc[0])
                _cu_qi_w  = int(_cu_wins_row["qi_wins"].iloc[0])
                if _cu_gbg_w:
                    _cu_medals_html += (
                        f'<span style="background:#2A2000;color:#FFD700;border:1px solid #FFD70055;'
                        f'padding:2px 9px;border-radius:20px;font-size:0.72rem;font-weight:700;">'
                        f'🥇 {_cu_gbg_w}× GBG</span>'
                    )
                if _cu_qi_w:
                    _cu_medals_html += (
                        f'<span style="background:#1A1A2A;color:#C0C0C0;border:1px solid #C0C0C055;'
                        f'padding:2px 9px;border-radius:20px;font-size:0.72rem;font-weight:700;">'
                        f'🥇 {_cu_qi_w}× QI</span>'
                    )

        # ── Era pill ──────────────────────────────────────────────────────
        _cu_era_pill = (
            f'<span style="background:#1A2A2A;color:#4A90D9;border:1px solid #4A90D955;'
            f'padding:2px 9px;border-radius:20px;font-size:0.72rem;font-weight:600;">'
            f'{_cu_era}</span>'
        ) if _cu_era else ""

        # ── Points pill ───────────────────────────────────────────────────
        _cu_pts_pill = ""
        if _cu_pts:
            _delta_html = ""
            if _cu_pts_snap_delta is not None:
                _d_col = "#2ECC71" if _cu_pts_snap_delta >= 0 else "#E74C3C"
                _d_str = f'+{_cu_pts_snap_delta:,}' if _cu_pts_snap_delta >= 0 else f'{_cu_pts_snap_delta:,}'
                _delta_html = f'<span style="color:{_d_col};margin-left:4px;font-size:0.68rem;">{_d_str}</span>'
            _cu_pts_pill = (
                f'<span style="background:#2A2A1A;color:#FFD700;border:1px solid #FFD70055;'
                f'padding:2px 9px;border-radius:20px;font-size:0.72rem;font-weight:700;">'
                f'{_cu_pts:,} pts</span>{_delta_html}'
            )

        # ── Build card ────────────────────────────────────────────────────
        _gbg_status = '✅' if _gbg_ok_cu else '❌'
        _qi_status  = '✅' if _qi_ok_cu  else '❌'
        _streak_icon = '🔥' if _cu_streak >= 2 else ('✅' if _cu_streak == 1 else '—')
        _vs_avg_str = (f'+{_cu_gbg_vs_avg:,}' if _cu_gbg_vs_avg >= 0 else f'{_cu_gbg_vs_avg:,}') if _cu_gbg_avg else '—'
        _vs_avg_col = '#2ECC71' if _cu_gbg_vs_avg >= 0 else '#E74C3C'
        _rank_medal = {1:'🥇', 2:'🥈', 3:'🥉'}.get(_cu_guild_rank, f'#{_cu_guild_rank}')

        def _wc_box(label, main_val, main_col, lines):
            _inner = ''.join(
                f'<div style="color:{lc};font-size:0.7rem;margin-top:2px;">{lt}</div>'
                for lt, lc in lines if lt
            )
            return (
                '<div style="background:#0E1117;border-radius:10px;padding:12px 16px;min-width:110px;">'
                f'<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">{label}</div>'
                f'<div style="color:{main_col};font-size:1.25rem;font-weight:900;line-height:1;">{main_val}</div>'
                + _inner +
                '</div>'
            )

        _cu_html = (
            '<div style="background:linear-gradient(135deg,#1A1D27 0%,#12151E 100%);'
            'border:1px solid #2A2D3A;border-radius:14px;padding:20px 24px;margin-bottom:20px;">'

            # ── Header row ────────────────────────────────────────────────
            '<div style="display:flex;align-items:flex-start;justify-content:space-between;'
            'flex-wrap:wrap;gap:8px;margin-bottom:14px;">'
            '<div>'
            '<div style="color:#C8CBD8;font-size:0.7rem;text-transform:uppercase;letter-spacing:1px;">Welcome back</div>'
            '<div style="color:#FFD700;font-size:1.4rem;font-weight:900;margin-bottom:6px;">' + _cu + '</div>'
            '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
            + _cu_era_pill
            + _cu_pts_pill
            + _cu_top_pct_badge
            + _cu_medals_html
            + _cu_last_seen_pill +
            '</div>'
            '</div>'
            + (
                f'<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:8px;'
                f'padding:6px 14px;text-align:center;">'
                f'<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;letter-spacing:0.5px;">Guild Rank</div>'
                f'<div style="color:#FFD700;font-size:1.2rem;font-weight:900;">{_rank_medal}</div>'
                f'</div>'
                if _cu_guild_rank else ''
            ) +
            '</div>'

            # ── Stat boxes ────────────────────────────────────────────────
            '<div style="display:flex;gap:10px;flex-wrap:wrap;">'
            + (_wc_box(
                'GBG ' + _cu_gbg_s if _cu_gbg_s else 'GBG',
                f'{_cu_fights:,}', _fc,
                [
                    (f'{_gbg_status} {"Met" if _gbg_ok_cu else "Below"} min (1,000)', '#2ECC71' if _gbg_ok_cu else '#E74C3C'),
                    (f'Rank #{_cu_gbg_rank}' if _cu_gbg_rank else '', '#C8CBD8'),
                    (f'{_vs_avg_str} vs your avg' if _cu_gbg_avg else '', _vs_avg_col),
                    (f'PB: {_cu_pb_gbg:,}' if _cu_pb_gbg else '', '#FFD700'),
                ]
            ) if _cu_gbg_s else '')
            + (_wc_box(
                'QI ' + _cu_qi_s if _cu_qi_s else 'QI',
                f'{_cu_prog:,}', _qc,
                [
                    (f'{_qi_status} {"Met" if _qi_ok_cu else "Below"} min (3,000)', '#9B59B6' if _qi_ok_cu else '#E74C3C'),
                ]
            ) if _cu_qi_s else '')
            + _wc_box(
                'Min Streak',
                f'{_streak_icon} {_cu_streak}' if _cu_streak else '—',
                '#FFD700' if _cu_streak >= 3 else ('#2ECC71' if _cu_streak >= 1 else '#C8CBD8'),
                [
                    ('seasons hitting both mins' if _cu_streak else 'No streak yet', '#C8CBD8'),
                ]
            )
            + '</div>'
            '</div>'
        )
        st.markdown(_cu_html, unsafe_allow_html=True)

    gbg_tots = _load_gbg_totals(gbg_df)
    qi_tots  = _load_qi_totals(qi_df)

    # Allow dashboard to show even with only member data
    has_any_data = not (gbg_tots.empty and qi_tots.empty and members_df.empty)

    if not has_any_data:
        st.info("👋 Welcome! Head to **📥 Data Import** to upload your first season CSV.")
    else:
        health = _load_guild_health(gbg_df, qi_df, members_df)

        # ── Helper: card render ───────────────────────────────────────────
        def _dash_card(rank, player, val_label, val, val_col, sub_label=None, sub_val=None,
                       sub_col="#C8CBD8", bar_pct=100):
            medal   = {0:"🥇",1:"🥈",2:"🥉"}.get(rank, f"#{rank+1}")
            bar_col = "#FFD700" if rank==0 else "#C0C0C0" if rank==1 else "#CD7F32" if rank==2 else "#4A90D9"
            sub_html = ""
            if sub_label and sub_val is not None:
                sub_html = (
                    '<div style="text-align:right;">'
                    '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">' + sub_label + '</div>'
                    '<div style="color:' + sub_col + ';font-weight:700;font-size:0.85rem;">' + str(sub_val) + '</div>'
                    '</div>'
                )
            return (
                '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;'
                'padding:12px 16px;margin-bottom:6px;">'
                '<div style="display:flex;align-items:center;justify-content:space-between;">'
                '<div style="display:flex;align-items:center;gap:10px;">'
                '<span style="font-size:1.1rem;">' + medal + '</span>'
                '<span style="color:#E8E8E8;font-weight:700;font-size:0.9rem;">' + str(player) + '</span>'
                '</div>'
                '<div style="display:flex;gap:16px;align-items:center;">'
                '<div style="text-align:right;">'
                '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">' + val_label + '</div>'
                '<div style="color:' + val_col + ';font-weight:700;font-size:0.85rem;">' + str(val) + '</div>'
                '</div>'
                + sub_html +
                '</div></div>'
                '<div style="background:#0E1117;border-radius:4px;height:4px;margin-top:8px;">'
                '<div style="background:' + bar_col + ';width:' + str(bar_pct) + '%;height:4px;border-radius:4px;"></div>'
                '</div></div>'
            )

        def _render_cards_with_expander(rows, render_fn, label="more"):
            """Show top 3, rest in expander."""
            for i, row in enumerate(rows[:3]):
                st.markdown(render_fn(i, row), unsafe_allow_html=True)
            if len(rows) > 3:
                with st.expander(f"Show {len(rows)-3} more"):
                    for i, row in enumerate(rows[3:], 3):
                        st.markdown(render_fn(i, row), unsafe_allow_html=True)

        # ── KPI rows ──────────────────────────────────────────────────────
        def _kpi_card(label, value, value_colour, sub=""):
            return (
                '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:12px;'
                'padding:16px 20px;">'
                f'<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;'
                f'letter-spacing:1px;margin-bottom:6px;">{label}</div>'
                f'<div style="color:{value_colour};font-weight:800;font-size:1.45rem;line-height:1.1;">{value}</div>'
                f'<div style="color:#C8CBD8;font-size:0.72rem;margin-top:4px;min-height:1em;">{sub}</div>'
                '</div>'
            )

        # Compute GBG stats
        _gbg_total_fights = f"{int(gbg_df['Fights'].sum()):,}" if not gbg_df.empty else "—"
        _gbg_seasons_n    = str(gbg_df["season"].nunique()) if not gbg_df.empty else "—"
        _gbg_part         = health.get("gbg_participation")
        _gbg_part_val     = f"{_gbg_part}%" if _gbg_part is not None else "—"
        _gbg_part_sub     = (f"{health.get('gbg_players','?')} of {health.get('total_members','?')} members"
                             if _gbg_part is not None else "")
        _gbg_last_fights = "—"
        _gbg_last_season_label = "Last Season"
        if not gbg_df.empty:
            _gbg_all_s = sort_seasons(gbg_df["season"].unique().tolist())
            _gbg_last_s = _gbg_all_s[-1]
            _gbg_last_fights = f"{int(gbg_df[gbg_df['season'] == _gbg_last_s]['Fights'].sum()):,}"
            _gbg_last_season_label = _gbg_last_s

        # Compute QI stats
        _qi_total_prog  = f"{int(qi_df['Progress'].sum()):,}" if not qi_df.empty else "—"
        _qi_seasons_n   = str(qi_df["season"].nunique()) if not qi_df.empty else "—"
        _qi_part_val, _qi_part_sub = "—", ""
        if not qi_df.empty and not gbg_df.empty:
            _qi_latest_s   = sort_seasons(qi_df["season"].unique().tolist())[-1]
            _gbg_latest_s  = sort_seasons(gbg_df["season"].unique().tolist())[-1]
            _curr_pids_qi  = set(gbg_df[gbg_df["season"] == _gbg_latest_s]["Player_ID"].astype(str))
            _qi_latest_row = qi_df[qi_df["season"] == _qi_latest_s]
            _qi_players    = _qi_latest_row[_qi_latest_row["Player_ID"].astype(str).isin(_curr_pids_qi)]["Player_ID"].nunique()
            _total_curr    = len(_curr_pids_qi)
            _qi_part_pct   = round(_qi_players / max(_total_curr, 1) * 100)
            _qi_part_val   = f"{_qi_part_pct}%"
            _qi_part_sub   = f"{_qi_players} of {_total_curr} current players"
        _qi_last_prog = "—"
        _qi_last_season_label = "Last Season"
        if not qi_df.empty:
            _qi_all_s = sort_seasons(qi_df["season"].unique().tolist())
            _qi_last_s = _qi_all_s[-1]
            _qi_last_prog = f"{int(qi_df[qi_df['season'] == _qi_last_s]['Progress'].sum()):,}"
            _qi_last_season_label = _qi_last_s

        # Row 1 — GBG
        _r1c1, _r1c2, _r1c3, _r1c4 = st.columns(4)
        with _r1c1:
            st.markdown(_kpi_card(f"{gbg_icon(14)} Total Guild Fights", _gbg_total_fights, "#FFD700"), unsafe_allow_html=True)
        with _r1c2:
            st.markdown(_kpi_card(f"{gbg_icon(14)} GBG Seasons", _gbg_seasons_n, "#FFD700"), unsafe_allow_html=True)
        with _r1c3:
            st.markdown(_kpi_card(f"{gbg_icon(14)} GBG Participation", _gbg_part_val, "#FFD700", _gbg_part_sub), unsafe_allow_html=True)
        with _r1c4:
            st.markdown(_kpi_card(f"{gbg_icon(14)} Fights Last Season", _gbg_last_fights, "#FFD700", _gbg_last_season_label), unsafe_allow_html=True)

        st.markdown('<div style="margin-bottom:10px;"></div>', unsafe_allow_html=True)

        # Row 2 — QI
        _r2c1, _r2c2, _r2c3, _r2c4 = st.columns(4)
        with _r2c1:
            st.markdown(_kpi_card(f"{qi_icon(14)} Total QI Progress", _qi_total_prog, "#9B59B6"), unsafe_allow_html=True)
        with _r2c2:
            st.markdown(_kpi_card(f"{qi_icon(14)} QI Seasons", _qi_seasons_n, "#9B59B6"), unsafe_allow_html=True)
        with _r2c3:
            st.markdown(_kpi_card(f"{qi_icon(14)} QI Participation", _qi_part_val, "#9B59B6", _qi_part_sub), unsafe_allow_html=True)
        with _r2c4:
            st.markdown(_kpi_card(f"{qi_icon(14)} QI Progress Last Season", _qi_last_prog, "#9B59B6", _qi_last_season_label), unsafe_allow_html=True)

        # ── Boost headline KPIs ───────────────────────────────────────────
        if not guild_stats_df.empty:
            st.markdown('<div style="margin-bottom:10px;"></div>', unsafe_allow_html=True)
            _bs1, _bs2, _bs3, _bs4 = st.columns(4)
            def _gs_avg(col): return int(pd.to_numeric(guild_stats_df.get(col, pd.Series()), errors="coerce").dropna().mean()) if col in guild_stats_df.columns else 0
            _gg_sum     = int(pd.to_numeric(guild_stats_df.get("guild_goods_production", pd.Series()), errors="coerce").fillna(0).sum())
            _avg_atk_a  = _gs_avg("gbg_attack")
            _avg_def_a  = _gs_avg("gbg_defense")
            _avg_atk_d  = _gs_avg("gbg_defending_units_attack")
            _avg_def_d  = _gs_avg("gbg_defending_units_defense")
            _avg_crit   = round(float(pd.to_numeric(guild_stats_df.get("critical_hit", pd.Series()), errors="coerce").dropna().mean()), 2) if "critical_hit" in guild_stats_df.columns else 0
            with _bs1:
                st.markdown(_kpi_card("🏰 Daily Guild Goods", f"{_gg_sum:,}", "#4A90D9", "total roster output"), unsafe_allow_html=True)
            with _bs2:
                st.markdown(_kpi_card("⚔️ Avg Attacking Units", f"{_avg_atk_a:,}%", "#E74C3C", f"atk · def: {_avg_def_a:,}%"), unsafe_allow_html=True)
            with _bs3:
                st.markdown(_kpi_card("🛡️ Avg Defending Units", f"{_avg_atk_d:,}%", "#4A90D9", f"atk · def: {_avg_def_d:,}%"), unsafe_allow_html=True)
            with _bs4:
                st.markdown(_kpi_card("🎯 Avg Crit Chance", f"{_avg_crit:.2f}%", "#FFD700", "mean across guild"), unsafe_allow_html=True)

        # ── Recruitment & Recognition KPIs ───────────────────────────────
        st.markdown('<div class="section-title">📊 Guild Health Indicators</div>', unsafe_allow_html=True)

        _rr1, _rr2, _rr3, _rr4, _rr5 = st.columns(5)

        # ── Roster size vs target ──
        with _rr1:
            _roster_count = len(members_df[members_df["snapshot"] == sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)[0]]) if not members_df.empty and "snapshot" in members_df.columns else 0
            _roster_delta = _roster_count - 80
            _roster_label = f"{_roster_delta:+d} vs cap" if _roster_delta != 0 else "At cap"
            st.metric(
                "Roster Size",
                f"{_roster_count} / 80",
                delta=_roster_label,
                delta_color="inverse" if _roster_delta < 0 else "normal",
                help="Current members vs guild cap of 80"
            )

        # ── Dead slots ──
        with _rr2:
            _dead_slots = 0
            if not gbg_df.empty and not qi_df.empty:
                _all_gbg_seasons = sort_seasons(gbg_df["season"].unique().tolist())
                _all_qi_seasons  = sort_seasons(qi_df["season"].unique().tolist())
                _last3_gbg = set(_all_gbg_seasons[-3:]) if len(_all_gbg_seasons) >= 3 else set(_all_gbg_seasons)
                _last3_qi  = set(_all_qi_seasons[-3:])  if len(_all_qi_seasons)  >= 3 else set(_all_qi_seasons)
                # Get all known current player IDs
                if not members_df.empty and "snapshot" in members_df.columns:
                    _latest_snap = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)[0]
                    _current_pids_rr = set(members_df[members_df["snapshot"]==_latest_snap]["Player_ID"].astype(str))
                else:
                    _current_pids_rr = set(gbg_df[gbg_df["season"]==_all_gbg_seasons[-1]]["Player_ID"].astype(str))
                for _dpid in _current_pids_rr:
                    _in_gbg = any(_dpid in gbg_df[gbg_df["season"]==s]["Player_ID"].astype(str).values for s in _last3_gbg)
                    _in_qi  = any(_dpid in qi_df[qi_df["season"]==s]["Player_ID"].astype(str).values  for s in _last3_qi)
                    if not _in_gbg and not _in_qi:
                        _dead_slots += 1
            st.metric(
                "Dead Slots",
                _dead_slots,
                delta="inactive 3+ seasons" if _dead_slots > 0 else "None",
                delta_color="inverse" if _dead_slots > 0 else "normal",
                help="Current members who haven't appeared in GBG or QI in the last 3 seasons"
            )

        # ── Points floor ──
        with _rr3:
            _pts_floor = 0
            _pts_floor_name = "—"
            if not members_df.empty and "snapshot" in members_df.columns and "points" in members_df.columns:
                _latest_snap_pf = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)[0]
                _snap_df_pf = members_df[members_df["snapshot"]==_latest_snap_pf].copy()
                _snap_df_pf["points"] = pd.to_numeric(_snap_df_pf["points"], errors="coerce").fillna(0)
                if not _snap_df_pf.empty:
                    _floor_row = _snap_df_pf.loc[_snap_df_pf["points"].idxmin()]
                    _pts_floor = int(_floor_row["points"])
                    _pts_floor_name = str(_floor_row.get("Player", _floor_row.get("member", "?")))
                    _guild_avg_pts = int(_snap_df_pf["points"].mean())
                    _floor_gap = _pts_floor - _guild_avg_pts
            st.metric(
                "Points Floor",
                f"{_pts_floor:,}" if _pts_floor else "—",
                delta=_pts_floor_name,
                delta_color="off",
                help="Lowest ranked member's points — large gap vs guild average may indicate a weak slot"
            )

        # ── Perfect season count ──
        with _rr4:
            _perfect = 0
            _total_active = 0
            if not gbg_df.empty and not qi_df.empty:
                _lat_gbg = sort_seasons(gbg_df["season"].unique().tolist())[-1]
                _lat_qi  = sort_seasons(qi_df["season"].unique().tolist())[-1]
                _lat_gbg_df = gbg_df[gbg_df["season"]==_lat_gbg]
                _lat_qi_df  = qi_df[qi_df["season"]==_lat_qi]
                _active_pids = set(_lat_gbg_df["Player_ID"].astype(str)) | set(_lat_qi_df["Player_ID"].astype(str))
                _total_active = len(_active_pids)
                for _ppid in _active_pids:
                    _pf = int(_lat_gbg_df[_lat_gbg_df["Player_ID"].astype(str)==_ppid]["Fights"].sum())
                    _pp = int(_lat_qi_df[_lat_qi_df["Player_ID"].astype(str)==_ppid]["Progress"].sum())
                    if _pf >= 1000 and _pp >= 3000:
                        _perfect += 1
            st.metric(
                "Perfect Season",
                f"{_perfect} / {_total_active}" if _total_active else "—",
                delta="met both targets" if _perfect == _total_active and _total_active > 0 else f"{_total_active - _perfect} missed",
                delta_color="normal" if _perfect == _total_active else "inverse",
                help="Players who hit both GBG (1,000 fights) and QI (3,000 progress) minimums last season"
            )

        # ── New personal bests ──
        with _rr5:
            _new_pbs = 0
            if not gbg_df.empty:
                _pb_latest = sort_seasons(gbg_df["season"].unique().tolist())[-1]
                _pb_pids   = gbg_df[gbg_df["season"]==_pb_latest]["Player_ID"].astype(str).unique()
                for _pb_pid in _pb_pids:
                    _pb_hist = gbg_df[gbg_df["Player_ID"].astype(str)==_pb_pid]
                    if len(_pb_hist) < 2:
                        continue
                    _this_pb  = int(_pb_hist[_pb_hist["season"]==_pb_latest]["Fights"].sum())
                    _prev_best = int(_pb_hist[_pb_hist["season"]!=_pb_latest]["Fights"].max())
                    if _this_pb > _prev_best and _this_pb >= 1000:
                        _new_pbs += 1
            st.metric(
                "New Personal Bests",
                _new_pbs,
                delta="players this season" if _new_pbs > 0 else "none this season",
                delta_color="normal" if _new_pbs > 0 else "off",
                help="Players who set their highest ever GBG fight count this season"
            )

        st.markdown("---")

        # ── Season vs season KPI comparison ──────────────────────────────
        gbg_seasons = sort_seasons(gbg_df["season"].unique().tolist()) if not gbg_df.empty else []
        qi_seasons  = sort_seasons(qi_df["season"].unique().tolist())  if not qi_df.empty  else []

        if len(gbg_seasons) >= 2 or len(qi_seasons) >= 2:
            st.markdown('<div class="section-title">📊 Season vs Season Comparison</div>', unsafe_allow_html=True)
            kc1, kc2, kc3, kc4 = st.columns(4)

            def _delta_html(delta, formatter=lambda d: f"{d:+,}"):
                if delta is None:
                    return ""
                col = "#2ECC71" if delta >= 0 else "#E74C3C"
                arrow = "▲" if delta >= 0 else "▼"
                return f'<span style="color:{col};font-size:0.78rem;font-weight:700;">{arrow} {formatter(abs(delta))}</span>'

            if len(gbg_seasons) >= 2:
                curr_s, prev_s = gbg_seasons[-1], gbg_seasons[-2]
                curr_fights = int(gbg_df[gbg_df["season"] == curr_s]["Fights"].sum())
                prev_fights = int(gbg_df[gbg_df["season"] == prev_s]["Fights"].sum())
                curr_p = gbg_df[gbg_df["season"] == curr_s]["Player_ID"].nunique()
                prev_p = gbg_df[gbg_df["season"] == prev_s]["Player_ID"].nunique()
                with kc1:
                    st.markdown(_kpi_card(
                        f"{gbg_icon(14)} GBG Fights",
                        f"{curr_fights:,}",
                        "#FFD700",
                        f"vs {prev_s}: {_delta_html(curr_fights - prev_fights)}"
                    ), unsafe_allow_html=True)
                with kc2:
                    st.markdown(_kpi_card(
                        f"{gbg_icon(14)} GBG Players",
                        str(curr_p),
                        "#FFD700",
                        f"vs {prev_s}: {_delta_html(curr_p - prev_p)}"
                    ), unsafe_allow_html=True)

            if len(qi_seasons) >= 2:
                curr_qs, prev_qs = qi_seasons[-1], qi_seasons[-2]
                curr_prog = int(qi_df[qi_df["season"] == curr_qs]["Progress"].sum())
                prev_prog = int(qi_df[qi_df["season"] == prev_qs]["Progress"].sum())
                curr_qp   = qi_df[qi_df["season"] == curr_qs]["Player_ID"].nunique()
                prev_qp   = qi_df[qi_df["season"] == prev_qs]["Player_ID"].nunique()
                with kc3:
                    st.markdown(_kpi_card(
                        f"{qi_icon(14)} QI Progress",
                        f"{curr_prog:,}",
                        "#9B59B6",
                        f"vs {prev_qs}: {_delta_html(curr_prog - prev_prog)}"
                    ), unsafe_allow_html=True)
                with kc4:
                    st.markdown(_kpi_card(
                        f"{qi_icon(14)} QI Players",
                        str(curr_qp),
                        "#9B59B6",
                        f"vs {prev_qs}: {_delta_html(curr_qp - prev_qp)}"
                    ), unsafe_allow_html=True)

            st.markdown("---")

        # ── Season Debrief ────────────────────────────────────────────────
        if not gbg_df.empty and len(gbg_seasons) >= 1:
            _db_s       = gbg_seasons[-1]
            _db_prev    = gbg_seasons[-2] if len(gbg_seasons) >= 2 else None
            _db_rows    = gbg_df[gbg_df["season"] == _db_s]
            _db_tot     = int(_db_rows["Fights"].sum())
            _db_tot_neg = int(_db_rows["Negotiations"].sum()) if "Negotiations" in _db_rows.columns else 0
            _db_players = int(_db_rows["Player_ID"].nunique())
            _db_avg     = int(_db_tot / max(_db_players, 1))
            _db_top_f   = _db_rows.sort_values("Fights", ascending=False).iloc[0]
            _db_top_n   = (_db_rows.sort_values("Negotiations", ascending=False).iloc[0]
                           if "Negotiations" in _db_rows.columns else None)
            _db_below   = int((_db_rows["Fights"] < 1000).sum())
            _db_prev_tot   = int(gbg_df[gbg_df["season"]==_db_prev]["Fights"].sum()) if _db_prev else None
            _db_prev_below = int((gbg_df[gbg_df["season"]==_db_prev]["Fights"] < 1000).sum()) if _db_prev else None
            _best_ever  = int(gbg_df.groupby("season")["Fights"].sum().max())

            # Most improved — biggest absolute fights gain vs their previous season
            _db_improved_name, _db_improved_delta = None, 0
            if _db_prev:
                _prev_rows = gbg_df[gbg_df["season"] == _db_prev].set_index("Player_ID")["Fights"]
                for _, _r in _db_rows.iterrows():
                    _pid_s = str(_r["Player_ID"])
                    if _pid_s in _prev_rows.index.astype(str).values:
                        _delta = int(_r["Fights"]) - int(_prev_rows[_prev_rows.index.astype(str) == _pid_s].iloc[0])
                        if _delta > _db_improved_delta:
                            _db_improved_delta = _delta
                            _db_improved_name  = _r["Player"]

            # New personal bests this season
            _pb_count = 0
            for _pid_pb in _db_rows["Player_ID"].astype(str).unique():
                _all_pb  = gbg_df[gbg_df["Player_ID"].astype(str) == _pid_pb]
                _this_pb = int(_db_rows[_db_rows["Player_ID"].astype(str) == _pid_pb]["Fights"].sum())
                if _this_pb >= int(_all_pb["Fights"].max()):
                    _pb_count += 1

            def _nm(name):   # yellow name
                return f'<span style="color:#FFD700;font-weight:700;">{name}</span>'
            def _nb(number): # blue number
                return f'<span style="color:#4A90D9;font-weight:700;">{number}</span>'

            _lines = []

            # Line 1 — guild total fights + % change
            if _db_prev_tot:
                _pct = (_db_tot - _db_prev_tot) / max(_db_prev_tot, 1) * 100
                _dir = '<span style="color:#2ECC71;">▲</span>' if _pct > 0 else '<span style="color:#E74C3C;">▼</span>'
                _lines.append(
                    f'Guild recorded {_nb(f"{_db_tot:,}")} fights from {_nb(_db_players)} players '
                    f'— {_dir} {_nb(f"{abs(_pct):.1f}%")} vs previous season.'
                )
            else:
                _lines.append(
                    f'Guild recorded {_nb(f"{_db_tot:,}")} fights from {_nb(_db_players)} players.'
                )

            # Line 2 — negotiations + avg fights
            if _db_tot_neg > 0:
                _lines.append(
                    f'Total negotiations: {_nb(f"{_db_tot_neg:,}")} · Average fights per player: {_nb(f"{_db_avg:,}")}.'
                )
            else:
                _lines.append(f'Average fights per active player: {_nb(f"{_db_avg:,}")}.')

            # Line 3 — top fighter
            _top_f_name   = _db_top_f["Player"]
            _top_f_fights = int(_db_top_f["Fights"])
            _lines.append(
                f'{_nm(_top_f_name)} led all fighters with {_nb(f"{_top_f_fights:,}")} fights.'
            )

            # Line 4 — top negotiator (only if different from top fighter and has negs data)
            if (_db_top_n is not None and
                    int(_db_top_n.get("Negotiations", 0)) > 0 and
                    _db_top_n["Player"] != _db_top_f["Player"]):
                _top_n_name = _db_top_n["Player"]
                _top_n_negs = int(_db_top_n["Negotiations"])
                _lines.append(
                    f'{_nm(_top_n_name)} led negotiations with {_nb(f"{_top_n_negs:,}")}.'
                )

            # Line 5 — most improved
            if _db_improved_name and _db_improved_delta > 0:
                _lines.append(
                    f'Biggest improvement: {_nm(_db_improved_name)} +{_nb(f"{_db_improved_delta:,}")} fights vs last season.'
                )

            # Line 6 — personal bests
            if _pb_count > 0:
                _lines.append(
                    f'{_nb(str(_pb_count))} player{"s" if _pb_count != 1 else ""} set a new personal best this season.'
                )

            # Line 7 — below minimum
            if _db_below > 0:
                _bd = ""
                if _db_prev_below is not None:
                    _bd = (f', <span style="color:#2ECC71;">down from {_db_prev_below}</span> last season'
                           if _db_below < _db_prev_below
                           else f', <span style="color:#E74C3C;">up from {_db_prev_below}</span> last season')
                _lines.append(
                    f'{_nb(str(_db_below))} player{"s" if _db_below != 1 else ""} missed the {_nb("1,000")} fight minimum{_bd}.'
                )
            else:
                _lines.append('Every active player met the <span style="color:#2ECC71;font-weight:700;">1,000</span> fight minimum. ✅')

            # Line 8 — best season ever
            if _db_tot >= _best_ever and len(gbg_seasons) > 1:
                _lines.append('This was the guild\'s <span style="color:#FFD700;font-weight:700;">best season on record</span>. 🏆')

            _debrief_html = "".join(
                f'<div style="margin-bottom:6px;">{l}</div>' for l in _lines
            )

            st.markdown('<div class="section-title">📋 Latest Season Debrief</div>', unsafe_allow_html=True)
            st.markdown(
                '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:12px;padding:18px 22px;margin-bottom:6px;">'
                '<div style="color:#C8CBD8;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;">' + _db_s + '</div>'
                '<div style="color:#E8E8E8;font-size:0.9rem;line-height:1.7;">' + _debrief_html + '</div>'
                '</div>', unsafe_allow_html=True)
            st.markdown("---")

        # ── GBG + QI Season Totals ────────────────────────────────────────
        col_l, col_r = st.columns(2)

        with col_l:
            st.markdown(f'<div class="section-title">{gbg_icon()} GBG Season Totals</div>', unsafe_allow_html=True)
            if not gbg_tots.empty:
                st.plotly_chart(gbg_guild_trend(gbg_tots), width="stretch")
                gbg_rows = list(hide_pid(gbg_tots).rename(columns={
                    "season":"Season","total_fights":"Fights",
                    "total_negotiations":"Negotiations","player_count":"Players"
                }).itertuples(index=False, name=None))
                # show most recent 3, rest in expander
                def _gbg_tot_card(i, row):
                    return (
                        '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;'
                        'padding:12px 16px;margin-bottom:6px;display:flex;align-items:center;gap:16px;">'
                        '<div style="flex:1;"><div style="color:#E8E8E8;font-weight:700;font-size:0.9rem;display:flex;align-items:center;gap:5px;">' + gbg_icon(16) + ' ' + str(row[0]) + '</div></div>'
                        '<div style="text-align:center;min-width:70px;">'
                        '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;">Fights</div>'
                        '<div style="color:#FFD700;font-weight:700;">' + f"{int(row[1]):,}" + '</div></div>'
                        '<div style="text-align:center;min-width:70px;">'
                        '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;">Negs</div>'
                        '<div style="color:#4A90D9;font-weight:700;">' + f"{int(row[2]):,}" + '</div></div>'
                        '<div style="text-align:center;min-width:50px;">'
                        '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;">Players</div>'
                        '<div style="color:#2ECC71;font-weight:700;">' + str(int(row[3])) + '</div></div>'
                        '</div>'
                    )
                gbg_rows_sorted = sorted(gbg_rows, key=lambda r: r[0], reverse=True)
                for row in gbg_rows_sorted[:3]:
                    st.markdown(_gbg_tot_card(0, row), unsafe_allow_html=True)
                if len(gbg_rows_sorted) > 3:
                    with st.expander(f"Show {len(gbg_rows_sorted)-3} more seasons"):
                        for row in gbg_rows_sorted[3:]:
                            st.markdown(_gbg_tot_card(0, row), unsafe_allow_html=True)

        with col_r:
            st.markdown(f'<div class="section-title">{qi_icon()} QI Season Totals</div>', unsafe_allow_html=True)
            if not qi_tots.empty:
                st.plotly_chart(qi_guild_trend(qi_tots), width="stretch")
                qi_rows = list(hide_pid(qi_tots).rename(columns={
                    "season":"Season","total_progress":"Progress","player_count":"Players"
                }).itertuples(index=False, name=None))
                def _qi_tot_card(i, row):
                    return (
                        '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;'
                        'padding:12px 16px;margin-bottom:6px;display:flex;align-items:center;gap:16px;">'
                        '<div style="flex:1;"><div style="color:#E8E8E8;font-weight:700;font-size:0.9rem;display:flex;align-items:center;gap:5px;">' + qi_icon(16) + ' ' + str(row[0]) + '</div></div>'
                        '<div style="text-align:center;min-width:80px;">'
                        '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;">Progress</div>'
                        '<div style="color:#FFD700;font-weight:700;">' + f"{int(row[1]):,}" + '</div></div>'
                        '<div style="text-align:center;min-width:50px;">'
                        '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;">Players</div>'
                        '<div style="color:#2ECC71;font-weight:700;">' + str(int(row[2])) + '</div></div>'
                        '</div>'
                    )
                qi_rows_sorted = sorted(qi_rows, key=lambda r: r[0], reverse=True)
                for row in qi_rows_sorted[:3]:
                    st.markdown(_qi_tot_card(0, row), unsafe_allow_html=True)
                if len(qi_rows_sorted) > 3:
                    with st.expander(f"Show {len(qi_rows_sorted)-3} more seasons"):
                        for row in qi_rows_sorted[3:]:
                            st.markdown(_qi_tot_card(0, row), unsafe_allow_html=True)

        st.markdown("---")

        # ── Top Contributors ──────────────────────────────────────────────
        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown(f'<div class="section-title">{gbg_icon()} Top GBG Contributors (Latest)</div>', unsafe_allow_html=True)
            top_gbg = hide_pid(_load_gbg_top(gbg_df, n=20))
            if not top_gbg.empty:
                max_f = top_gbg["Fights"].max() if "Fights" in top_gbg.columns else 1
                rows_gbg = list(top_gbg.itertuples(index=False))
                def _gbg_contrib(i, row):
                    bar = int(getattr(row,"Fights",0) / max(max_f,1) * 100)
                    return _dash_card(i, row.Player, "Fights", f"{int(getattr(row,'Fights',0)):,}",
                                      "#FFD700", "Negs", f"{int(getattr(row,'Negotiations',0)):,}",
                                      "#4A90D9", bar)
                _render_cards_with_expander(rows_gbg, _gbg_contrib)

        with col_b:
            st.markdown(f'<div class="section-title">{qi_icon()} Top QI Contributors (Latest)</div>', unsafe_allow_html=True)
            top_qi = hide_pid(_load_qi_top(qi_df, n=20))
            if not top_qi.empty:
                max_p = top_qi["Progress"].max() if "Progress" in top_qi.columns else 1
                rows_qi = list(top_qi.itertuples(index=False))
                def _qi_contrib(i, row):
                    bar = int(getattr(row,"Progress",0) / max(max_p,1) * 100)
                    return _dash_card(i, row.Player, "Progress", f"{int(getattr(row,'Progress',0)):,}",
                                      "#FFD700", bar_pct=bar)
                _render_cards_with_expander(rows_qi, _qi_contrib)

        st.markdown("---")

        # ── Avg Fights / Avg Progress ─────────────────────────────────────
        col_c, col_d = st.columns(2)

        with col_c:
            st.markdown(f'<div class="section-title">{gbg_icon()} Top 10 Avg Fights / Season</div>', unsafe_allow_html=True)
            avg_gbg = _load_most_consistent(gbg_df, qi_df, "gbg")
            if not isinstance(avg_gbg, pd.DataFrame):
                avg_gbg = pd.DataFrame()
            if not avg_gbg.empty:
                _avg_col_g = [c for c in avg_gbg.columns if "Avg" in c or "Fight" in c]
                _avg_col_g = _avg_col_g[0] if _avg_col_g else avg_gbg.columns[1]
                _score_col_g = [c for c in avg_gbg.columns if "Score" in c or "⭐" in c]
                _score_col_g = _score_col_g[0] if _score_col_g else avg_gbg.columns[-1]
                _max_g = avg_gbg.index[0] if not avg_gbg.empty else 1
                for i, (_, row) in enumerate(avg_gbg.reset_index(drop=True).iterrows()):
                    _sc = str(row.get(_score_col_g, "")).replace(",","")
                    _sc_int = int(float(_sc)) if _sc else 1
                    _max_sc = int(float(str(avg_gbg[_score_col_g].iloc[0]).replace(",",""))) if not avg_gbg.empty else 1
                    bar = int(_sc_int / max(_max_sc, 1) * 100)
                    st.markdown(_dash_card(i, row["Player"], "Avg Fights",
                                str(row.get(_avg_col_g, "")), "#FFD700",
                                "Seasons", str(row.get("Seasons", "")), "#C8CBD8", bar),
                                unsafe_allow_html=True)
                if len(avg_gbg) > 3:
                    pass  # already showing all 10, expander not needed for this section

        with col_d:
            st.markdown(f'<div class="section-title">{qi_icon()} Top 10 Avg Progress / Season</div>', unsafe_allow_html=True)
            avg_qi = _load_most_consistent(gbg_df, qi_df, "qi")
            if not isinstance(avg_qi, pd.DataFrame):
                avg_qi = pd.DataFrame()
            if not avg_qi.empty:
                _avg_col_q = [c for c in avg_qi.columns if "Avg" in c or "Progress" in c]
                _avg_col_q = _avg_col_q[0] if _avg_col_q else avg_qi.columns[1]
                _score_col_q = [c for c in avg_qi.columns if "Score" in c or "⭐" in c]
                _score_col_q = _score_col_q[0] if _score_col_q else avg_qi.columns[-1]
                for i, (_, row) in enumerate(avg_qi.reset_index(drop=True).iterrows()):
                    _sc = str(row.get(_score_col_q, "")).replace(",","")
                    _sc_int = int(float(_sc)) if _sc else 1
                    _max_sc = int(float(str(avg_qi[_score_col_q].iloc[0]).replace(",",""))) if not avg_qi.empty else 1
                    bar = int(_sc_int / max(_max_sc, 1) * 100)
                    st.markdown(_dash_card(i, row["Player"], "Avg Progress",
                                str(row.get(_avg_col_q, "")), "#9B59B6",
                                "Seasons", str(row.get("Seasons", "")), "#C8CBD8", bar),
                                unsafe_allow_html=True)

        st.markdown("---")

        # ── Player spotlights ─────────────────────────────────────────────
        st.markdown('<div class="section-title">🔦 Player Spotlights</div>', unsafe_allow_html=True)
        improved  = get_most_improved(gbg_df, qi_df)
        streaks   = get_active_streak(gbg_df, qi_df)
        newcomers = get_newcomers(gbg_df, qi_df)

        sp1, sp2, sp3, sp4 = st.columns(4)

        def _stat_card(emoji, title, name, value_html, sub=""):
            return (
                '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:12px;'
                'padding:16px 18px;height:100%;min-height:120px;">'
                '<div style="color:#C8CBD8;font-size:0.7rem;text-transform:uppercase;'
                'letter-spacing:1px;margin-bottom:6px;">' + emoji + ' ' + title + '</div>'
                '<div style="color:#E8E8E8;font-size:1rem;font-weight:700;margin-bottom:4px;">' + name + '</div>'
                '<div style="font-size:0.9rem;">' + value_html + '</div>'
                + ('<div style="color:#A8ABB8;font-size:0.72rem;margin-top:6px;">' + sub + '</div>' if sub else '') +
                '</div>'
            )

        with sp1:
            b = improved.get("best")
            if b:
                sign  = "+" if b["delta"] >= 0 else ""
                vhtml = '<span style="color:#2ECC71;font-weight:700;">' + sign + f'{b["delta"]:,}' + ' fights (' + sign + f'{b["pct"]:.1f}%)</span>'
                st.markdown(_stat_card("🚀","Most Improved", b["player"], vhtml, b["seasons"]), unsafe_allow_html=True)
            else:
                st.markdown(_stat_card("🚀","Most Improved","—","Need 2+ seasons",""), unsafe_allow_html=True)

        with sp2:
            w = improved.get("worst")
            if w:
                sign  = "+" if w["delta"] >= 0 else ""
                col   = "#E74C3C" if w["delta"] < 0 else "#2ECC71"
                vhtml = '<span style="color:' + col + ';font-weight:700;">' + sign + f'{w["delta"]:,}' + ' fights (' + sign + f'{w["pct"]:.1f}%)</span>'
                st.markdown(_stat_card("⚠️","Needs Attention", w["player"], vhtml, w["seasons"]), unsafe_allow_html=True)
            else:
                st.markdown(_stat_card("⚠️","Needs Attention","—","Need 2+ seasons",""), unsafe_allow_html=True)

        with sp3:
            if streaks:
                top_s = streaks[0]
                vhtml = '<span style="color:#FFD700;font-weight:700;">' + str(top_s["streak"]) + ' consecutive seasons</span>'
                st.markdown(_stat_card("🔥","Longest Streak", top_s["player"], vhtml,
                                       f'{top_s["total_seasons"]} total seasons'), unsafe_allow_html=True)
            else:
                st.markdown(_stat_card("🔥","Longest Streak","—","No data",""), unsafe_allow_html=True)

        with sp4:
            if newcomers:
                names_html = "".join(
                    '<div style="color:#4A90D9;font-size:0.85rem;">• ' + n["player"] +
                    ' <span style="color:#A8ABB8;font-size:0.75rem;">(' + ", ".join(n["sections"]) + ')</span></div>'
                    for n in newcomers[:4]
                )
                extra = f'+{len(newcomers)-4} more' if len(newcomers) > 4 else ""
                st.markdown(
                    '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:12px;'
                    'padding:16px 18px;min-height:120px;">'
                    '<div style="color:#C8CBD8;font-size:0.7rem;text-transform:uppercase;'
                    'letter-spacing:1px;margin-bottom:8px;">🌟 Newcomers This Season</div>'
                    + names_html +
                    ('<div style="color:#A8ABB8;font-size:0.72rem;margin-top:4px;">' + extra + '</div>' if extra else '') +
                    '</div>', unsafe_allow_html=True)
            else:
                st.markdown(_stat_card("🌟","Newcomers This Season","—","No newcomers",""), unsafe_allow_html=True)

        # ── Fun KPIs ──────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown('<div class="section-title">🎲 Guild Curiosities</div>', unsafe_allow_html=True)
        st.markdown('<div style="color:#A8ABB8;font-size:0.78rem;margin-bottom:12px;">Refreshes every 24 hours</div>', unsafe_allow_html=True)

        import hashlib as _hl, datetime as _dt_fun

        _day_seed = int(_hl.md5(str(_dt_fun.date.today()).encode()).hexdigest(), 16)

        def _fun_card(emoji, title, name, value, sub, bg_col, text_col="#E8E8E8"):
            return (
                '<div style="background:' + bg_col + ';border-radius:12px;padding:16px 18px;height:100%;">'
                '<div style="font-size:1.6rem;margin-bottom:6px;">' + emoji + '</div>'
                '<div style="color:' + text_col + ';font-size:0.68rem;text-transform:uppercase;'
                'letter-spacing:1px;margin-bottom:4px;opacity:0.8;">' + title + '</div>'
                '<div style="color:' + text_col + ';font-size:1.05rem;font-weight:900;margin-bottom:2px;">' + str(name) + '</div>'
                '<div style="color:' + text_col + ';font-size:0.88rem;font-weight:700;opacity:0.9;margin-bottom:4px;">' + str(value) + '</div>'
                '<div style="color:' + text_col + ';font-size:0.72rem;opacity:0.6;">' + str(sub) + '</div>'
                '</div>'
            )

        _fun_stats = []

        if not gbg_df.empty:
            _fun_seasons = sort_seasons(gbg_df["season"].unique().tolist())
            _fun_latest  = _fun_seasons[-1]
            _lat_gbg_df  = gbg_df[gbg_df["season"] == _fun_latest]

            # 1. The Grinder
            _grinder_row = gbg_df.loc[gbg_df["Fights"].idxmax()]
            _fun_stats.append({
                "emoji": "🔩", "title": "The Grinder",
                "name": str(_grinder_row["Player"]),
                "value": f"{int(_grinder_row['Fights']):,} fights",
                "sub": f"All-time single season record · {_grinder_row['season']}",
                "bg": "#1A2A1A", "col": "#2ECC71"
            })

            # 2. The Ghost
            if not members_df.empty and "snapshot" in members_df.columns:
                _ghost_snap = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)[0]
                _ghost_pids = set(members_df[members_df["snapshot"]==_ghost_snap]["Player_ID"].astype(str))
                _gbg_pids   = set(gbg_df["Player_ID"].astype(str))
                _qi_pids    = set(qi_df["Player_ID"].astype(str)) if not qi_df.empty else set()
                _ghosts     = _ghost_pids - _gbg_pids - _qi_pids
                if _ghosts:
                    _ghost_pid  = list(_ghosts)[0]
                    _ghost_rows = members_df[members_df["Player_ID"].astype(str)==_ghost_pid]
                    _ghost_name = str(_ghost_rows["Player"].iloc[0]) if not _ghost_rows.empty else _ghost_pid
                    _fun_stats.append({
                        "emoji": "👻", "title": "The Ghost",
                        "name": _ghost_name,
                        "value": "0 GBG or QI seasons",
                        "sub": "On the roster but never seen in action",
                        "bg": "#1A1A2A", "col": "#9B59B6"
                    })

            # 3. The Comeback Kid
            _comeback_best = None
            _comeback_delta = 0
            for _cpid in gbg_df["Player_ID"].astype(str).unique():
                _cp_hist   = gbg_df[gbg_df["Player_ID"].astype(str)==_cpid].copy()
                _cp_sorted = sort_seasons(_cp_hist["season"].unique().tolist())
                if len(_cp_sorted) < 3:
                    continue
                _cp_vals = {s: int(_cp_hist[_cp_hist["season"]==s]["Fights"].sum()) for s in _cp_sorted}
                for _ci in range(1, len(_cp_sorted)-1):
                    _prev_f = _cp_vals.get(_cp_sorted[_ci-1], 0)
                    _curr_f = _cp_vals.get(_cp_sorted[_ci], 0)
                    _next_f = _cp_vals.get(_cp_sorted[_ci+1], 0)
                    if _prev_f > 1000 and _curr_f < 500 and _next_f > _prev_f:
                        _delta = _next_f - _curr_f
                        if _delta > _comeback_delta:
                            _comeback_delta = _delta
                            _comeback_name  = str(_cp_hist["Player"].iloc[0])
                            _comeback_from  = _curr_f
                            _comeback_to    = _next_f
                            _comeback_best  = True
            if _comeback_best:
                _fun_stats.append({
                    "emoji": "🔄", "title": "The Comeback Kid",
                    "name": _comeback_name,
                    "value": f"{_comeback_from:,} → {_comeback_to:,} fights",
                    "sub": "Biggest bounce back after a bad season",
                    "bg": "#2A1A1A", "col": "#E74C3C"
                })

            # 4. The Metronome
            _metro_best = None
            _metro_std  = 999999
            _metro_avg  = 0
            for _mpid in gbg_df["Player_ID"].astype(str).unique():
                _mp_hist = gbg_df[gbg_df["Player_ID"].astype(str)==_mpid]
                if len(_mp_hist) < 5:
                    continue
                _mp_std = float(_mp_hist["Fights"].std())
                _mp_avg = float(_mp_hist["Fights"].mean())
                if _mp_avg >= 1000 and _mp_std < _metro_std:
                    _metro_std  = _mp_std
                    _metro_best = str(_mp_hist["Player"].iloc[0])
                    _metro_avg  = int(_mp_avg)
            if _metro_best:
                _fun_stats.append({
                    "emoji": "⏱️", "title": "The Metronome",
                    "name": _metro_best,
                    "value": f"±{int(_metro_std):,} fights variance",
                    "sub": f"Most consistent player · avg {_metro_avg:,}/season",
                    "bg": "#1A2A2A", "col": "#4A90D9"
                })

            # 5. The Overachiever
            _over_best = None
            _over_pct  = 0
            _over_this = 0
            for _opid in _lat_gbg_df["Player_ID"].astype(str).unique():
                _op_hist = gbg_df[gbg_df["Player_ID"].astype(str)==_opid]
                if len(_op_hist) < 3:
                    continue
                _op_avg  = float(_op_hist[_op_hist["season"]!=_fun_latest]["Fights"].mean())
                _op_this = int(_op_hist[_op_hist["season"]==_fun_latest]["Fights"].sum())
                if _op_avg > 0:
                    _op_pct = (_op_this - _op_avg) / _op_avg * 100
                    if _op_pct > _over_pct:
                        _over_pct  = _op_pct
                        _over_best = str(_op_hist["Player"].iloc[0])
                        _over_this = _op_this
            if _over_best:
                _fun_stats.append({
                    "emoji": "🚀", "title": "The Overachiever",
                    "name": _over_best,
                    "value": f"+{_over_pct:.0f}% above their average",
                    "sub": f"{_over_this:,} fights this season",
                    "bg": "#2A2A1A", "col": "#FFD700"
                })

            # 6. The Veteran
            _vet_counts = gbg_df.groupby("Player_ID")["season"].nunique()
            if not qi_df.empty:
                _qi_counts  = qi_df.groupby("Player_ID")["season"].nunique()
                _vet_counts = _vet_counts.add(_qi_counts, fill_value=0)
            _vet_pid  = str(_vet_counts.idxmax())
            _vet_rows = gbg_df[gbg_df["Player_ID"].astype(str)==_vet_pid]
            _vet_name = str(_vet_rows["Player"].iloc[0]) if not _vet_rows.empty else _vet_pid
            _fun_stats.append({
                "emoji": "🎖️", "title": "The Veteran",
                "name": _vet_name,
                "value": f"{int(_vet_counts.max())} total seasons",
                "sub": "Most seasons played across GBG and QI",
                "bg": "#1A1A2A", "col": "#9B59B6"
            })

            # 7. The Dark Horse
            if not members_df.empty and "points" in members_df.columns:
                _dh_snap   = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)[0]
                _dh_mem    = members_df[members_df["snapshot"]==_dh_snap][["Player_ID","points","rank"]].copy()
                _dh_mem["points"]    = pd.to_numeric(_dh_mem["points"], errors="coerce").fillna(0)
                _dh_mem["rank"]      = pd.to_numeric(_dh_mem["rank"],   errors="coerce").fillna(999)
                _dh_mem["Player_ID"] = _dh_mem["Player_ID"].astype(str)
                _dh_fights = _lat_gbg_df.groupby("Player_ID")["Fights"].sum().reset_index()
                _dh_fights["Player_ID"] = _dh_fights["Player_ID"].astype(str)
                _dh_merged = _dh_fights.merge(_dh_mem, on="Player_ID", how="inner")
                if not _dh_merged.empty:
                    _dh_merged["fight_rank"] = _dh_merged["Fights"].rank(ascending=False)
                    _dh_merged["score"]      = _dh_merged["rank"] - _dh_merged["fight_rank"]
                    _dh_row   = _dh_merged.loc[_dh_merged["score"].idxmax()]
                    _dh_rows  = gbg_df[gbg_df["Player_ID"].astype(str)==str(_dh_row["Player_ID"])]
                    _dh_name  = str(_dh_rows["Player"].iloc[0]) if not _dh_rows.empty else "?"
                    _fun_stats.append({
                        "emoji": "🐴", "title": "The Dark Horse",
                        "name": _dh_name,
                        "value": f"{int(_dh_row['Fights']):,} fights",
                        "sub": f"Guild rank #{int(_dh_row['rank'])} but fights like a top player",
                        "bg": "#1A1E2A", "col": "#4A90D9"
                    })

            # 8. The Loyal One
            _loyal_best  = None
            _loyal_count = 0
            _all_gbg_s_set = set(gbg_df["season"].unique())
            for _lpid in gbg_df["Player_ID"].astype(str).unique():
                _lp_seasons = set(gbg_df[gbg_df["Player_ID"].astype(str)==_lpid]["season"].unique())
                if _lp_seasons == _all_gbg_s_set and len(_lp_seasons) > _loyal_count:
                    _loyal_count = len(_lp_seasons)
                    _loyal_rows  = gbg_df[gbg_df["Player_ID"].astype(str)==_lpid]
                    _loyal_best  = str(_loyal_rows["Player"].iloc[0])
            if _loyal_best:
                _fun_stats.append({
                    "emoji": "🤝", "title": "The Loyal One",
                    "name": _loyal_best,
                    "value": f"All {_loyal_count} seasons",
                    "sub": "Never missed a single GBG season",
                    "bg": "#1A2A1A", "col": "#2ECC71"
                })

            # 9. The Late Bloomer
            _bloom_best  = None
            _bloom_delta = 0
            _bloom_early = 0
            _bloom_late  = 0
            for _bpid in gbg_df["Player_ID"].astype(str).unique():
                _bp_hist = gbg_df[gbg_df["Player_ID"].astype(str)==_bpid]
                _bp_seas = sort_seasons(_bp_hist["season"].unique().tolist())
                if len(_bp_seas) < 6:
                    continue
                _bp_vals  = {s: int(_bp_hist[_bp_hist["season"]==s]["Fights"].sum()) for s in _bp_seas}
                _bp_early = sum(_bp_vals[s] for s in _bp_seas[:3]) / 3
                _bp_late  = sum(_bp_vals[s] for s in _bp_seas[-3:]) / 3
                _bp_delta = _bp_late - _bp_early
                if _bp_delta > _bloom_delta:
                    _bloom_delta = _bp_delta
                    _bloom_best  = str(_bp_hist["Player"].iloc[0])
                    _bloom_early = int(_bp_early)
                    _bloom_late  = int(_bp_late)
            if _bloom_best:
                _fun_stats.append({
                    "emoji": "🌱", "title": "The Late Bloomer",
                    "name": _bloom_best,
                    "value": f"{_bloom_early:,} → {_bloom_late:,} avg fights",
                    "sub": "Biggest career improvement over time",
                    "bg": "#2A1A2A", "col": "#9B59B6"
                })

            # 10. The Sleeping Giant
            if not members_df.empty and "points" in members_df.columns:
                _sg_snap   = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)[0]
                _sg_mem    = members_df[members_df["snapshot"]==_sg_snap][["Player_ID","points"]].copy()
                _sg_mem["points"]    = pd.to_numeric(_sg_mem["points"], errors="coerce").fillna(0)
                _sg_mem["Player_ID"] = _sg_mem["Player_ID"].astype(str)
                _sg_fights = _lat_gbg_df.groupby("Player_ID")["Fights"].sum().reset_index()
                _sg_fights["Player_ID"] = _sg_fights["Player_ID"].astype(str)
                _sg_merged = _sg_mem.merge(_sg_fights, on="Player_ID", how="inner")
                if not _sg_merged.empty and _sg_merged["points"].max() > 0:
                    _sg_merged["pts_norm"]    = _sg_merged["points"] / _sg_merged["points"].max()
                    _sg_merged["fights_norm"] = _sg_merged["Fights"] / max(_sg_merged["Fights"].max(), 1)
                    _sg_merged["score"]       = _sg_merged["pts_norm"] - _sg_merged["fights_norm"]
                    _sg_row   = _sg_merged.loc[_sg_merged["score"].idxmax()]
                    _sg_rows  = gbg_df[gbg_df["Player_ID"].astype(str)==str(_sg_row["Player_ID"])]
                    _sg_name  = str(_sg_rows["Player"].iloc[0]) if not _sg_rows.empty else "?"
                    _fun_stats.append({
                        "emoji": "😴", "title": "The Sleeping Giant",
                        "name": _sg_name,
                        "value": f"{int(_sg_row['points']):,} pts · {int(_sg_row['Fights']):,} fights",
                        "sub": "High points, low GBG output — untapped potential",
                        "bg": "#2A1A1A", "col": "#F39C12"
                    })

        # ── Pick 3 based on daily seed ────────────────────────────────────
        if _fun_stats:
            import random as _rnd
            _rnd.seed(_day_seed)
            _todays_picks = _rnd.sample(_fun_stats, min(3, len(_fun_stats)))
            _fc1, _fc2, _fc3 = st.columns(3)
            for _fcol, _pick in zip([_fc1, _fc2, _fc3], _todays_picks):
                with _fcol:
                    st.markdown(
                        _fun_card(
                            _pick["emoji"], _pick["title"],
                            _pick["name"],  _pick["value"],
                            _pick["sub"],   _pick["bg"],   _pick["col"]
                        ),
                        unsafe_allow_html=True,
                    )

        # ── Achievements Feed ─────────────────────────────────────────────
        st.markdown('<div class="section-title">🎖️ Recent Milestones</div>', unsafe_allow_html=True)
        _achieve_events = []
        if not gbg_df.empty:
            _af_seasons = sort_seasons(gbg_df["season"].unique().tolist())
            _af_latest  = _af_seasons[-1]
            _curr_pids_af = set(gbg_df[gbg_df["season"]==_af_latest]["Player_ID"].astype(str))
            for _pid in _curr_pids_af:
                _pname = gbg_df[gbg_df["Player_ID"].astype(str)==_pid]["Player"].iloc[-1]
                _total_f = int(gbg_df[gbg_df["Player_ID"].astype(str)==_pid]["Fights"].sum())
                _seasons_count = int(gbg_df[gbg_df["Player_ID"].astype(str)==_pid]["season"].nunique())
                for _thresh, _label, _col in [(1_000_000,"crossed 1M lifetime fights","#FFD700"),(500_000,"crossed 500K lifetime fights","#9B59B6"),(100_000,"crossed 100K lifetime fights","#E74C3C"),(50_000,"crossed 50K lifetime fights","#F39C12")]:
                    _prev_total = _total_f - int(gbg_df[(gbg_df["Player_ID"].astype(str)==_pid) & (gbg_df["season"]==_af_latest)]["Fights"].sum())
                    if _prev_total < _thresh <= _total_f:
                        _achieve_events.append({"icon":"⚔️","player":_pname,"text":_label,"col":_col,"season":_af_latest})
                        break
                for _sc, _sl in [(20,"played their 20th season"),(15,"played their 15th season"),(10,"played their 10th season"),(5,"played their 5th season")]:
                    if _seasons_count == _sc:
                        _achieve_events.append({"icon":"🛡️","player":_pname,"text":_sl,"col":"#4A90D9","season":_af_latest})
                        break
                _this_f = int(gbg_df[(gbg_df["Player_ID"].astype(str)==_pid) & (gbg_df["season"]==_af_latest)]["Fights"].sum())
                _pb_f_raw = gbg_df[(gbg_df["Player_ID"].astype(str)==_pid) & (gbg_df["season"]!=_af_latest)]["Fights"].max() if len(_af_seasons) > 1 else None
                _pb_f = int(_pb_f_raw) if _pb_f_raw is not None and pd.notna(_pb_f_raw) else 0
                if _this_f > _pb_f > 0 and _this_f >= 3000:
                    _achieve_events.append({"icon":"🚀","player":_pname,"text":f"set a new personal best with {_this_f:,} fights","col":"#2ECC71","season":_af_latest})
                _above5k = gbg_df[(gbg_df["Player_ID"].astype(str)==_pid) & (gbg_df["Fights"]>=5000)]
                if len(_above5k) == 1 and _af_latest in _above5k["season"].values:
                    _achieve_events.append({"icon":"⭐","player":_pname,"text":"hit 5,000+ fights for the first time","col":"#FFD700","season":_af_latest})
        if _achieve_events:
            _af_cols = st.columns(2)
            _af_col_html = ["", ""]
            for _ei, _ev in enumerate(_achieve_events[:10]):
                _af_av = get_avatar_html(_ev["player"], size=40)
                _af_col_html[_ei % 2] += (
                    '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;'
                    'padding:12px 16px;margin-bottom:6px;display:flex;align-items:center;gap:12px;">'
                    + _af_av +
                    '<div style="flex:1;">'
                    '<div style="color:' + _ev["col"] + ';font-weight:700;font-size:0.92rem;">' + _ev["player"] + '</div>'
                    '<div style="color:#C8CBD8;font-size:0.8rem;">' + _ev["text"] + '</div>'
                    '<div style="color:#A8ABB8;font-size:0.68rem;margin-top:2px;">' + _ev["season"] + '</div>'
                    '</div>'
                    '<div style="font-size:1.4rem;flex-shrink:0;">' + _ev["icon"] + '</div>'
                    '</div>'
                )
            with _af_cols[0]:
                st.markdown(_af_col_html[0], unsafe_allow_html=True)
            with _af_cols[1]:
                st.markdown(_af_col_html[1], unsafe_allow_html=True)
        else:
            st.info("No milestones detected yet — import more seasons to build history.")

        st.markdown("---")

        # ── Points trend + Era distribution ──────────────────────────────
        pt1, pt2 = st.columns(2)
        with pt1:
            st.markdown('<div class="section-title">📈 Guild Points Trend</div>', unsafe_allow_html=True)
            if not members_df.empty:
                st.plotly_chart(points_trend_chart(members_df), width="stretch")
            else:
                st.info("No member snapshot data yet.")
        with pt2:
            st.markdown('<div class="section-title">🌍 Era Distribution</div>', unsafe_allow_html=True)
            if not members_df.empty:
                st.plotly_chart(era_distribution_chart(members_df), width="stretch")
            else:
                st.info("No member snapshot data yet.")

        st.markdown("---")

        # ── Player status ─────────────────────────────────────────────────
        st.markdown('<div class="section-title">📋 Player Status — Latest Season</div>', unsafe_allow_html=True)
        status_df = detect_player_status(gbg_df, qi_df)
        if not status_df.empty:
            for sec in status_df["section"].unique():
                st.markdown(f"**{sec}**")
                sec_df = status_df[status_df["section"] == sec]
                latest_season = sec_df["season"].max()
                latest_df = sec_df[sec_df["season"] == latest_season]
                for status, css in [("new","pill-new"),("returning","pill-returning"),
                                     ("missing","pill-missing"),("active","pill-active")]:
                    names = latest_df[latest_df["status"] == status]["Player"].tolist()
                    if names:
                        st.markdown(
                            f'<span class="{css}">{status.upper()}: {len(names)}</span> — {", ".join(names)}',
                            unsafe_allow_html=True,
                        )
    _render_footer()


# ══════════════════════════════════════════════════════════════════════════
# PAGE: GBG
# ══════════════════════════════════════════════════════════════════════════
elif page == "⚔️ GBG":
    log_event(st.session_state.get("current_user",""), "GBG", "visit")
    st.markdown(f'<h1>{gbg_icon(32)} Guild Battlegrounds (GBG)</h1>', unsafe_allow_html=True)

    if gbg_df.empty:
        st.info("No GBG data yet. Import a season in **📥 Data Import**.")
    else:
        # Filter to current players only
        _current_pids_gbg = set(gbg_df[gbg_df["season"] == sort_seasons(gbg_df["season"].unique().tolist())[-1]]["Player_ID"].astype(str))
        gbg_df_curr = gbg_df[gbg_df["Player_ID"].astype(str).isin(_current_pids_gbg)]

        seasons_list = sort_seasons(get_all_seasons()["gbg"], descending=True)
        tab_lb, tab_charts, tab_comp, tab_cumu = st.tabs(
            ["🏅 Leaderboard", "📊 Charts", "📈 Season Comparison", "📦 Cumulative"]
        )

        with tab_lb:
            col_s, col_sort = st.columns([2, 2])
            with col_s:
                sel_season = st.selectbox("Season", ["Latest"] + seasons_list, key="gbg_lb_season")
            with col_sort:
                sort_col = st.selectbox("Sort by", ["Total", "Fights", "Negotiations"], key="gbg_sort")
            season_arg = None if sel_season == "Latest" else sel_season
            lb = hide_pid(gbg_leaderboard(gbg_df_curr, season=season_arg, sort_by=sort_col))
            if not lb.empty:
                medal_map = {0:"🥇", 1:"🥈", 2:"🥉"}
                max_val = lb[sort_col].max() if sort_col in lb.columns else 1
                _lb_html = ""
                for i, (_, row) in enumerate(lb.iterrows()):
                    medal   = medal_map.get(i, f"#{i+1}")
                    bar_pct = int(row.get(sort_col, 0) / max(max_val, 1) * 100)
                    bar_col = "#FFD700" if i==0 else "#C0C0C0" if i==1 else "#CD7F32" if i==2 else "#4A90D9"
                    fights  = f"{int(row.get('Fights', 0)):,}"
                    negs    = f"{int(row.get('Negotiations', 0)):,}"
                    total   = f"{int(row.get('Total', 0)):,}"
                    av      = get_avatar_html(row['Player'], size=36) if i < 5 else ""
                    _lb_html += (
                        '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;'
                        'padding:12px 16px;margin-bottom:6px;">'
                        '<div style="display:flex;align-items:center;justify-content:space-between;">'
                        '<div style="display:flex;align-items:center;gap:10px;">'
                        f'<span style="font-size:1.1rem;min-width:28px;">{medal}</span>'
                        + av +
                        f'<span style="color:#E8E8E8;font-weight:700;font-size:0.95rem;">{row["Player"]}</span>'
                        '</div>'
                        '<div style="display:flex;gap:20px;">'
                        '<div style="text-align:right;">'
                        '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">Fights</div>'
                        f'<div style="color:#FFD700;font-weight:700;">{fights}</div>'
                        '</div>'
                        '<div style="text-align:right;">'
                        '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">Negs</div>'
                        f'<div style="color:#4A90D9;font-weight:700;">{negs}</div>'
                        '</div>'
                        '<div style="text-align:right;">'
                        '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">Total</div>'
                        f'<div style="color:#2ECC71;font-weight:700;">{total}</div>'
                        '</div>'
                        '</div>'
                        '</div>'
                        '<div style="background:#0E1117;border-radius:4px;height:4px;margin-top:8px;">'
                        f'<div style="background:{bar_col};width:{bar_pct}%;height:4px;border-radius:4px;"></div>'
                        '</div>'
                        '</div>'
                    )
                st.markdown(_lb_html, unsafe_allow_html=True)

        with tab_charts:
            chart_season = st.selectbox("Season for charts", ["Latest"] + seasons_list, key="gbg_chart_season")
            ca = None if chart_season == "Latest" else chart_season
            top_n = st.slider("Show top N players", 5, 40, 20, key="gbg_topn")
            st.plotly_chart(gbg_fights_leaderboard(gbg_df_curr, season=ca, top_n=top_n), width="stretch")
            st.plotly_chart(gbg_total_contribution_chart(gbg_df_curr, season=ca, top_n=top_n), width="stretch")
            st.plotly_chart(gbg_guild_trend(gbg_totals(gbg_df_curr)), width="stretch")

        with tab_comp:
            comp = gbg_season_comparison(gbg_df_curr)
            if comp.empty:
                st.info("Need at least 2 seasons for comparison.")
            else:
                s_curr = comp["season_current"].iloc[0]
                s_prev = comp["season_previous"].iloc[0]
                st.markdown(f'<div class="section-title">📊 {s_curr} vs {s_prev}</div>', unsafe_allow_html=True)
                _sort_opt = st.selectbox(
                    "Sort by",
                    ["Ranking (most fights)", "Most increase in fights", "Biggest % increase"],
                    key="gbg_comp_sort",
                )
                display = comp[["Player", "Fights_previous", "Fights_current",
                                "Fights_change", "Fights_pct"]].copy()
                display.columns = ["Player", "prev", "curr", "delta", "pct"]
                if _sort_opt == "Most increase in fights":
                    display = display.sort_values("delta", ascending=False).reset_index(drop=True)
                elif _sort_opt == "Biggest % increase":
                    display = display.sort_values("pct", ascending=False).reset_index(drop=True)
                else:
                    display = display.sort_values("curr", ascending=False).reset_index(drop=True)
                max_curr = display["curr"].max() if not display.empty else 1
                _comp_html = ""
                for i, (_, row) in enumerate(display.iterrows()):
                    delta_v = int(row["delta"])
                    pct_v   = float(row["pct"])
                    sign    = "+" if delta_v >= 0 else ""
                    d_col   = "#2ECC71" if delta_v >= 0 else "#E74C3C"
                    bar_pct = int(row["curr"] / max(max_curr, 1) * 100)
                    medal   = {0:"🥇",1:"🥈",2:"🥉"}.get(i, f"#{i+1}")
                    av      = get_avatar_html(row['Player'], size=36) if i < 5 else ""
                    prev_v  = f"{int(row['prev']):,}"
                    curr_v  = f"{int(row['curr']):,}"
                    _comp_html += (
                        '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;'
                        'padding:12px 16px;margin-bottom:6px;">'
                        '<div style="display:flex;align-items:center;justify-content:space-between;">'
                        '<div style="display:flex;align-items:center;gap:10px;">'
                        f'<span style="font-size:1.0rem;min-width:28px;">{medal}</span>'
                        + av +
                        f'<span style="color:#E8E8E8;font-weight:700;font-size:0.95rem;">{row["Player"]}</span>'
                        '</div>'
                        '<div style="display:flex;gap:20px;align-items:center;">'
                        '<div style="text-align:right;">'
                        f'<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">{s_prev}</div>'
                        f'<div style="color:#C8CBD8;font-weight:600;">{prev_v}</div>'
                        '</div>'
                        '<div style="text-align:right;">'
                        f'<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">{s_curr}</div>'
                        f'<div style="color:#FFD700;font-weight:700;">{curr_v}</div>'
                        '</div>'
                        '<div style="text-align:right;min-width:80px;">'
                        '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">Change</div>'
                        f'<div style="color:{d_col};font-weight:700;">{sign}{delta_v:,} ({sign}{pct_v:.1f}%)</div>'
                        '</div>'
                        '</div>'
                        '</div>'
                        '<div style="background:#0E1117;border-radius:4px;height:4px;margin-top:8px;">'
                        f'<div style="background:#4A90D9;width:{bar_pct}%;height:4px;border-radius:4px;"></div>'
                        '</div>'
                        '</div>'
                    )
                st.markdown(_comp_html, unsafe_allow_html=True)
                st.plotly_chart(
                    comparison_waterfall(comp, "Fights", f"GBG Fights: {s_curr} vs {s_prev}"),
                    width="stretch",
                )

        with tab_cumu:
            st.markdown('<div class="section-title">📦 Cumulative Fights (Current Players)</div>', unsafe_allow_html=True)
            cumu = hide_pid(get_cumulative_fights(gbg_df_curr))
            if not cumu.empty:
                max_cumu = cumu["cumulative_fights"].max() if "cumulative_fights" in cumu.columns else 1
                _cumu_html = ""
                for i, (_, row) in enumerate(cumu.iterrows()):
                    bar_pct  = int(row.get("cumulative_fights", 0) / max(max_cumu, 1) * 100)
                    bar_col  = "#FFD700" if i==0 else "#C0C0C0" if i==1 else "#CD7F32" if i==2 else "#4A90D9"
                    medal    = {0:"🥇",1:"🥈",2:"🥉"}.get(i, f"#{i+1}")
                    av       = get_avatar_html(row['Player'], size=36) if i < 5 else ""
                    cumu_val = f"{int(row.get('cumulative_fights', 0)):,}"
                    _cumu_html += (
                        '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;'
                        'padding:12px 16px;margin-bottom:6px;">'
                        '<div style="display:flex;align-items:center;justify-content:space-between;">'
                        '<div style="display:flex;align-items:center;gap:10px;">'
                        f'<span style="font-size:1.0rem;min-width:28px;">{medal}</span>'
                        + av +
                        f'<span style="color:#E8E8E8;font-weight:700;font-size:0.95rem;">{row["Player"]}</span>'
                        '</div>'
                        '<div style="text-align:right;">'
                        '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">All-Time Fights</div>'
                        f'<div style="color:#FFD700;font-weight:800;font-size:1rem;">{cumu_val}</div>'
                        '</div>'
                        '</div>'
                        '<div style="background:#0E1117;border-radius:4px;height:4px;margin-top:8px;">'
                        f'<div style="background:{bar_col};width:{bar_pct}%;height:4px;border-radius:4px;"></div>'
                        '</div>'
                        '</div>'
                    )
                st.markdown(_cumu_html, unsafe_allow_html=True)
    _render_footer()


# ══════════════════════════════════════════════════════════════════════════
# PAGE: QI
# ══════════════════════════════════════════════════════════════════════════
elif page == "🌀 QI":
    log_event(st.session_state.get("current_user",""), "QI", "visit")
    st.markdown(f'<h1>{qi_icon(32)} Quantum Incursions (QI)</h1>', unsafe_allow_html=True)

    if qi_df.empty:
        st.info("No QI data yet. Import a season in **📥 Data Import**.")
    else:
        # Filter to current players only
        _current_pids_qi = set(qi_df[qi_df["season"] == sort_seasons(qi_df["season"].unique().tolist())[-1]]["Player_ID"].astype(str))
        qi_df_curr = qi_df[qi_df["Player_ID"].astype(str).isin(_current_pids_qi)]

        qi_seasons_list = sort_seasons(get_all_seasons()["qi"], descending=True)
        tab_lb, tab_charts, tab_comp, tab_cumu = st.tabs(
            ["🏅 Leaderboard", "📊 Charts", "📈 Season Comparison", "📦 Cumulative"]
        )

        with tab_lb:
            col_s, col_sort = st.columns([2, 2])
            with col_s:
                qi_sel = st.selectbox("Season", ["Latest"] + qi_seasons_list, key="qi_lb_season")
            with col_sort:
                qi_sort = st.selectbox("Sort by", ["Progress", "Actions"], key="qi_sort")
            qi_season_arg = None if qi_sel == "Latest" else qi_sel
            qi_lb = hide_pid(qi_leaderboard(qi_df_curr, season=qi_season_arg, sort_by=qi_sort))
            if not qi_lb.empty:
                medal_map = {0:"🥇", 1:"🥈", 2:"🥉"}
                max_val = qi_lb[qi_sort].max() if qi_sort in qi_lb.columns else 1
                _qi_lb_html = ""
                for i, (_, row) in enumerate(qi_lb.iterrows()):
                    medal   = medal_map.get(i, f"#{i+1}")
                    bar_pct = int(row.get(qi_sort, 0) / max(max_val, 1) * 100)
                    bar_col = "#FFD700" if i==0 else "#C0C0C0" if i==1 else "#CD7F32" if i==2 else "#9B59B6"
                    prog    = f"{int(row.get('Progress', 0)):,}"
                    acts    = f"{int(row.get('Actions', 0)):,}"
                    av      = get_avatar_html(row['Player'], size=36) if i < 5 else ""
                    _qi_lb_html += (
                        '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;'
                        'padding:12px 16px;margin-bottom:6px;">'
                        '<div style="display:flex;align-items:center;justify-content:space-between;">'
                        '<div style="display:flex;align-items:center;gap:10px;">'
                        f'<span style="font-size:1.1rem;min-width:28px;">{medal}</span>'
                        + av +
                        f'<span style="color:#E8E8E8;font-weight:700;font-size:0.95rem;">{row["Player"]}</span>'
                        '</div>'
                        '<div style="display:flex;gap:20px;">'
                        '<div style="text-align:right;">'
                        '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">Progress</div>'
                        f'<div style="color:#FFD700;font-weight:700;">{prog}</div>'
                        '</div>'
                        '<div style="text-align:right;">'
                        '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">Actions</div>'
                        f'<div style="color:#9B59B6;font-weight:700;">{acts}</div>'
                        '</div>'
                        '</div>'
                        '</div>'
                        '<div style="background:#0E1117;border-radius:4px;height:4px;margin-top:8px;">'
                        f'<div style="background:{bar_col};width:{bar_pct}%;height:4px;border-radius:4px;"></div>'
                        '</div>'
                        '</div>'
                    )
                st.markdown(_qi_lb_html, unsafe_allow_html=True)

        with tab_charts:
            qi_chart_s = st.selectbox("Season for charts", ["Latest"] + qi_seasons_list, key="qi_chart_season")
            qi_ca = None if qi_chart_s == "Latest" else qi_chart_s
            qi_top_n = st.slider("Show top N players", 5, 40, 20, key="qi_topn")
            st.plotly_chart(qi_progress_leaderboard(qi_df_curr, season=qi_ca, top_n=qi_top_n), width="stretch")
            st.plotly_chart(qi_guild_trend(qi_totals(qi_df_curr)), width="stretch")

        with tab_comp:
            qi_comp = qi_season_comparison(qi_df_curr)
            if qi_comp.empty:
                st.info("Need at least 2 seasons for comparison.")
            else:
                qi_s_curr = qi_comp["season_current"].iloc[0]
                qi_s_prev = qi_comp["season_previous"].iloc[0]
                st.markdown(f'<div class="section-title">📊 {qi_s_curr} vs {qi_s_prev}</div>', unsafe_allow_html=True)
                _qi_sort_opt = st.selectbox(
                    "Sort by",
                    ["Ranking (most progress)", "Most increase in progress", "Biggest % increase"],
                    key="qi_comp_sort",
                )
                qi_display = qi_comp[["Player", "Progress_previous", "Progress_current",
                                      "Progress_change", "Progress_pct"]].copy()
                qi_display.columns = ["Player", "prev", "curr", "delta", "pct"]
                if _qi_sort_opt == "Most increase in progress":
                    qi_display = qi_display.sort_values("delta", ascending=False).reset_index(drop=True)
                elif _qi_sort_opt == "Biggest % increase":
                    qi_display = qi_display.sort_values("pct", ascending=False).reset_index(drop=True)
                else:
                    qi_display = qi_display.sort_values("curr", ascending=False).reset_index(drop=True)
                max_curr = qi_display["curr"].max() if not qi_display.empty else 1
                _qi_comp_html = ""
                for i, (_, row) in enumerate(qi_display.iterrows()):
                    delta_v = int(row["delta"])
                    pct_v   = float(row["pct"])
                    sign    = "+" if delta_v >= 0 else ""
                    d_col   = "#2ECC71" if delta_v >= 0 else "#E74C3C"
                    bar_pct = int(row["curr"] / max(max_curr, 1) * 100)
                    medal   = {0:"🥇",1:"🥈",2:"🥉"}.get(i, f"#{i+1}")
                    av      = get_avatar_html(row['Player'], size=36) if i < 5 else ""
                    prev_v  = f"{int(row['prev']):,}"
                    curr_v  = f"{int(row['curr']):,}"
                    _qi_comp_html += (
                        '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;'
                        'padding:12px 16px;margin-bottom:6px;">'
                        '<div style="display:flex;align-items:center;justify-content:space-between;">'
                        '<div style="display:flex;align-items:center;gap:10px;">'
                        f'<span style="font-size:1.0rem;min-width:28px;">{medal}</span>'
                        + av +
                        f'<span style="color:#E8E8E8;font-weight:700;font-size:0.95rem;">{row["Player"]}</span>'
                        '</div>'
                        '<div style="display:flex;gap:20px;align-items:center;">'
                        '<div style="text-align:right;">'
                        f'<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">{qi_s_prev}</div>'
                        f'<div style="color:#C8CBD8;font-weight:600;">{prev_v}</div>'
                        '</div>'
                        '<div style="text-align:right;">'
                        f'<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">{qi_s_curr}</div>'
                        f'<div style="color:#FFD700;font-weight:700;">{curr_v}</div>'
                        '</div>'
                        '<div style="text-align:right;min-width:80px;">'
                        '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">Change</div>'
                        f'<div style="color:{d_col};font-weight:700;">{sign}{delta_v:,} ({sign}{pct_v:.1f}%)</div>'
                        '</div>'
                        '</div>'
                        '</div>'
                        '<div style="background:#0E1117;border-radius:4px;height:4px;margin-top:8px;">'
                        f'<div style="background:#9B59B6;width:{bar_pct}%;height:4px;border-radius:4px;"></div>'
                        '</div>'
                        '</div>'
                    )
                st.markdown(_qi_comp_html, unsafe_allow_html=True)
                st.plotly_chart(
                    comparison_waterfall(qi_comp, "Progress", f"QI Progress: {qi_s_curr} vs {qi_s_prev}"),
                    width="stretch",
                )

        with tab_cumu:
            st.markdown('<div class="section-title">📦 Cumulative Progress (Current Players)</div>', unsafe_allow_html=True)
            qi_cumu = hide_pid(get_cumulative_progress(qi_df_curr))
            if not qi_cumu.empty:
                max_cumu = qi_cumu["cumulative_progress"].max() if "cumulative_progress" in qi_cumu.columns else 1
                _qi_cumu_html = ""
                for i, (_, row) in enumerate(qi_cumu.iterrows()):
                    bar_pct  = int(row.get("cumulative_progress", 0) / max(max_cumu, 1) * 100)
                    bar_col  = "#FFD700" if i==0 else "#C0C0C0" if i==1 else "#CD7F32" if i==2 else "#9B59B6"
                    medal    = {0:"🥇",1:"🥈",2:"🥉"}.get(i, f"#{i+1}")
                    av       = get_avatar_html(row['Player'], size=36) if i < 5 else ""
                    cumu_val = f"{int(row.get('cumulative_progress', 0)):,}"
                    _qi_cumu_html += (
                        '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;'
                        'padding:12px 16px;margin-bottom:6px;">'
                        '<div style="display:flex;align-items:center;justify-content:space-between;">'
                        '<div style="display:flex;align-items:center;gap:10px;">'
                        f'<span style="font-size:1.0rem;min-width:28px;">{medal}</span>'
                        + av +
                        f'<span style="color:#E8E8E8;font-weight:700;font-size:0.95rem;">{row["Player"]}</span>'
                        '</div>'
                        '<div style="text-align:right;">'
                        '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">All-Time Progress</div>'
                        f'<div style="color:#FFD700;font-weight:800;font-size:1rem;">{cumu_val}</div>'
                        '</div>'
                        '</div>'
                        '<div style="background:#0E1117;border-radius:4px;height:4px;margin-top:8px;">'
                        f'<div style="background:{bar_col};width:{bar_pct}%;height:4px;border-radius:4px;"></div>'
                        '</div>'
                        '</div>'
                    )
                st.markdown(_qi_cumu_html, unsafe_allow_html=True)
    _render_footer()


# ══════════════════════════════════════════════════════════════════════════
# PAGE: PLAYER PROFILES
# ══════════════════════════════════════════════════════════════════════════
elif page == "👤 Player Profiles":
    log_event(st.session_state.get("current_user",""), "Player Profiles", "visit")
    st.markdown("""<style>
.strip-wrap { position: relative; }
.strip-tooltip {
    display: none;
    position: absolute;
    top: 6px;
    left: 50%;
    transform: translateX(-50%);
    background: #1A1D27;
    border: 1px solid #2A2D3A;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 0.72rem;
    color: #E8E8E8;
    white-space: nowrap;
    z-index: 10;
    pointer-events: none;
}
.strip-wrap:hover .strip-tooltip { display: block; }
</style>""", unsafe_allow_html=True)
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">'
        f'{icon_html("player_profiles_icon.svg", 32)}'
        f'<span style="font-size:1.8rem;font-weight:800;color:#E8E8E8;">Player Profiles</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    players = _load_all_players(gbg_df, qi_df, members_df)
    current_players = players["current"]
    former_players  = players["former"]

    # Last-seen map for all cards on this page (loaded once)
    import datetime as _dt_pp
    _pp_ls_map = get_last_seen(days=365)

    def _make_ls_badge(player_name, size="0.68rem"):
        _ls_dt = _pp_ls_map.get(str(player_name))
        if not _ls_dt:
            return ""
        _d = (_dt_pp.datetime.utcnow() - _ls_dt).days
        if _d == 0:
            _bg, _cl, _lbl = "#1A3A1A", "#2ECC71", "👁 today"
        elif _d <= 3:
            _bg, _cl, _lbl = "#3A2A1A", "#F39C12", f"👁 {_d}d ago"
        else:
            _bg, _cl, _lbl = "#1A1D27", "#A8ABB8", f"👁 {_d}d ago"
        return (
            f'<span style="background:{_bg};color:{_cl};border:1px solid {_cl}55;'
            f'padding:1px 7px;border-radius:20px;font-size:{size};font-weight:600;">'
            f'{_lbl}</span>'
        )

    if current_players.empty and former_players.empty:
        st.info("No player data found. Import seasons first.")
    else:
        # ── Filter bar ───────────────────────────────────────────────────
        # Search
        search = st.text_input("Search", placeholder="Search players...",
                               label_visibility="collapsed")

        fc1, fc2 = st.columns(2)

        # Status pills
        with fc1:
            _status_opts = ["All", "Current", "Former"]
            _status = st.radio("Status", _status_opts, horizontal=True,
                               key="pp_status", label_visibility="collapsed")

        # Sort-by pills
        with fc2:
            _sort_opts = ["Points", "Name", "GBG Fights", "QI Progress", "Rank"]
            _sort_by = st.radio("Sort by", _sort_opts, horizontal=True,
                                key="pp_sort", label_visibility="collapsed")

        def _sort_df(df):
            if df.empty:
                return df
            if _sort_by == "Name":
                return df.sort_values("Player", ascending=True).reset_index(drop=True)
            if _sort_by == "Rank":
                def _get_rank(pid):
                    m = get_latest_member_stats(members_df, str(pid))
                    return m.get("rank", 9999) if m else 9999
                df = df.copy()
                df["_rank"] = df["Player_ID"].apply(_get_rank)
                return df.sort_values("_rank").drop(columns=["_rank"]).reset_index(drop=True)
            if _sort_by == "GBG Fights":
                if gbg_df.empty:
                    return df
                from modules.comparisons import sort_seasons as _ss_sort
                _ls = _ss_sort(gbg_df["season"].unique().tolist())[-1]
                _ftotals = (gbg_df[gbg_df["season"] == _ls]
                            .groupby("Player_ID")["Fights"].sum()
                            .reset_index())
                df = df.copy()
                df["Player_ID"] = df["Player_ID"].astype(str)
                _ftotals["Player_ID"] = _ftotals["Player_ID"].astype(str)
                df = df.merge(_ftotals, on="Player_ID", how="left").fillna({"Fights": 0})
                return df.sort_values("Fights", ascending=False).drop(columns=["Fights"]).reset_index(drop=True)
            if _sort_by == "QI Progress":
                if qi_df.empty:
                    return df
                from modules.comparisons import sort_seasons as _ss_sort
                _ls = _ss_sort(qi_df["season"].unique().tolist())[-1]
                _qtotals = (qi_df[qi_df["season"] == _ls]
                            .groupby("Player_ID")["Progress"].sum()
                            .reset_index())
                df = df.copy()
                df["Player_ID"] = df["Player_ID"].astype(str)
                _qtotals["Player_ID"] = _qtotals["Player_ID"].astype(str)
                df = df.merge(_qtotals, on="Player_ID", how="left").fillna({"Progress": 0})
                return df.sort_values("Progress", ascending=False).drop(columns=["Progress"]).reset_index(drop=True)
            # Default: Points (already sorted by points desc from get_all_players)
            return df

        def filter_players(df):
            result = df.copy()
            if search:
                result = result[result["Player"].str.contains(search, case=False, na=False)]
            return _sort_df(result)

        curr_filtered   = filter_players(current_players) if _status != "Former"  else pd.DataFrame()
        former_filtered = filter_players(former_players)  if _status != "Current" else pd.DataFrame()

        def render_player_grid(df, is_former=False):
            if df.empty:
                return

            # Era colour map
            _era_colours = {
                "SAAB": "#E74C3C", "SASH": "#9B59B6", "CATH": "#3498DB",
                "INDU": "#E67E22", "PROG": "#2ECC71", "CONT": "#F39C12",
                "GILD": "#FFD700", "VIRT": "#1ABC9C", "OCEA": "#2980B9",
                "TOMO": "#8E44AD", "FUTU": "#16A085",
            }

            # Pre-compute latest GBG and QI season names for activity lookup
            from modules.comparisons import sort_seasons as _ss_grid
            _latest_gbg_s = _ss_grid(gbg_df["season"].unique().tolist())[-1] if not gbg_df.empty else None
            _latest_qi_s  = _ss_grid(qi_df["season"].unique().tolist())[-1]  if not qi_df.empty  else None

            cols_per_row = 2
            for i in range(0, len(df), cols_per_row):
                row_df = df.iloc[i:i+cols_per_row]
                cols = st.columns(cols_per_row)
                for col, (_, prow) in zip(cols, row_df.iterrows()):
                    with col:
                        pid     = str(prow["Player_ID"])
                        has_gbg = not gbg_df.empty and pid in gbg_df["Player_ID"].astype(str).values
                        has_qi  = not qi_df.empty  and pid in qi_df["Player_ID"].astype(str).values

                        avatar_html = get_avatar_html(prow["Player"], size=68)
                        former_tag  = '<span class="former-badge">LEFT GUILD</span>' if is_former else ""

                        # Member stats
                        mem      = get_latest_member_stats(members_df, pid)
                        pts      = mem.get("points", 0)       if mem else 0
                        era      = mem.get("eraName", "")     if mem else ""
                        wb       = mem.get("won_battles", 0)  if mem else 0
                        gg       = mem.get("guildgoods", 0)   if mem else 0
                        rank_num = mem.get("rank", 0)         if mem else 0

                        # Last seen badge
                        _ls_badge = _make_ls_badge(prow["Player"])

                        # Season wins
                        wins_row = wins_df[wins_df["Player_ID"] == pid] if not wins_df.empty else pd.DataFrame()
                        gbg_wins = int(wins_row["gbg_wins"].iloc[0]) if not wins_row.empty else 0
                        qi_wins  = int(wins_row["qi_wins"].iloc[0])  if not wins_row.empty else 0

                        # Latest season activity
                        _last_fights = 0
                        _last_qi     = 0
                        if _latest_gbg_s:
                            _f_row = gbg_df[(gbg_df["Player_ID"].astype(str) == pid) &
                                            (gbg_df["season"] == _latest_gbg_s)]
                            _last_fights = int(_f_row["Fights"].sum()) if not _f_row.empty else 0
                        if _latest_qi_s:
                            _q_row = qi_df[(qi_df["Player_ID"].astype(str) == pid) &
                                           (qi_df["season"] == _latest_qi_s)]
                            _last_qi = int(_q_row["Progress"].sum()) if not _q_row.empty else 0

                        # Status strip colour
                        _gbg_ok = _last_fights >= 1000 or not has_gbg
                        _qi_ok  = _last_qi >= 3000    or not has_qi
                        if _gbg_ok and _qi_ok:
                            _strip_col = "#2ECC71"
                        elif _gbg_ok or _qi_ok:
                            _strip_col = "#F39C12"
                        else:
                            _strip_col = "#E74C3C"
                        if is_former:
                            _strip_col = "#3A3D4A"

                        # Era pill
                        _era_col   = _era_colours.get(era[:4].upper(), "#4A90D9") if era else "#4A90D9"
                        _era_pill  = (
                            f'<span style="background:{_era_col}22;color:{_era_col};'
                            f'border:1px solid {_era_col}55;padding:1px 8px;border-radius:20px;'
                            f'font-size:0.72rem;font-weight:700;">{era}</span>'
                        ) if era else ""

                        # Rank badge
                        _rank_badge = (
                            f'<span style="background:#0E1117;color:#C8CBD8;'
                            f'border:1px solid #2A2D3A;padding:1px 7px;border-radius:20px;'
                            f'font-size:0.72rem;font-weight:600;">#{rank_num}</span>'
                        ) if rank_num else ""

                        # Medal badges
                        _medal_html = ""
                        if gbg_wins > 0:
                            _medal_html += f'<span style="background:#2A2000;color:#FFD700;padding:2px 7px;border-radius:20px;font-size:0.72rem;font-weight:700;">🥇{gbg_wins}×GBG</span> '
                        if qi_wins > 0:
                            _medal_html += f'<span style="background:#1A1A2A;color:#C0C0C0;padding:2px 7px;border-radius:20px;font-size:0.72rem;font-weight:700;">🥇{qi_wins}×QI</span>'

                        # Activity badges (last season)
                        _act_gbg = ""
                        _act_qi  = ""
                        if has_gbg and _latest_gbg_s:
                            _fc = "#2ECC71" if _last_fights >= 1000 else "#E74C3C"
                            _act_gbg = (
                                f'<div style="text-align:center;">'
                                f'<div style="color:#C8CBD8;font-size:0.6rem;text-transform:uppercase;'
                                f'letter-spacing:0.5px;">GBG</div>'
                                f'<div style="color:{_fc};font-weight:800;font-size:0.88rem;">{_last_fights:,}</div>'
                                f'</div>'
                            )
                        if has_qi and _latest_qi_s:
                            _qc = "#9B59B6" if _last_qi >= 3000 else "#E74C3C"
                            _act_qi = (
                                f'<div style="text-align:center;">'
                                f'<div style="color:#C8CBD8;font-size:0.6rem;text-transform:uppercase;'
                                f'letter-spacing:0.5px;">QI</div>'
                                f'<div style="color:{_qc};font-weight:800;font-size:0.88rem;">{_last_qi:,}</div>'
                                f'</div>'
                            )

                        _card_bg  = "#161820" if is_former else "#1A1D27"
                        _card_bdr = "#3A2A2A" if is_former else "#2A2D3A"
                        _opacity  = "opacity:0.78;" if is_former else ""
                        _name_col = "#C8CBD8" if is_former else "#F0F0F0"

                        _pts_html = (
                            '<div style="color:#FFD700;font-size:1.5rem;font-weight:900;'
                            'line-height:1;margin-bottom:4px;">' + f"{pts:,}" +
                            '<span style="color:#C8CBD8;font-size:0.7rem;font-weight:400;'
                            'margin-left:4px;">pts</span></div>'
                        ) if pts else ""

                        _rank_top = (
                            '<div style="color:#A8ABB8;font-size:0.78rem;font-weight:700;">'
                            '#' + str(rank_num) + '</div>'
                        ) if rank_num else ""

                        # Assemble full card HTML as a single string — no multiline f-string
                        _card_html = (
                            '<div style="background:' + _card_bg + ';border:1px solid ' + _card_bdr + ';'
                            'border-radius:14px;margin-bottom:10px;overflow:hidden;' + _opacity +
                            'box-shadow:0 2px 8px rgba(0,0,0,0.3);">'
                            '<div style="height:4px;background:' + _strip_col + ';width:100%;"></div>'
                            '<div style="padding:16px 18px;">'
                              '<div style="display:flex;align-items:flex-start;gap:14px;">'
                                + avatar_html +
                                '<div style="flex:1;min-width:0;">'
                                  '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:5px;margin-bottom:5px;">'
                                    '<span style="color:' + _name_col + ';font-weight:800;font-size:1.08rem;line-height:1.2;">' + prow['Player'] + '</span>'
                                    + _ls_badge + former_tag +
                                  '</div>'
                                  '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;margin-bottom:8px;">'
                                    + _era_pill + _rank_badge + _medal_html +
                                  '</div>'
                                  + _pts_html +
                                '</div>'
                                '<div style="text-align:right;min-width:32px;">' + _rank_top + '</div>'
                              '</div>'
                              '<div style="display:flex;gap:16px;margin-top:6px;padding-top:10px;border-top:1px solid ' + _card_bdr + ';">'
                                '<div style="flex:1;display:flex;gap:16px;flex-wrap:wrap;">'
                                  '<div>'
                                    '<div style="color:#C8CBD8;font-size:0.6rem;text-transform:uppercase;letter-spacing:0.5px;">Battles</div>'
                                    '<div style="color:#2ECC71;font-weight:700;font-size:0.82rem;">' + f"{wb:,}" + '</div>'
                                  '</div>'
                                  '<div>'
                                    '<div style="color:#C8CBD8;font-size:0.6rem;text-transform:uppercase;letter-spacing:0.5px;">Goods</div>'
                                    '<div style="color:#4A90D9;font-weight:700;font-size:0.82rem;">' + f"{gg:,}" + '</div>'
                                  '</div>'
                                '</div>'
                                '<div style="display:flex;gap:14px;">' + _act_gbg + _act_qi + '</div>'
                              '</div>'
                            '</div>'
                            '</div>'
                        )
                        st.markdown(_card_html, unsafe_allow_html=True)

                        if st.button("View Profile", key=f"btn_{pid}"):
                            st.session_state.selected_player = pid
                            st.rerun()

        # ── Profile view or grid ──────────────────────────────────────────
        if st.session_state.selected_player is None:
            total = len(curr_filtered) + len(former_filtered)
            st.markdown(f"**{total} players found**")

            # Current members
            if not curr_filtered.empty:
                render_player_grid(curr_filtered, is_former=False)

            # Former members
            if not former_filtered.empty:
                st.markdown(
                    '<div class="former-section-header">🚪 Previous Guild Members</div>',
                    unsafe_allow_html=True,
                )
                st.caption("These players do not appear in the latest season data. Records are kept for if they rejoin.")
                render_player_grid(former_filtered, is_former=True)

        else:
            # ── Individual profile ────────────────────────────────────────
            _components.html("<script>setTimeout(function(){ window.parent.scrollTo({top:0,behavior:'instant'}); }, 150);</script>", height=0)
            pid = st.session_state.selected_player
            if st.button("← Back to Players"):
                st.session_state.selected_player = None
                st.rerun()

            profile     = get_player_profile(pid, gbg_df, qi_df, members_df)
            log_event(st.session_state.get("current_user",""), "Player Profiles", f"viewed:{profile['player_name']}")
            avatar_html = get_avatar_html(profile["player_name"], size=90)
            is_former_p = profile["is_former"]

            mem      = profile.get("member_stats", {})
            wins     = profile.get("wins", {})
            gbg_w    = wins.get("gbg_wins", 0)
            qi_w     = wins.get("qi_wins", 0)
            pts      = mem.get("points", 0)       if mem else 0
            era      = mem.get("eraName", "")     if mem else ""
            wb       = mem.get("won_battles", 0)  if mem else 0
            gg       = mem.get("guildgoods", 0)   if mem else 0
            rank_num = mem.get("rank", 0)         if mem else 0
            snap_str = str(mem.get("snapshot", "")) if mem else ""
            snap_str = snap_str if snap_str and snap_str != "nan" else ""

            # ── Safe defaults — ensure all variables exist regardless of data ──
            from modules.comparisons import sort_seasons as _ss_trend
            _p_gbg_s    = None
            _p_qi_s     = None
            _p_fights   = 0
            _p_qi_val   = 0
            _fc_p       = "#C8CBD8"
            _qc_p       = "#C8CBD8"
            _trend_gbg  = ""
            _trend_qi   = ""
            _pb_gbg     = 0
            _pb_qi      = 0
            _pb_gbg_html = ""
            _pb_qi_html  = ""
            _seasons_html = ""
            _consist_html = ""
            _achieve_row  = ""
            _achieve_badges = []
            _guild_stats_html      = ""
            _mil_html              = ""
            _prod_tab_html         = ""
            _boost_percentile_badge = ""
            _crit_pill_p = ""
            _ls_badge_p = ""
            _sorted_gbg = []
            _sorted_qi  = []

            # Latest season activity
            from modules.comparisons import sort_seasons as _ss_prof
            _p_gbg_s = _ss_prof(gbg_df["season"].unique().tolist())[-1] if not gbg_df.empty else None
            _p_qi_s  = _ss_prof(qi_df["season"].unique().tolist())[-1]  if not qi_df.empty  else None
            _p_fights = 0
            _p_qi_val = 0
            if _p_gbg_s:
                _pf = gbg_df[(gbg_df["Player_ID"].astype(str) == pid) & (gbg_df["season"] == _p_gbg_s)]
                _p_fights = int(_pf["Fights"].sum()) if not _pf.empty else 0
            if _p_qi_s:
                _pq = qi_df[(qi_df["Player_ID"].astype(str) == pid) & (qi_df["season"] == _p_qi_s)]
                _p_qi_val = int(_pq["Progress"].sum()) if not _pq.empty else 0

            # Status strip
            _has_gbg_p = not gbg_df.empty and pid in gbg_df["Player_ID"].astype(str).values
            _has_qi_p  = not qi_df.empty  and pid in qi_df["Player_ID"].astype(str).values
            _gbg_ok_p  = _p_fights >= 1000 or not _has_gbg_p
            _qi_ok_p   = _p_qi_val >= 3000  or not _has_qi_p
            if is_former_p:
                _strip_p = "#3A3D4A"
            elif _gbg_ok_p and _qi_ok_p:
                _strip_p = "#2ECC71"
            elif _gbg_ok_p or _qi_ok_p:
                _strip_p = "#F39C12"
            else:
                _strip_p = "#E74C3C"

            if _strip_p == "#2ECC71":
                _strip_label = "✅ Meeting all minimums"
            elif _strip_p == "#F39C12":
                _strip_label = "⚠️ Partially meeting minimums"
            elif _strip_p == "#E74C3C":
                _strip_label = "❌ Below minimum requirements"
            else:
                _strip_label = "👤 Former member"

            # Era pill
            _era_colours_p = {
                "SAAB":"#E74C3C","SASH":"#9B59B6","CATH":"#3498DB",
                "INDU":"#E67E22","PROG":"#2ECC71","CONT":"#F39C12",
                "GILD":"#FFD700","VIRT":"#1ABC9C","OCEA":"#2980B9",
                "TOMO":"#8E44AD","FUTU":"#16A085",
            }
            _era_col_p  = _era_colours_p.get(era[:4].upper(), "#4A90D9") if era else "#4A90D9"
            _era_pill_p = (
                '<span style="background:' + _era_col_p + '22;color:' + _era_col_p + ';'
                'border:1px solid ' + _era_col_p + '55;padding:2px 10px;border-radius:20px;'
                'font-size:0.78rem;font-weight:700;">' + era + '</span>'
            ) if era else ""

            _rank_badge_p = (
                '<span style="background:#0E1117;color:#C8CBD8;border:1px solid #2A2D3A;'
                'padding:2px 8px;border-radius:20px;font-size:0.78rem;font-weight:600;">'
                '#' + str(rank_num) + '</span>'
            ) if rank_num else ""

            _medals_p = ""
            if gbg_w > 0:
                _medals_p += '<span style="background:#2A2000;color:#FFD700;padding:2px 9px;border-radius:20px;font-size:0.78rem;font-weight:700;">🥇' + str(gbg_w) + '×GBG</span> '
            if qi_w > 0:
                _medals_p += '<span style="background:#1A1A2A;color:#C0C0C0;padding:2px 9px;border-radius:20px;font-size:0.78rem;font-weight:700;">🥇' + str(qi_w) + '×QI</span>'

            _ls_badge_p   = _make_ls_badge(profile["player_name"], size="0.75rem")
            _former_tag_p = '<span class="former-badge" style="font-size:0.78rem;">LEFT GUILD</span>' if is_former_p else ""
            _name_col_p   = "#C8CBD8" if is_former_p else "#F0F0F0"
            _card_bg_p    = "#161820" if is_former_p else "#1A1D27"
            _card_bdr_p   = "#3A2A2A" if is_former_p else "#2A2D3A"

            # Load persisted Snuggy Bug badges for this player
            try:
                _sb_badges_p = load_player_badges(profile["player_name"])
            except Exception:
                _sb_badges_p = []

            # Points pill with delta vs previous snapshot
            _pts_snap_delta_p = None
            if pid and not members_df.empty and "snapshot" in members_df.columns:
                _snaps_p = sort_seasons(members_df["snapshot"].unique().tolist(), descending=True)
                if len(_snaps_p) >= 2:
                    _prev_snap_p = members_df[members_df["snapshot"] == _snaps_p[1]]
                    _prev_row_p  = _prev_snap_p[_prev_snap_p["Player_ID"].astype(str) == str(pid)]
                    if not _prev_row_p.empty:
                        _prev_pts_p = pd.to_numeric(_prev_row_p["points"].iloc[0], errors="coerce")
                        if pd.notna(_prev_pts_p) and pts:
                            _pts_snap_delta_p = int(pts) - int(_prev_pts_p)

            _pts_p = ""
            if pts:
                _pts_delta_html_p = ""
                if _pts_snap_delta_p is not None:
                    _dc = "#2ECC71" if _pts_snap_delta_p >= 0 else "#E74C3C"
                    _ds = f'+{_pts_snap_delta_p:,}' if _pts_snap_delta_p >= 0 else f'{_pts_snap_delta_p:,}'
                    _pts_delta_html_p = f'<span style="color:{_dc};margin-left:4px;font-size:0.68rem;">{_ds}</span>'
                _pts_p = (
                    f'<span style="background:#2A2A1A;color:#FFD700;border:1px solid #FFD70055;'
                    f'padding:2px 9px;border-radius:20px;font-size:0.78rem;font-weight:700;">'
                    f'{pts:,} pts</span>{_pts_delta_html_p}'
                )

            _fc_p = "#2ECC71" if _p_fights >= 1000 else "#E74C3C"
            _qc_p = "#9B59B6" if _p_qi_val >= 3000 else "#E74C3C"

            _snap_p = (
                '<div style="position:absolute;bottom:12px;right:16px;">'
                '<span style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:20px;'
                'padding:2px 10px;font-size:0.68rem;color:#A8ABB8;">📅 As of: ' + snap_str + '</span>'
                '</div>'
            ) if snap_str else ""

            # ── Achievement badges ────────────────────────────────────────
            _achieve_badges = ""

            # Century Club tier
            _p_total_fights = int(gbg_df[gbg_df["Player_ID"].astype(str) == pid]["Fights"].sum()) if not gbg_df.empty else 0
            if _p_total_fights >= 1_000_000:
                _achieve_badges += '<span style="background:#2A2000;color:#FFD700;border:1px solid #FFD70055;padding:2px 9px;border-radius:20px;font-size:0.75rem;font-weight:700;">💯 1M Club</span> '
            elif _p_total_fights >= 500_000:
                _achieve_badges += '<span style="background:#1A0A2A;color:#9B59B6;border:1px solid #9B59B655;padding:2px 9px;border-radius:20px;font-size:0.75rem;font-weight:700;">💎 500K Club</span> '
            elif _p_total_fights >= 100_000:
                _achieve_badges += '<span style="background:#2A1A1A;color:#E74C3C;border:1px solid #E74C3C55;padding:2px 9px;border-radius:20px;font-size:0.75rem;font-weight:700;">🔥 100K Club</span> '

            # Iron Player — seasons in both GBG and QI
            if not gbg_df.empty and not qi_df.empty:
                _p_gbg_seasons = set(gbg_df[gbg_df["Player_ID"].astype(str) == pid]["season"])
                _p_qi_seasons  = set(qi_df[qi_df["Player_ID"].astype(str) == pid]["season"])
                _iron_count    = len(_p_gbg_seasons & _p_qi_seasons)
                if _iron_count > 0:
                    _achieve_badges += '<span style="background:#0A1A2A;color:#4A90D9;border:1px solid #4A90D955;padding:2px 9px;border-radius:20px;font-size:0.75rem;font-weight:700;">🛡️ ' + str(_iron_count) + ' Iron Seasons</span> '

            # Elite Fighter — seasons with 5000+ fights
            if not gbg_df.empty:
                _elite_count = int((gbg_df[gbg_df["Player_ID"].astype(str) == pid]["Fights"] >= 5000).sum())
                if _elite_count > 0:
                    _achieve_badges += '<span style="background:#2A2000;color:#F39C12;border:1px solid #F39C1255;padding:2px 9px;border-radius:20px;font-size:0.75rem;font-weight:700;display:inline-flex;align-items:center;gap:4px;">' + gbg_icon(14) + str(_elite_count) + ' Elite Seasons</span> '

            # QI Legend — seasons with 10000+ progress
            if not qi_df.empty:
                _legend_count = int((qi_df[qi_df["Player_ID"].astype(str) == pid]["Progress"] >= 10000).sum())
                if _legend_count > 0:
                    _achieve_badges += '<span style="background:#1A0A2A;color:#9B59B6;border:1px solid #9B59B655;padding:2px 9px;border-radius:20px;font-size:0.75rem;font-weight:700;display:inline-flex;align-items:center;gap:4px;">' + qi_icon(14) + str(_legend_count) + ' QI Legend Seasons</span> '

            _achieve_row = ""  # no longer used as a block — pills split into rows below

            # ── Personal bests ────────────────────────────────────────────
            _pb_gbg = 0
            _pb_qi  = 0
            if not gbg_df.empty:
                _pb_val = gbg_df[gbg_df["Player_ID"].astype(str) == pid]["Fights"].max()
                _pb_gbg = int(_pb_val) if pd.notna(_pb_val) else 0
            if not qi_df.empty:
                _pb_val = qi_df[qi_df["Player_ID"].astype(str) == pid]["Progress"].max()
                _pb_qi = int(_pb_val) if pd.notna(_pb_val) else 0

            # ── Consistency score ─────────────────────────────────────────
            _consistency = None
            if not gbg_df.empty and not qi_df.empty:
                _all_gbg_s = set(gbg_df[gbg_df["Player_ID"].astype(str) == pid]["season"])
                _all_qi_s  = set(qi_df[qi_df["Player_ID"].astype(str) == pid]["season"])
                _all_played = _all_gbg_s | _all_qi_s
                if _all_played:
                    _met = 0
                    for _s in _all_played:
                        _sf = gbg_df[(gbg_df["Player_ID"].astype(str) == pid) & (gbg_df["season"] == _s)]["Fights"].sum() if _s in _all_gbg_s else 1000
                        _sq = qi_df[(qi_df["Player_ID"].astype(str) == pid) & (qi_df["season"] == _s)]["Progress"].sum() if _s in _all_qi_s else 3000
                        if int(_sf) >= 1000 and int(_sq) >= 3000:
                            _met += 1
                    _consistency = int(_met / len(_all_played) * 100)

            # ── Trend indicator ───────────────────────────────────────────
            _trend_gbg = ""
            _trend_qi  = ""
            if not gbg_df.empty and len(_p_gbg_seasons) >= 2:
                from modules.comparisons import sort_seasons as _ss_trend
                _sorted_gbg = _ss_trend(list(_p_gbg_seasons))
                if len(_sorted_gbg) >= 2:
                    _prev_s = _sorted_gbg[-2]
                    _prev_f = int(gbg_df[(gbg_df["Player_ID"].astype(str) == pid) & (gbg_df["season"] == _prev_s)]["Fights"].sum())
                    _avg_f  = int(gbg_df[gbg_df["Player_ID"].astype(str) == pid]["Fights"].mean())
                    if _p_fights > _avg_f:
                        _trend_gbg = '<span style="color:#2ECC71;font-size:0.8rem;font-weight:700;margin-left:4px;">↑</span>'
                    elif _p_fights < _avg_f:
                        _trend_gbg = '<span style="color:#E74C3C;font-size:0.8rem;font-weight:700;margin-left:4px;">↓</span>'
                    else:
                        _trend_gbg = '<span style="color:#C8CBD8;font-size:0.8rem;margin-left:4px;">→</span>'

            if not qi_df.empty and len(_p_qi_seasons) >= 2:
                _sorted_qi = _ss_trend(list(_p_qi_seasons))
                if len(_sorted_qi) >= 2:
                    _avg_q = int(qi_df[qi_df["Player_ID"].astype(str) == pid]["Progress"].mean())
                    if _p_qi_val > _avg_q:
                        _trend_qi = '<span style="color:#2ECC71;font-size:0.8rem;font-weight:700;margin-left:4px;">↑</span>'
                    elif _p_qi_val < _avg_q:
                        _trend_qi = '<span style="color:#E74C3C;font-size:0.8rem;font-weight:700;margin-left:4px;">↓</span>'
                    else:
                        _trend_qi = '<span style="color:#C8CBD8;font-size:0.8rem;margin-left:4px;">→</span>'

            # ── Seasons active ────────────────────────────────────────────
            _seasons_active = len(
                set(gbg_df[gbg_df["Player_ID"].astype(str) == pid]["season"].tolist() if not gbg_df.empty else []) |
                set(qi_df[qi_df["Player_ID"].astype(str) == pid]["season"].tolist() if not qi_df.empty else [])
            )

            # ── Bottom stats row ──────────────────────────────────────────
            _consist_html = ""
            if _consistency is not None:
                _cc = "#2ECC71" if _consistency >= 80 else "#F39C12" if _consistency >= 50 else "#E74C3C"
                _circ   = 94.25
                _filled = round(_consistency / 100 * _circ, 2)
                _consist_html = (
                    '<div style="text-align:center;padding:0 12px;">'
                    '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:2px;">Consistency</div>'
                    '<svg width="52" height="52" viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg">'
                    '<circle cx="18" cy="18" r="15" fill="none" stroke="#1A1D27" stroke-width="3"/>'
                    f'<circle cx="18" cy="18" r="15" fill="none" stroke="{_cc}" stroke-width="3" '
                    f'stroke-linecap="round" stroke-dasharray="{_circ}" stroke-dashoffset="{round(_circ - _filled, 2)}" '
                    f'transform="rotate(-90 18 18)"/>'
                    f'<text x="18" y="22" text-anchor="middle" font-size="9" font-weight="700" fill="{_cc}">{_consistency}%</text>'
                    '</svg>'
                    '</div>'
                )

            # ── 3-dot GBG form indicator ──────────────────────────────────
            _form_dots = ""
            if not gbg_df.empty and "season" in gbg_df.columns:
                _p_gbg_all = gbg_df[gbg_df["Player_ID"].astype(str) == pid].copy()
                if not _p_gbg_all.empty:
                    from modules.comparisons import sort_seasons
                    _all_gbg_seasons = sort_seasons(gbg_df["season"].unique().tolist(), descending=True)
                    _last3 = _all_gbg_seasons[:3]
                    _dot_parts = []
                    for _s in reversed(_last3):
                        _s_row = _p_gbg_all[_p_gbg_all["season"] == _s]
                        if _s_row.empty:
                            _dot_col = "#3A3D4A"   # absent — grey
                        else:
                            _s_total = pd.to_numeric(_s_row["Total"], errors="coerce").fillna(0).sum()
                            if _s_total >= 1000:
                                _dot_col = "#2ECC71"  # met minimum — green
                            elif _s_total > 0:
                                _dot_col = "#F39C12"  # participated but below min — amber
                            else:
                                _dot_col = "#E74C3C"  # zero contribution — red
                        _dot_parts.append(
                            f'<div style="width:10px;height:10px;border-radius:50%;background:{_dot_col};'
                            f'flex-shrink:0;" title="{_s}"></div>'
                        )
                    if _dot_parts:
                        _form_dots = (
                            '<div style="display:flex;align-items:center;gap:4px;margin-left:6px;">'
                            + "".join(_dot_parts) +
                            '</div>'
                        )

            _seasons_html = (
                '<div><div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;letter-spacing:1px;">Seasons Active</div>'
                '<div style="color:#E8E8E8;font-size:1rem;font-weight:700;">' + str(_seasons_active) + '</div></div>'
            ) if _seasons_active else ""

            _pb_gbg_html = (
                '<div><div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;letter-spacing:1px;">Best GBG Season</div>'
                '<div style="color:#FFD700;font-size:1rem;font-weight:700;">' + f"{_pb_gbg:,}" + '</div></div>'
            ) if _pb_gbg else ""

            _pb_qi_html = (
                '<div><div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;letter-spacing:1px;">Best QI Season</div>'
                '<div style="color:#9B59B6;font-size:1rem;font-weight:700;">' + f"{_pb_qi:,}" + '</div></div>'
            ) if _pb_qi else ""

            # Update activity block with trend arrows
            _act_p = _consist_html  # consistency circle first (may be "")
            if _has_gbg_p and _p_gbg_s:
                _gbg_bdr = ('border-left:1px solid ' + _card_bdr_p + ';') if _consist_html else ''
                _act_p += (
                    '<div style="text-align:center;padding:0 12px;' + _gbg_bdr + '">'
                    '<div style="display:flex;align-items:center;justify-content:center;gap:4px;margin-bottom:2px;">'
                    + gbg_icon(16) +
                    '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.5px;">GBG</div>'
                    '</div>'
                    '<div style="color:' + _fc_p + ';font-weight:800;font-size:1.1rem;">' + f"{_p_fights:,}" + _trend_gbg + '</div>'
                    '<div style="color:#A8ABB8;font-size:0.65rem;">latest</div>'
                    '</div>'
                )
            if _has_qi_p and _p_qi_s:
                _act_p += (
                    '<div style="text-align:center;padding:0 12px;border-left:1px solid ' + _card_bdr_p + ';">'
                    '<div style="display:flex;align-items:center;justify-content:center;gap:4px;margin-bottom:2px;">'
                    + qi_icon(16) +
                    '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.5px;">QI</div>'
                    '</div>'
                    '<div style="color:' + _qc_p + ';font-weight:800;font-size:1.1rem;">' + f"{_p_qi_val:,}" + _trend_qi + '</div>'
                    '<div style="color:#A8ABB8;font-size:0.65rem;">latest</div>'
                    '</div>'
                )

            # ── Guild stats row ───────────────────────────────────────────
            _guild_stats_html = ""
            if not guild_stats_df.empty and "player_name" in guild_stats_df.columns:
                _gs_match = guild_stats_df[guild_stats_df["player_name"].str.strip() == profile["player_name"].strip()]
                if not _gs_match.empty:
                    _gs = _gs_match.iloc[0]

                    def _gsv(key):
                        raw = _gs.get(key, None)
                        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                            return None
                        if key == "critical_hit":
                            return f"{float(raw):.2f}%"
                        val = int(float(raw))
                        if key == "fp_production" and profile["player_name"].strip().lower() != "kuniggsbog":
                            val = val // 2
                        return f"{val:,}"

                    # Pre-load icons as img tags
                    _ic_atk_a = icon_html("Attack_Boost_for_Attacker.webp",  18)
                    _ic_def_a = icon_html("Defense_Boost_for_Attacker.webp", 18)
                    _ic_atk_d = icon_html("Attack_Boost_for_Defender.webp",  18)
                    _ic_def_d = icon_html("Defense_Boost_for_Defender.webp", 18)
                    _ic_goods = icon_html("Goods.webp", 18)

                    def _stat_item(ic, val, colour):
                        return (
                            f'<div style="display:flex;align-items:center;gap:5px;">'
                            f'{ic}'
                            f'<span style="color:{colour};font-weight:700;font-size:0.85rem;">{val}</span>'
                            f'</div>'
                        )

                    # Overlapping icon pair: atk icon + def icon side by side with slight overlap
                    def _icon_pair(atk_ic, def_ic):
                        return (
                            f'<span style="display:inline-flex;align-items:center;">'
                            f'<span style="display:inline-flex;">{atk_ic}</span>'
                            f'<span style="display:inline-flex;margin-left:-5px;">{def_ic}</span>'
                            f'</span>'
                        )

                    # One stats row: red side | [center icon] | blue side
                    # red_atk_key, red_def_key use attacker icons (red)
                    # blue_atk_key, blue_def_key use defender icons (blue)
                    def _gs_row(red_atk_key, red_def_key, blue_atk_key, blue_def_key, center_ic=""):
                        ra, rd = _gsv(red_atk_key),  _gsv(red_def_key)
                        ba, bd = _gsv(blue_atk_key), _gsv(blue_def_key)
                        if not any([ra, rd, ba, bd]):
                            return ""
                        _red_side = (
                            f'<div style="display:flex;align-items:center;gap:5px;">'
                            f'<span style="color:#E74C3C;font-weight:700;font-size:0.82rem;">{ra or "—"}</span>'
                            + _icon_pair(_ic_atk_a, _ic_def_a) +
                            f'<span style="color:#E74C3C;font-weight:700;font-size:0.82rem;">{rd or "—"}</span>'
                            f'</div>'
                        )
                        _center = (
                            f'<div style="flex:0 0 auto;padding:0 6px;opacity:0.7;">{center_ic}</div>'
                            if center_ic else
                            f'<div style="flex:0 0 28px;"></div>'
                        )
                        _blue_side = (
                            f'<div style="display:flex;align-items:center;gap:5px;">'
                            f'<span style="color:#4A90D9;font-weight:700;font-size:0.82rem;">{ba or "—"}</span>'
                            + _icon_pair(_ic_atk_d, _ic_def_d) +
                            f'<span style="color:#4A90D9;font-weight:700;font-size:0.82rem;">{bd or "—"}</span>'
                            f'</div>'
                        )
                        return (
                            f'<div style="display:flex;align-items:center;gap:8px;">'
                            + _red_side + _center + _blue_side +
                            f'</div>'
                        )

                    # Rows 1–3
                    _row_main = _gs_row("main_attack",                "main_defense",
                                        "defending_units_attack",      "defending_units_defense")
                    _row_gbg  = _gs_row("gbg_attack",                 "gbg_defense",
                                        "gbg_defending_units_attack",  "gbg_defending_units_defense",
                                        center_ic=icon_html("GBG_flag.png", 16))
                    _row_ge   = _gs_row("ge_attack",                  "ge_defense",
                                        "ge_defending_units_attack",   "ge_defending_units_defense",
                                        center_ic=icon_html("GE_flag.png", 16))

                    # Row 4 — Production
                    _prod_items = [
                        ("fp_production",         icon_html("forge_points.png", 18),  "#E8E8E8"),
                        ("units_production",       icon_html("units_icon.png", 18),    "#E8E8E8"),
                        ("goods_production",       _ic_goods,                          "#2ECC71"),
                        ("guild_goods_production", icon_html("guild_goods.png", 18),   "#4A90D9"),
                    ]
                    _prod_html = ""
                    for _pk, _pe, _pc in _prod_items:
                        v = _gsv(_pk)
                        if v:
                            _prod_html += _stat_item(_pe, v, _pc)

                    _crit_html = ""
                    _cv = _gsv("critical_hit")
                    if _cv:
                        _crit_html = _stat_item(icon_html("Crit_chance_icon.png", 18), _cv, "#FFD700")
                        _crit_pill_p = (
                            '<span style="background:#2A2000;color:#FFD700;border:1px solid #FFD70055;'
                            'padding:2px 9px;border-radius:20px;font-size:0.78rem;font-weight:700;'
                            'display:inline-flex;align-items:center;gap:5px;">'
                            + icon_html("Crit_chance_icon.png", 14)
                            + f'{float(str(_cv).rstrip("%")):.2f}%</span>'
                        )

                    _row4_html = ""
                    if _crit_html or _prod_html:
                        _row4_html = (
                            f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:14px;'
                            f'margin-top:10px;padding-top:10px;border-top:1px solid {_card_bdr_p}55;">'
                            + _crit_html + _prod_html +
                            f'</div>'
                        )

                    _rows_html = _row_main + _row_gbg + _row_ge

                    # ── Boost percentile badge ───────────────────────────
                    _all_atk_vals = pd.to_numeric(guild_stats_df["gbg_attack"], errors="coerce").dropna()
                    _p_atk_raw    = _gs.get("gbg_attack", None)
                    _p_atk_val    = float(_p_atk_raw) if _p_atk_raw is not None and pd.notna(_p_atk_raw) else None
                    if _p_atk_val is not None and len(_all_atk_vals) > 1:
                        _pct_rank  = int((_all_atk_vals < _p_atk_val).sum() / len(_all_atk_vals) * 100)
                        _top_pct   = 100 - _pct_rank
                        _pct_col   = "#2ECC71" if _top_pct <= 25 else "#F39C12" if _top_pct <= 60 else "#C8CBD8"
                        _boost_percentile_badge = (
                            f'<span style="background:{_pct_col}22;color:{_pct_col};'
                            f'border:1px solid {_pct_col}55;padding:2px 10px;border-radius:20px;'
                            f'font-size:0.75rem;font-weight:700;">⚔️ Top {_top_pct}% Attack</span>'
                        )

                    # ── Mil tab context strip (both unit types + efficiency) ──
                    _guild_avg_atk_val  = float(_all_atk_vals.mean()) if not _all_atk_vals.empty else 0
                    _all_def_atk_vals   = pd.to_numeric(guild_stats_df["gbg_defending_units_attack"], errors="coerce").dropna() if "gbg_defending_units_attack" in guild_stats_df.columns else pd.Series(dtype=float)
                    _all_def_def_vals   = pd.to_numeric(guild_stats_df["gbg_defending_units_defense"], errors="coerce").dropna() if "gbg_defending_units_defense" in guild_stats_df.columns else pd.Series(dtype=float)
                    _all_atk_def_vals   = pd.to_numeric(guild_stats_df["gbg_defense"], errors="coerce").dropna() if "gbg_defense" in guild_stats_df.columns else pd.Series(dtype=float)
                    _p_atk_def_raw   = _gs.get("gbg_defense", None)
                    _p_def_atk_raw   = _gs.get("gbg_defending_units_attack", None)
                    _p_def_def_raw   = _gs.get("gbg_defending_units_defense", None)
                    _p_atk_def_val   = float(_p_atk_def_raw) if _p_atk_def_raw is not None and pd.notna(_p_atk_def_raw) else None
                    _p_def_atk_val   = float(_p_def_atk_raw) if _p_def_atk_raw is not None and pd.notna(_p_def_atk_raw) else None
                    _p_def_def_val   = float(_p_def_def_raw) if _p_def_def_raw is not None and pd.notna(_p_def_def_raw) else None

                    def _ctx_stat(icon, val, colour, guild_vals=None):
                        _rank_html = ""
                        if guild_vals is not None and not guild_vals.empty and val is not None:
                            _r   = int((guild_vals > val).sum()) + 1
                            _n   = len(guild_vals)
                            _pct = int((_n - _r) / max(_n - 1, 1) * 100)
                            _rc  = "#2ECC71" if _r <= 3 else "#F39C12" if _r <= max(1, _n // 3) else "#C8CBD8"
                            _rank_html = (
                                f'<span style="color:{_rc};font-size:0.65rem;margin-left:3px;">'
                                f'#{_r}/{_n}'
                                f'</span>'
                                f'<span style="color:#A8ABB8;font-size:0.62rem;margin-left:2px;">'
                                f'Top {100 - _pct}%'
                                f'</span>'
                            )
                        _val_str = f'{int(val):,}%' if val is not None else '—'
                        return (
                            f'<div style="display:flex;align-items:center;gap:4px;">'
                            f'{icon}'
                            f'<span style="color:{colour};font-weight:700;font-size:0.88rem;">{_val_str}</span>'
                            + _rank_html +
                            f'</div>'
                        )

                    # Icons for context strip
                    _ic_atk_a = icon_html("GBG_Attack_Boost_for_Attacker.png",  16)
                    _ic_def_a = icon_html("GBG_Defense_Boost_for_Attacker.png", 16)
                    _ic_atk_d = icon_html("GBG_Attack_Boost_for_Defender.png",  16)
                    _ic_def_d = icon_html("GBG_Defense_Boost_for_Defender.png", 16)

                    # Boost balance ratio (A) + GBG attack rank (C)
                    _boost_ratio = round(_p_atk_val / _p_atk_def_val, 2) if _p_atk_val and _p_atk_def_val and _p_atk_def_val > 0 else None
                    _ratio_label = "offense-heavy" if _boost_ratio and _boost_ratio >= 1 else "defense-heavy"
                    _ratio_col   = "#E74C3C" if _boost_ratio and _boost_ratio >= 1 else "#4A90D9"
                    _atk_rank    = (int((_all_atk_vals > _p_atk_val).sum()) + 1) if _p_atk_val is not None and not _all_atk_vals.empty else None
                    _atk_rank_of = len(_all_atk_vals) if not _all_atk_vals.empty else None
                    _rank_col    = "#2ECC71" if _atk_rank and _atk_rank <= 3 else "#F39C12" if _atk_rank and _atk_rank <= max(1, _atk_rank_of // 3) else "#C8CBD8"

                    _ctx1 = _ctx_stat(_ic_atk_a, _p_atk_val,    "#E74C3C", _all_atk_vals)
                    _ctx2 = _ctx_stat(_ic_def_a, _p_atk_def_val, "#E74C3C", _all_atk_def_vals)
                    _ctx3 = _ctx_stat(_ic_atk_d, _p_def_atk_val, "#4A90D9", _all_def_atk_vals)
                    _ctx4 = _ctx_stat(_ic_def_d, _p_def_def_val, "#4A90D9", _all_def_def_vals)
                    _ctx5 = (
                        f'<div style="display:flex;align-items:center;gap:5px;">'
                        f'<span style="color:#E8E8E8;font-size:0.75rem;text-transform:uppercase;letter-spacing:0.4px;">Atk/Def ratio</span>'
                        f'<span style="color:{_ratio_col};font-weight:700;font-size:1rem;">{_boost_ratio:.2f}×</span>'
                        f'<span style="color:#E8E8E8;font-size:0.75rem;">({_ratio_label})</span>'
                        f'</div>'
                        if _boost_ratio else '<div></div>'
                    )
                    _ctx6 = (
                        f'<div style="display:flex;align-items:center;gap:5px;">'
                        f'<span style="color:#E8E8E8;font-size:0.75rem;text-transform:uppercase;letter-spacing:0.4px;">GBG Atk rank</span>'
                        f'<span style="color:{_rank_col};font-weight:700;font-size:1rem;">{_atk_rank}</span>'
                        f'<span style="color:#E8E8E8;font-size:0.75rem;">/ {_atk_rank_of}</span>'
                        f'</div>'
                        if _atk_rank else '<div></div>'
                    )
                    _mil_context = True  # flag

                    # Military Boosts tab content — flat 3-col grid so rows align across both sides
                    _ctx_border  = 'style="border-left:1px solid #3A3D4A;padding-left:8px;margin-left:4px;"'
                    _ctx_right   = 'style="border-left:1px solid #3A3D4A;padding-left:8px;"'
                    if _rows_html or _mil_context:
                        _mil_html = (
                            '<div style="padding:10px 0;">'
                            '<div style="display:grid;grid-template-columns:auto auto auto;gap:8px 0;align-items:center;">'
                            + _row_main + f'<div {_ctx_border}>' + _ctx1 + '</div>' + f'<div {_ctx_right}>' + _ctx2 + '</div>'
                            + _row_gbg  + f'<div {_ctx_border}>' + _ctx3 + '</div>' + f'<div {_ctx_right}>' + _ctx4 + '</div>'
                            + _row_ge   + f'<div {_ctx_border}>' + _ctx5 + '</div>' + f'<div {_ctx_right}>' + _ctx6 + '</div>'
                            + '</div>'
                            '</div>'
                        )

                    # Production tab content
                    if _prod_html:
                        _prod_tab_html = (
                            f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:20px;padding:10px 0;">'
                            + _prod_html +
                            f'</div>'
                        )

            _hero_html = (
                # URL-hash + :target tabs — hash lives in the URL, not the DOM,
                # so React re-renders can never reset it.
                '<style>'
                # Zero-size anchor targets sit at card top — browser scrolls there (already visible), so no jump
                'span._hct{position:fixed;top:0;left:0;width:0;height:0;overflow:hidden;pointer-events:none;}'
                # Content panels: p1 visible by default, p2/p3 hidden
                '.hc-p1{display:block}.hc-p2,.hc-p3{display:none}'
                ':has(#_hc2:target) .hc-p1{display:none}:has(#_hc2:target) .hc-p2{display:block}'
                ':has(#_hc3:target) .hc-p1{display:none}:has(#_hc3:target) .hc-p3{display:block}'
                # Tab link styles
                'a.htab{display:inline-block;padding:6px 16px;text-decoration:none;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid transparent;color:#A8ABB8;font-weight:400;}'
                'a.htab[href="#_hc1"]{border-bottom:2px solid #FFD700;color:#E8E8E8;font-weight:700;}'
                ':has(#_hc2:target) a.htab[href="#_hc1"]{border-bottom:2px solid transparent!important;color:#A8ABB8!important;font-weight:400!important;}'
                ':has(#_hc2:target) a.htab[href="#_hc2"]{border-bottom:2px solid #FFD700!important;color:#E8E8E8!important;font-weight:700!important;}'
                ':has(#_hc3:target) a.htab[href="#_hc1"]{border-bottom:2px solid transparent!important;color:#A8ABB8!important;font-weight:400!important;}'
                ':has(#_hc3:target) a.htab[href="#_hc3"]{border-bottom:2px solid #FFD700!important;color:#E8E8E8!important;font-weight:700!important;}'
                '</style>'

                '<div style="background:' + _card_bg_p + ';border:1px solid ' + _card_bdr_p + ';'
                'border-radius:14px;margin-bottom:16px;overflow:hidden;position:relative;'
                'box-shadow:0 2px 12px rgba(0,0,0,0.4);">'
                '<div style="position:relative;" class="strip-wrap">'
                '<div style="height:6px;background:' + _strip_p + ';width:100%;cursor:default;"></div>'
                '<div class="strip-tooltip">' + _strip_label + '</div>'
                '</div>'

                # Anchor targets — zero-size, fixed, invisible
                '<span id="_hc1" class="_hct"></span>'
                '<span id="_hc2" class="_hct"></span>'
                '<span id="_hc3" class="_hct"></span>'

                '<div style="padding:20px 24px;">'
                  # ── Header: avatar + name + key pills + activity ──
                  '<div style="display:flex;align-items:flex-start;gap:20px;">'
                    + avatar_html +
                    '<div style="flex:1;min-width:0;">'
                      '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:7px;">'
                        '<span style="color:' + _name_col_p + ';font-weight:900;font-size:1.5rem;line-height:1.2;">' + profile["player_name"] + '</span>'
                        + _ls_badge_p + _former_tag_p + _form_dots +
                      '</div>'
                      + (
                          '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:5px;margin-bottom:5px;">'
                          + _rank_badge_p + _pts_p + _era_pill_p +
                          '</div>'
                          if any([_rank_badge_p, _pts_p, _era_pill_p]) else ''
                      )
                      + (
                          '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:5px;margin-bottom:5px;">'
                          + _medals_p + _boost_percentile_badge +
                          '</div>'
                          if any([_medals_p, _boost_percentile_badge]) else ''
                      )
                      + (
                          '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:5px;margin-bottom:8px;">'
                          + _crit_pill_p + _achieve_badges +
                          '</div>'
                          if any([_crit_pill_p, _achieve_badges]) else ''
                      ) +
                    '</div>'
                    '<div style="display:flex;align-items:flex-start;border-left:1px solid ' + _card_bdr_p + ';margin-left:8px;">'
                      + _act_p +
                    '</div>'
                  '</div>'

                  # ── Tab bar ──
                  '<div style="margin-left:110px;border-bottom:1px solid ' + _card_bdr_p + ';margin-bottom:0;margin-top:14px;">'
                    '<div style="display:flex;gap:0;">'
                      '<a href="#_hc1" class="htab" style="padding-left:0;">Player Info</a>'
                      '<a href="#_hc2" class="htab">Battle Boosts</a>'
                      '<a href="#_hc3" class="htab">Production</a>'
                    '</div>'
                  '</div>'

                  # ── Tab content body row (110px spacer aligns content with name) ──
                  '<div style="display:flex;">'
                  '<div style="width:110px;flex-shrink:0;"></div>'
                  '<div style="flex:1;min-width:0;">'

                  # ── Tab 1 — Player Info ──
                  '<div class="hc-p1">'
                    '<div style="display:flex;gap:24px;margin-top:10px;padding-top:12px;border-top:1px solid ' + _card_bdr_p + ';flex-wrap:wrap;width:100%;justify-content:flex-start;align-items:flex-start;">'
                      + _pb_gbg_html + _pb_qi_html +
                      '<div><div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;letter-spacing:1px;">Guild Goods Daily</div>'
                      '<div style="color:#4A90D9;font-size:1rem;font-weight:700;">' + f"{gg:,}" + '</div></div>'
                      + _seasons_html +
                      '<div><div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;letter-spacing:1px;">Won Battles</div>'
                      '<div style="color:#2ECC71;font-size:1rem;font-weight:700;">' + f"{wb:,}" + '</div></div>'
                    '</div>'
                    + (
                        '<div style="margin-top:10px;padding-top:10px;border-top:1px solid ' + _card_bdr_p + '55;">'
                        '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">🐛 Snuggy Bug Badges</div>'
                        + "".join([
                            f'<span style="background:{b["bg"]};color:{b["col"]};border:1px solid {b["col"]}44;'
                            f'padding:2px 9px;border-radius:20px;font-size:0.72rem;font-weight:600;'
                            f'margin-right:5px;margin-bottom:4px;display:inline-block;">{b["icon"]} {b["name"]}</span>'
                            for b in _sb_badges_p
                        ]) +
                        '</div>'
                        if _sb_badges_p else ''
                    )
                    + _snap_p +
                  '</div>'

                  # ── Tab 2 — Battle Boosts ──
                  '<div class="hc-p2">'
                    '<div style="margin-top:10px;border-top:1px solid ' + _card_bdr_p + ';padding-top:12px;">'
                    + (
                        _mil_html
                        if _mil_html else
                        '<div style="color:#A8ABB8;font-size:0.85rem;padding:8px 0;">No battle boost data available for this player.</div>'
                    )
                    + _snap_p +
                    '</div>'
                  '</div>'

                  # ── Tab 3 — Production ──
                  '<div class="hc-p3">'
                    '<div style="margin-top:10px;border-top:1px solid ' + _card_bdr_p + ';padding-top:12px;">'
                    + (_prod_tab_html if _prod_tab_html else '<div style="color:#A8ABB8;font-size:0.85rem;padding:8px 0;">No production data available for this player.</div>')
                    + _snap_p +
                    '</div>'
                  '</div>'

                  '</div>'  # close flex:1 content col
                  '</div>'  # close body row

                '</div>'
                '</div>'
            )
            st.markdown(_hero_html, unsafe_allow_html=True)

            tab_gbg_p, tab_qi_p = st.tabs(["⚔ GBG History", "● QI History"])

            with tab_gbg_p:
                gbg_hist = profile["gbg_history"]
                gbg_chg  = profile["gbg_changes"]
                if gbg_hist.empty:
                    st.info("No GBG data for this player.")
                else:
                    if gbg_chg:
                        s_c = gbg_chg.get("season_current", "")
                        s_p = gbg_chg.get("season_previous", "")
                        st.markdown(f'<div class="section-title">📊 {s_c} vs {s_p}</div>', unsafe_allow_html=True)
                        ci1, ci2, ci3 = st.columns(3)
                        for ci, metric in zip([ci1, ci2, ci3], ["Fights", "Negotiations", "Total"]):
                            if metric in gbg_chg:
                                d    = gbg_chg[metric]
                                sign = "+" if d["delta"] >= 0 else ""
                                with ci:
                                    st.metric(label=metric, value=f"{d['current']:,}",
                                              delta=f"{sign}{d['delta']:,} ({sign}{d['pct']:.1f}%)")
                    st.markdown('<div class="section-title">📅 Season History</div>', unsafe_allow_html=True)
                    _gh = hide_pid(gbg_hist)
                    if "season" in _gh.columns and "Fights" in _gh.columns:
                        from modules.comparisons import sort_seasons as _ss_gh
                        _gh_order  = _ss_gh(_gh["season"].tolist(), descending=True)
                        _gh_sorted = _gh.set_index("season").reindex(_gh_order).reset_index()
                        _gh_sorted = _gh_sorted.dropna(subset=["Fights"]).reset_index(drop=True)
                        _max_fights = _gh_sorted["Fights"].max() if not _gh_sorted.empty else 1
                        for _, _row in _gh_sorted.iterrows():
                            _f  = int(_row.get("Fights", 0))
                            _n  = int(_row.get("Negotiations", 0))
                            _t  = int(_row.get("Total", 0))
                            _bp = int(_f / max(_max_fights, 1) * 100)
                            _bc = "#2ECC71" if _f >= 1000 else "#E74C3C"
                            _min_tag = "" if _f >= 1000 else '<span style="color:#E74C3C;font-size:0.7rem;margin-left:6px;">⚠️ below min</span>'
                            st.markdown(f"""
                            <div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;
                                        padding:10px 16px;margin-bottom:5px;">
                              <div style="display:flex;align-items:center;justify-content:space-between;">
                                <div style="color:#C8CBD8;font-weight:600;font-size:0.85rem;">{_row['season']}{_min_tag}</div>
                                <div style="display:flex;gap:20px;">
                                  <div style="text-align:right;">
                                    <div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">Fights</div>
                                    <div style="color:#FFD700;font-weight:700;">{_f:,}</div>
                                  </div>
                                  <div style="text-align:right;">
                                    <div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">Negs</div>
                                    <div style="color:#4A90D9;font-weight:700;">{_n:,}</div>
                                  </div>
                                  <div style="text-align:right;">
                                    <div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">Total</div>
                                    <div style="color:#2ECC71;font-weight:700;">{_t:,}</div>
                                  </div>
                                </div>
                              </div>
                              <div style="background:#0E1117;border-radius:4px;height:4px;margin-top:8px;">
                                <div style="background:{_bc};width:{_bp}%;height:4px;border-radius:4px;"></div>
                              </div>
                            </div>""", unsafe_allow_html=True)
                    st.plotly_chart(gbg_player_trend(gbg_hist, profile["player_name"]), width="stretch")

            with tab_qi_p:
                qi_hist = profile["qi_history"]
                qi_chg  = profile["qi_changes"]
                if qi_hist.empty:
                    st.info("No QI data for this player.")
                else:
                    if qi_chg:
                        s_c = qi_chg.get("season_current", "")
                        s_p = qi_chg.get("season_previous", "")
                        st.markdown(f'<div class="section-title">📊 {s_c} vs {s_p}</div>', unsafe_allow_html=True)
                        if "Progress" in qi_chg:
                            d    = qi_chg["Progress"]
                            sign = "+" if d["delta"] >= 0 else ""
                            st.metric(label="Progress", value=f"{d['current']:,}",
                                      delta=f"{sign}{d['delta']:,} ({sign}{d['pct']:.1f}%)")
                    st.markdown('<div class="section-title">📅 Season History</div>', unsafe_allow_html=True)
                    _qh = hide_pid(qi_hist)
                    if "season" in _qh.columns and "Progress" in _qh.columns:
                        from modules.comparisons import sort_seasons as _ss_qh
                        _qh_order  = _ss_qh(_qh["season"].tolist(), descending=True)
                        _qh_sorted = _qh.set_index("season").reindex(_qh_order).reset_index()
                        _qh_sorted = _qh_sorted.dropna(subset=["Progress"]).reset_index(drop=True)
                        _max_prog  = _qh_sorted["Progress"].max() if not _qh_sorted.empty else 1
                        for _, _row in _qh_sorted.iterrows():
                            _p  = int(_row.get("Progress", 0))
                            _bp = int(_p / max(_max_prog, 1) * 100)
                            _bc = "#9B59B6" if _p >= 3000 else "#E74C3C"
                            _min_tag = "" if _p >= 3000 else '<span style="color:#E74C3C;font-size:0.7rem;margin-left:6px;">⚠️ below min</span>'
                            st.markdown(f"""
                            <div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;
                                        padding:10px 16px;margin-bottom:5px;">
                              <div style="display:flex;align-items:center;justify-content:space-between;">
                                <div style="color:#C8CBD8;font-weight:600;font-size:0.85rem;">{_row['season']}{_min_tag}</div>
                                <div style="text-align:right;">
                                  <div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">Progress</div>
                                  <div style="color:#9B59B6;font-weight:700;">{_p:,}</div>
                                </div>
                              </div>
                              <div style="background:#0E1117;border-radius:4px;height:4px;margin-top:8px;">
                                <div style="background:{_bc};width:{_bp}%;height:4px;border-radius:4px;"></div>
                              </div>
                            </div>""", unsafe_allow_html=True)
                    st.plotly_chart(qi_player_trend(qi_hist, profile["player_name"]), width="stretch")

            st.markdown("---")
    _render_footer()


# ══════════════════════════════════════════════════════════════════════════
# PAGE: HEAD TO HEAD
# ══════════════════════════════════════════════════════════════════════════
elif page == "⚔️ Head to Head":
    log_event(st.session_state.get("current_user",""), "Head to Head", "visit")
    st.markdown("# ⚔️ Head to Head")
    st.markdown('<div style="color:#C8CBD8;font-size:0.88rem;margin-bottom:20px;">Compare any two players side by side across all seasons.</div>', unsafe_allow_html=True)

    _all_p_h2h = _load_all_players(gbg_df, qi_df, members_df)
    _h2h_names = sorted(
        _all_p_h2h["current"]["Player"].dropna().tolist()
    )

    if len(_h2h_names) < 2:
        st.info("Need at least 2 players in the system.")
    else:
        # ── Default selection: current user vs guild #1, else #1 vs #2 ──
        _cu_h2h = st.session_state.get("current_user")

        # Top player by points from members_df
        _top_by_points = []
        if not members_df.empty and "points" in members_df.columns and "Player" in members_df.columns:
            _mb_pts = members_df.dropna(subset=["Player"]).copy()
            _mb_pts["points"] = pd.to_numeric(_mb_pts["points"], errors="coerce").fillna(0)
            _top_by_points = _mb_pts.sort_values("points", ascending=False)["Player"].tolist()

        def _best_other(exclude):
            for _n in _top_by_points:
                if _n in _h2h_names and _n != exclude:
                    return _n
            return next((n for n in _h2h_names if n != exclude), _h2h_names[0])

        if "h2h_p1" not in st.session_state:
            if _cu_h2h and _cu_h2h in _h2h_names:
                st.session_state.h2h_p1 = _cu_h2h
            else:
                st.session_state.h2h_p1 = _h2h_names[0]

        if "h2h_p2" not in st.session_state:
            st.session_state.h2h_p2 = _best_other(st.session_state.h2h_p1)

        h2h_c1, h2h_c2 = st.columns(2)
        with h2h_c1:
            _p1_name = st.selectbox("Player 1", _h2h_names, key="h2h_p1")
        with h2h_c2:
            if st.session_state.h2h_p2 == st.session_state.h2h_p1:
                st.session_state.h2h_p2 = _best_other(st.session_state.h2h_p1)
            _p2_name = st.selectbox("Player 2", _h2h_names, key="h2h_p2")

        if _p1_name == _p2_name:
            st.warning("Select two different players.")
        else:
            _h2h_pair = " vs ".join(sorted([_p1_name, _p2_name]))
            log_event(st.session_state.get("current_user",""), "Head to Head", f"h2h:{_h2h_pair}")

            # Get PIDs
            _all_combined = pd.concat([_all_p_h2h["current"], _all_p_h2h["former"]], ignore_index=True)
            def _get_pid(name):
                r = _all_combined[_all_combined["Player"] == name]
                return str(r["Player_ID"].iloc[0]) if not r.empty else None

            _pid1 = _get_pid(_p1_name)
            _pid2 = _get_pid(_p2_name)

            # Member stats
            _m1 = get_latest_member_stats(members_df, _pid1) if _pid1 else {}
            _m2 = get_latest_member_stats(members_df, _pid2) if _pid2 else {}

            # GBG history
            _g1 = gbg_df[gbg_df["Player_ID"].astype(str)==_pid1] if _pid1 and not gbg_df.empty else pd.DataFrame()
            _g2 = gbg_df[gbg_df["Player_ID"].astype(str)==_pid2] if _pid2 and not gbg_df.empty else pd.DataFrame()
            _q1 = qi_df[qi_df["Player_ID"].astype(str)==_pid1] if _pid1 and not qi_df.empty else pd.DataFrame()
            _q2 = qi_df[qi_df["Player_ID"].astype(str)==_pid2] if _pid2 and not qi_df.empty else pd.DataFrame()

            def _h2h_stat(label, v1, v2, colour, fmt="{:,}"):
                _s1 = fmt.format(v1) if isinstance(v1, (int,float)) else str(v1)
                _s2 = fmt.format(v2) if isinstance(v2, (int,float)) else str(v2)
                _w1 = "font-weight:900;font-size:1.1rem;" if v1 > v2 else "opacity:0.7;"
                _w2 = "font-weight:900;font-size:1.1rem;" if v2 > v1 else "opacity:0.7;"
                return (
                    '<div style="display:grid;grid-template-columns:1fr auto 1fr;'
                    'align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid #1A1D27;">'
                    '<div style="text-align:right;color:' + colour + ';' + _w1 + '">' + _s1 + '</div>'
                    '<div style="text-align:center;color:#A8ABB8;font-size:0.7rem;text-transform:uppercase;white-space:nowrap;">' + label + '</div>'
                    '<div style="text-align:left;color:' + colour + ';' + _w2 + '">' + _s2 + '</div>'
                    '</div>'
                )

            # ── Header cards ──
            hh1, hh2 = st.columns(2)
            _era_colours_h = {"SAAB":"#E74C3C","SASH":"#9B59B6","CATH":"#3498DB","INDU":"#E67E22","PROG":"#2ECC71","CONT":"#F39C12","GILD":"#FFD700"}
            for _col, _name, _mem, _pid in [(hh1,_p1_name,_m1,_pid1),(hh2,_p2_name,_m2,_pid2)]:
                with _col:
                    _era = _mem.get("eraName","")
                    _ec  = _era_colours_h.get(_era[:4].upper(),"#4A90D9") if _era else "#4A90D9"
                    _av  = get_avatar_html(_name, size=56)
                    st.markdown(
                        '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:12px;padding:16px 20px;">'
                        '<div style="display:flex;align-items:center;gap:14px;">'
                        + _av +
                        '<div>'
                        '<div style="color:#F0F0F0;font-size:1.1rem;font-weight:800;">' + _name + '</div>'
                        + ('<div style="color:' + _ec + ';font-size:0.78rem;font-weight:700;margin-top:3px;">' + _era + '</div>' if _era else '') +
                        ('<div style="color:#FFD700;font-size:0.88rem;margin-top:2px;">' + f"{_mem.get('points',0):,}" + ' pts</div>' if _mem.get('points') else '') +
                        '</div></div></div>',
                        unsafe_allow_html=True,
                    )

            st.markdown("---")

            # ── Boost lookup helper (needed for both cards) ──
            _gs_h2h = guild_stats_df if guild_stats_df is not None and not guild_stats_df.empty else None
            def _gs_h2h_val(df, name, col):
                if df is None or col not in df.columns:
                    return None
                _name_lower = name.strip().lower()
                r = df[df["player_name"].str.strip().str.lower() == _name_lower]
                if r.empty:
                    return None
                v = r[col].iloc[0]
                try:
                    f = float(v)
                    if pd.isna(f):
                        return None
                    if col == "fp_production" and _name_lower != "kuniggsbog":
                        f = f / 2
                    return f
                except (TypeError, ValueError):
                    return None

            def _card_header(name1, name2):
                return (
                    '<div style="display:grid;grid-template-columns:1fr auto 1fr;gap:8px;'
                    'padding:0 0 8px;margin-bottom:4px;border-bottom:1px solid #2A2D3A;">'
                    '<div style="text-align:right;color:#E8E8E8;font-weight:700;font-size:0.85rem;">' + name1 + '</div>'
                    '<div style="color:#A8ABB8;font-size:0.7rem;align-self:center;">vs</div>'
                    '<div style="text-align:left;color:#E8E8E8;font-weight:700;font-size:0.85rem;">' + name2 + '</div>'
                    '</div>'
                )

            st.markdown('<div class="section-title">📊 Head to Head Stats</div>', unsafe_allow_html=True)
            _h2h_left_col, _h2h_right_col = st.columns(2)

            # ── LEFT: Military boosts ──────────────────────────────────────
            with _h2h_left_col:
                _mil_card = (
                    '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:12px;padding:16px 20px;">'
                    + _card_header(_p1_name, _p2_name)
                )
                _mil_boost_pairs = [
                    ("gbg_attack",                  "#E74C3C", "{:.0f}%"),
                    ("gbg_defense",                 "#E74C3C", "{:.0f}%"),
                    ("gbg_defending_units_attack",  "#4A90D9", "{:.0f}%"),
                    ("gbg_defending_units_defense", "#4A90D9", "{:.0f}%"),
                    ("critical_hit",                "#F39C12", "{:.2f}%"),
                ]
                _mil_icon_map = {
                    "gbg_attack":                  "GBG_Attack_Boost_for_Attacker.png",
                    "gbg_defense":                 "GBG_Defense_Boost_for_Attacker.png",
                    "gbg_defending_units_attack":  "GBG_Attack_Boost_for_Defender.png",
                    "gbg_defending_units_defense": "GBG_Defense_Boost_for_Defender.png",
                    "critical_hit":                "Crit_chance_icon.png",
                }
                _any_mil = False
                for _bc, _bclr, _bfmt in _mil_boost_pairs:
                    _bv1 = _gs_h2h_val(_gs_h2h, _p1_name, _bc)
                    _bv2 = _gs_h2h_val(_gs_h2h, _p2_name, _bc)
                    if _bv1 is None and _bv2 is None:
                        continue
                    _any_mil = True
                    _bv1f = _bv1 if _bv1 is not None else 0.0
                    _bv2f = _bv2 if _bv2 is not None else 0.0
                    _icon_b64 = _img_to_b64(ICON_DIR / _mil_icon_map[_bc])
                    _icon_tag = (f'<img src="data:image/png;base64,{_icon_b64}" '
                                 f'style="width:18px;height:18px;vertical-align:middle;margin:0 3px;">') if _icon_b64 else ""
                    _mil_card += _h2h_stat(_icon_tag, _bv1f, _bv2f, _bclr, _bfmt)

                # ── Daily production ──────────────────────────────────────
                _prod_pairs = [
                    (icon_html("forge_points.png", 14) + " Forge Points",  "fp_production",          "#2ECC71", "{:,.0f}"),
                    (icon_html("units_icon.png", 14)  + " Units",           "units_production",       "#E8E8E8", "{:,.0f}"),
                    (icon_html("Goods.webp", 14)       + " Goods",           "goods_production",        "#F39C12", "{:,.0f}"),
                    (icon_html("guild_goods.png", 14)  + " Guild Goods",    "guild_goods_production",  "#4A90D9", "{:,.0f}"),
                ]
                _prod_divider_added = False
                for _pl, _pc, _pclr, _pfmt in _prod_pairs:
                    _pv1 = _gs_h2h_val(_gs_h2h, _p1_name, _pc)
                    _pv2 = _gs_h2h_val(_gs_h2h, _p2_name, _pc)
                    if _pv1 is None and _pv2 is None:
                        continue
                    if not _prod_divider_added:
                        _mil_card += (
                            '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;'
                            'letter-spacing:0.5px;padding:10px 0 2px;">Daily Production</div>'
                        )
                        _prod_divider_added = True
                    _any_mil = True
                    _mil_card += _h2h_stat(_pl, _pv1 or 0.0, _pv2 or 0.0, _pclr, _pfmt)

                _mil_card += '</div>'
                if _any_mil:
                    st.markdown(_mil_card, unsafe_allow_html=True)
                elif _gs_h2h is None:
                    st.info("No boost data — upload guild_stats_final_named.csv.")
                else:
                    st.info("No boost data found for these players.")

            # ── RIGHT: General stats ───────────────────────────────────────
            with _h2h_right_col:
                _gen_card = (
                    '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:12px;padding:16px 20px;">'
                    + _card_header(_p1_name, _p2_name)
                )

                if _m1 or _m2:
                    _gen_card += _h2h_stat("Guild Rank",
                        _m2.get("rank",999) if _m1.get("rank",0)>_m2.get("rank",0) else _m1.get("rank",0),
                        _m1.get("rank",999) if _m1.get("rank",0)>_m2.get("rank",0) else _m2.get("rank",0),
                        "#C8CBD8", "#{:,}")
                    _gen_card += _h2h_stat("Points",      _m1.get("points",0),      _m2.get("points",0),      "#FFD700")
                    _gen_card += _h2h_stat("Won Battles", _m1.get("won_battles",0), _m2.get("won_battles",0), "#2ECC71")
                    _gen_card += _h2h_stat("Guild Goods", _m1.get("guildgoods",0),  _m2.get("guildgoods",0),  "#4A90D9")

                if not _g1.empty or not _g2.empty:
                    _tf1  = int(_g1["Fights"].sum()) if not _g1.empty else 0
                    _tf2  = int(_g2["Fights"].sum()) if not _g2.empty else 0
                    _pb1  = int(_g1["Fights"].max()) if not _g1.empty else 0
                    _pb2  = int(_g2["Fights"].max()) if not _g2.empty else 0
                    _avg1 = int(_g1["Fights"].mean()) if not _g1.empty else 0
                    _avg2 = int(_g2["Fights"].mean()) if not _g2.empty else 0
                    _s1c  = int(_g1["season"].nunique()) if not _g1.empty else 0
                    _s2c  = int(_g2["season"].nunique()) if not _g2.empty else 0
                    _gen_card += _h2h_stat("GBG Seasons",    _s1c,  _s2c,  "#4A90D9", "{:,}")
                    _gen_card += _h2h_stat("Lifetime Fights", _tf1, _tf2,  "#FFD700")
                    _gen_card += _h2h_stat("Best Season",     _pb1, _pb2,  "#F39C12")
                    _gen_card += _h2h_stat("Avg per Season",  _avg1,_avg2, "#E8E8E8")

                if not _q1.empty or not _q2.empty:
                    _tq1  = int(_q1["Progress"].sum()) if not _q1.empty else 0
                    _tq2  = int(_q2["Progress"].sum()) if not _q2.empty else 0
                    _qpb1 = int(_q1["Progress"].max()) if not _q1.empty else 0
                    _qpb2 = int(_q2["Progress"].max()) if not _q2.empty else 0
                    _gen_card += _h2h_stat("QI Seasons",
                        int(_q1["season"].nunique()) if not _q1.empty else 0,
                        int(_q2["season"].nunique()) if not _q2.empty else 0,
                        "#9B59B6", "{:,}")
                    _gen_card += _h2h_stat("Lifetime Progress", _tq1,  _tq2,  "#9B59B6")
                    _gen_card += _h2h_stat("Best QI Season",    _qpb1, _qpb2, "#E67E22")

                _gen_card += '</div>'
                st.markdown(_gen_card, unsafe_allow_html=True)

            # ── Battle stats radar / bar chart ──
            if _gs_h2h is not None:
                _radar_cols = [
                    ("gbg_attack",                 "GBG_Attack_Boost_for_Attacker.png",  "png"),
                    ("gbg_defense",                "GBG_Defense_Boost_for_Attacker.png", "png"),
                    ("gbg_defending_units_attack", "GBG_Attack_Boost_for_Defender.png",  "png"),
                    ("gbg_defending_units_defense","GBG_Defense_Boost_for_Defender.png", "png"),
                    ("critical_hit",               "Crit_chance_icon.png",               "png"),
                ]
                _rc_available = [(col, fname, ext) for col, fname, ext in _radar_cols
                                 if col in _gs_h2h.columns]
                if _rc_available:
                    _rv1 = [_gs_h2h_val(_gs_h2h, _p1_name, col) or 0 for col, _, __ in _rc_available]
                    _rv2 = [_gs_h2h_val(_gs_h2h, _p2_name, col) or 0 for col, _, __ in _rc_available]
                    if any(_rv1) or any(_rv2):
                        st.markdown("---")
                        st.markdown('<div class="section-title">⚔️ Battle Boosts Comparison</div>', unsafe_allow_html=True)
                        import plotly.graph_objects as _go_boost
                        _fig_boost = _go_boost.Figure()
                        _x_pos = list(range(len(_rc_available)))
                        _bar_w = 0.35
                        _fig_boost.add_trace(_go_boost.Bar(
                            name=_p1_name,
                            x=[x - _bar_w/2 for x in _x_pos],
                            y=_rv1,
                            width=_bar_w,
                            marker_color="#FFD700",
                            text=[f"{v:.0f}%" for v in _rv1],
                            textposition="outside",
                        ))
                        _fig_boost.add_trace(_go_boost.Bar(
                            name=_p2_name,
                            x=[x + _bar_w/2 for x in _x_pos],
                            y=_rv2,
                            width=_bar_w,
                            marker_color="#9B59B6",
                            text=[f"{v:.0f}%" for v in _rv2],
                            textposition="outside",
                        ))
                        # Build icon images for x-axis
                        _boost_images = []
                        for _bi, (_, _bfname, _bext) in enumerate(_rc_available):
                            _b64 = _img_to_b64(ICON_DIR / _bfname)
                            if _b64:
                                _boost_images.append(dict(
                                    source=f"data:image/{_bext};base64,{_b64}",
                                    xref="x", yref="paper",
                                    x=_bi, y=-0.06,
                                    sizex=0.55, sizey=0.14,
                                    xanchor="center", yanchor="top",
                                    layer="above",
                                ))
                        _fig_boost.update_layout(
                            paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
                            font=dict(color="#E8E8E8", family="Inter, sans-serif"),
                            margin=dict(l=20, r=20, t=30, b=70),
                            height=360,
                            barmode="overlay",
                            xaxis=dict(
                                tickmode="array",
                                tickvals=_x_pos,
                                ticktext=[""] * len(_rc_available),
                                gridcolor="#1A1D27",
                            ),
                            yaxis=dict(gridcolor="#1A1D27", ticksuffix="%"),
                            legend=dict(bgcolor="#1A1D27", bordercolor="#2A2D3A"),
                            images=_boost_images,
                        )
                        st.plotly_chart(_fig_boost, width="stretch")

            # ── Shared seasons chart ──
            if not _g1.empty and not _g2.empty:
                st.markdown("---")
                st.markdown('<div class="section-title">📈 GBG Fights — Season by Season</div>', unsafe_allow_html=True)
                from modules.comparisons import sort_seasons as _ss_h2h
                import plotly.graph_objects as _go_h2h
                _shared = sorted(set(_g1["season"].tolist()) | set(_g2["season"].tolist()),
                                  key=lambda s: _ss_h2h([s] if s else [""])[0] if s else s)
                _shared = _ss_h2h(_shared)
                _f1v = [int(_g1[_g1["season"]==s]["Fights"].sum()) if s in _g1["season"].values else 0 for s in _shared]
                _f2v = [int(_g2[_g2["season"]==s]["Fights"].sum()) if s in _g2["season"].values else 0 for s in _shared]
                _fig_h2h = _go_h2h.Figure()
                _fig_h2h.add_trace(_go_h2h.Scatter(x=_shared, y=_f1v, name=_p1_name,
                    line=dict(color="#FFD700",width=3), marker=dict(size=8)))
                _fig_h2h.add_trace(_go_h2h.Scatter(x=_shared, y=_f2v, name=_p2_name,
                    line=dict(color="#9B59B6",width=3), marker=dict(size=8)))
                _fig_h2h.update_layout(
                    paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
                    font=dict(color="#E8E8E8", family="Inter, sans-serif"),
                    margin=dict(l=20,r=20,t=30,b=60),
                    height=320,
                    xaxis=dict(gridcolor="#1A1D27", tickangle=-30),
                    yaxis=dict(gridcolor="#1A1D27"),
                    legend=dict(bgcolor="#1A1D27", bordercolor="#2A2D3A"),
                )
                st.plotly_chart(_fig_h2h, width="stretch")

    _render_footer()


# ══════════════════════════════════════════════════════════════════════════
# PAGE: DATA IMPORT  (password-protected)
# ══════════════════════════════════════════════════════════════════════════
elif page == "🐛 Snuggy Bug":

    # ── Session state ────────────────────────────────────────────────────
    if "sb_history"       not in st.session_state: st.session_state.sb_history       = []
    if "sb_points"        not in st.session_state: st.session_state.sb_points        = 0
    if "sb_questions"     not in st.session_state: st.session_state.sb_questions     = 0
    if "sb_session_count" not in st.session_state: st.session_state.sb_session_count = 0
    if "sb_players_asked" not in st.session_state: st.session_state.sb_players_asked = set()
    if "sb_daily_done"    not in st.session_state: st.session_state.sb_daily_done    = False
    if "sb_context"         not in st.session_state: st.session_state.sb_context         = None
    if "sb_context_version" not in st.session_state: st.session_state.sb_context_version = None

    _cu = st.session_state.get("current_user")

    # ── Build context once per session (rebuild if version changed) ──────
    if st.session_state.sb_context is None or st.session_state.sb_context_version != CONTEXT_VERSION:
        with st.spinner("Snuggy Bug is loading guild data..."):
            st.session_state.sb_context = build_guild_context(
                gbg_df, qi_df, members_df,
                guild_stats_df=guild_stats_df,
                activity_df=load_log(30),
                current_user=_cu,
            )
            st.session_state.sb_context_version = CONTEXT_VERSION

    # ── Page header ──────────────────────────────────────────────────────
    st.markdown(
        '<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">'
        '<svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">'
        '<ellipse cx="16" cy="19" rx="9" ry="10" fill="#2ECC71"/>'
        '<ellipse cx="16" cy="15" rx="6.5" ry="6" fill="#27AE60"/>'
        '<circle cx="13" cy="13" r="2.2" fill="white"/><circle cx="19" cy="13" r="2.2" fill="white"/>'
        '<circle cx="13.5" cy="13" r="1.1" fill="#0E1117"/><circle cx="19.5" cy="13" r="1.1" fill="#0E1117"/>'
        '<line x1="7" y1="11" x2="2" y2="7" stroke="#2ECC71" stroke-width="1.5" stroke-linecap="round"/>'
        '<line x1="7" y1="14" x2="1" y2="14" stroke="#2ECC71" stroke-width="1.5" stroke-linecap="round"/>'
        '<line x1="25" y1="11" x2="30" y2="7" stroke="#2ECC71" stroke-width="1.5" stroke-linecap="round"/>'
        '<line x1="25" y1="14" x2="31" y2="14" stroke="#2ECC71" stroke-width="1.5" stroke-linecap="round"/>'
        '<line x1="11" y1="27" x2="8" y2="31" stroke="#2ECC71" stroke-width="1.5" stroke-linecap="round"/>'
        '<line x1="16" y1="29" x2="16" y2="32" stroke="#2ECC71" stroke-width="1.5" stroke-linecap="round"/>'
        '<line x1="21" y1="27" x2="24" y2="31" stroke="#2ECC71" stroke-width="1.5" stroke-linecap="round"/>'
        '<ellipse cx="16" cy="9" rx="3.5" ry="3" fill="#FFD700"/>'
        '<line x1="13.5" y1="6.5" x2="11" y2="3" stroke="#FFD700" stroke-width="1.2" stroke-linecap="round"/>'
        '<line x1="18.5" y1="6.5" x2="21" y2="3" stroke="#FFD700" stroke-width="1.2" stroke-linecap="round"/>'
        '</svg>'
        '<div>'
        '<div style="font-size:1.3rem;font-weight:900;color:#F0F0F0;">Ask Snuggy Bug</div>'
        '<div style="color:#A8ABB8;font-size:0.78rem;">Your guild data assistant · earn points for every question</div>'
        '</div>'
        + (f'<div style="margin-left:auto;background:#1A2A1A;border:1px solid #2ECC71;border-radius:8px;padding:6px 14px;font-size:0.8rem;color:#2ECC71;font-weight:700;">'
           f'👤 {_cu} · {st.session_state.sb_points} pts</div>' if _cu else '') +
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown("---")

    _sb_tab1, _sb_tab2, _sb_tab3 = st.tabs(["💬 Chat", "🏆 Leaderboard", "🎖️ My Stats"])

    # ════════════════════════════════════════════════════════════════════
    # TAB 1 — CHAT
    # ════════════════════════════════════════════════════════════════════
    with _sb_tab1:

        # ── Proactive briefing ───────────────────────────────────────────
        if not st.session_state.sb_history:
            _briefing = build_proactive_briefing(gbg_df, qi_df, members_df, _cu)
            if _briefing:
                st.markdown('<div style="color:#C8CBD8;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Guild briefing</div>', unsafe_allow_html=True)
                _bc = st.columns(min(len(_briefing), 3))
                for _bi, _card in enumerate(_briefing[:3]):
                    with _bc[_bi]:
                        st.markdown(
                            '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-left:3px solid ' + _card["colour"] + ';'
                            'border-radius:10px;padding:12px 14px;margin-bottom:12px;">'
                            '<div style="font-size:0.7rem;font-weight:700;color:' + _card["colour"] + ';margin-bottom:4px;">'
                            + _card["icon"] + ' ' + _card["title"] + '</div>'
                            '<div style="font-size:0.78rem;color:#C8C8C8;line-height:1.5;">' + _card["body"] + '</div>'
                            '</div>',
                            unsafe_allow_html=True
                        )

        # ── Chat history ─────────────────────────────────────────────────
        for _msg in st.session_state.sb_history:
            if _msg["role"] == "user":
                with st.chat_message("user"):
                    st.markdown(_msg["content"])
            else:
                with st.chat_message("assistant", avatar="🐛"):
                    st.markdown(_msg["content"])
                    if _msg.get("points"):
                        st.markdown(
                            f'<span style="background:#1A2A1A;border:1px solid #2ECC71;border-radius:10px;'
                            f'padding:2px 8px;font-size:0.72rem;color:#2ECC71;font-weight:700;">'
                            f'+{_msg["points"]} pts earned</span>',
                            unsafe_allow_html=True
                        )

        # ── Suggestion chips (only on first visit) ───────────────────────
        if not st.session_state.sb_history:
            _suggestions = [
                "Who are the top 5 fighters this season?",
                "Which players are below minimum?",
                "Who has the longest streak?",
                "How has our guild total changed over time?",
            ]
            if _cu:
                _suggestions.insert(0, f"How am I performing compared to my average?")

            _sug_cols = st.columns(len(_suggestions[:4]))
            for _si, _sug in enumerate(_suggestions[:4]):
                with _sug_cols[_si]:
                    if st.button(_sug, key=f"sug_{_si}", use_container_width=True):
                        st.session_state._pending_question = _sug
                        st.rerun()

        # ── Handle pending question from suggestion chips ─────────────────
        if hasattr(st.session_state, "_pending_question"):
            _q = st.session_state._pending_question
            del st.session_state._pending_question
            st.session_state._process_question = _q

        # ── Chat input ────────────────────────────────────────────────────
        if _user_input := st.chat_input("Ask Snuggy Bug anything about your guild..."):
            st.session_state._process_question = _user_input

        # ── Process question ──────────────────────────────────────────────
        if hasattr(st.session_state, "_process_question"):
            _q = st.session_state._process_question
            del st.session_state._process_question

            # Display user message
            with st.chat_message("user"):
                st.markdown(_q)
            st.session_state.sb_history.append({"role": "user", "content": _q})

            # Calculate points
            _pts_earned = POINTS_RULES["question"]
            if not st.session_state.sb_daily_done:
                _pts_earned += POINTS_RULES["daily_first"]
                st.session_state.sb_daily_done = True
            if st.session_state.sb_questions == 0:
                _pts_earned += POINTS_RULES["first_ever"]

            # Check if asking about a specific player
            _all_players = list(gbg_df["Player"].unique()) if not gbg_df.empty else []
            for _pn in _all_players:
                if _pn.lower() in _q.lower() and _pn != _cu:
                    st.session_state.sb_players_asked.add(_pn)
                    _pts_earned += POINTS_RULES["about_player"]
                    break

            st.session_state.sb_session_count += 1
            if st.session_state.sb_session_count == 5:
                _pts_earned += POINTS_RULES["session_5"]

            # Get answer
            with st.chat_message("assistant", avatar="🐛"):
                import random as _random
                _thinking_msgs = [
                    "Snuggy Bug is conbobulating the data...",
                    "Snuggy Bug is skedaddling through the records...",
                    "Snuggy Bug is cogitating furiously...",
                    "Snuggy Bug is rummaging through the guild archives...",
                    "Snuggy Bug is discombobulating the statistics...",
                    "Snuggy Bug is wrangling the numbers...",
                    "Snuggy Bug is scuttling through seasons past...",
                    "Snuggy Bug is pondering the guild mysteries...",
                    "Snuggy Bug is crunching, munching, and data-lunching...",
                    "Snuggy Bug is spelunking through the data caves...",
                ]
                with st.spinner(_random.choice(_thinking_msgs)):
                    _answer = ask_snuggy_bug(
                        _q,
                        st.session_state.sb_context,
                        st.session_state.sb_history[:-1],
                        _cu,
                    )
                st.markdown(_answer)
                st.markdown(
                    f'<span style="background:#1A2A1A;border:1px solid #2ECC71;border-radius:10px;'
                    f'padding:2px 8px;font-size:0.72rem;color:#2ECC71;font-weight:700;">'
                    f'+{_pts_earned} pts earned</span>',
                    unsafe_allow_html=True
                )

            st.session_state.sb_history.append({
                "role": "assistant",
                "content": _answer,
                "points": _pts_earned,
            })
            st.session_state.sb_questions  += 1
            st.session_state.sb_points     += _pts_earned

            # Persist any newly earned badges
            if _cu:
                try:
                    _all_badges = get_earned_badges(
                        st.session_state.sb_questions,
                        len(st.session_state.sb_players_asked),
                        1,
                        st.session_state.sb_session_count,
                    )
                    save_badges(_cu, _all_badges)
                except Exception:
                    pass

            # Log to activity
            try:
                log_event(_cu or "", "Snuggy Bug", f"question:{_q[:60]}")
            except Exception:
                pass

            st.rerun()

    # ════════════════════════════════════════════════════════════════════
    # TAB 2 — LEADERBOARD
    # ════════════════════════════════════════════════════════════════════
    with _sb_tab2:
        st.markdown('<div style="color:#C8CBD8;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;">Snuggy Bug points leaderboard</div>', unsafe_allow_html=True)

        # Load from activity log
        try:
            _act_df = load_log(days=365)
            if not _act_df.empty:
                _sb_log = _act_df[_act_df["page"] == "Snuggy Bug"].copy()
                if not _sb_log.empty:
                    _lb_counts = _sb_log.groupby("player").size().reset_index(name="questions")
                    _lb_counts["points"] = _lb_counts["questions"] * POINTS_RULES["question"]
                    _lb_counts = _lb_counts.sort_values("points", ascending=False).reset_index(drop=True)

                    _lbc1, _lbc2, _lbc3 = st.columns(3)
                    _lbc1.metric("Active users", len(_lb_counts))
                    _lbc2.metric("Questions asked", int(_lb_counts["questions"].sum()))
                    _lbc3.metric("Total pts awarded", f"{int(_lb_counts['points'].sum()):,}")

                    st.markdown("---")
                    _medal_map = {0:"🥇", 1:"🥈", 2:"🥉"}
                    _max_pts = int(_lb_counts["points"].iloc[0]) if not _lb_counts.empty else 1
                    for _li, (_, _lr) in enumerate(_lb_counts.iterrows()):
                        _medal = _medal_map.get(_li, f"#{_li+1}")
                        _lpts  = int(_lr["points"])
                        _lq    = int(_lr["questions"])
                        _lname = str(_lr["player"])
                        _earned_badges = get_earned_badges(_lq, 0, 0, 0)
                        _border = "border:1px solid #FFD700;" if _li == 0 else "border:1px solid #2A2D3A;"
                        _badges_html = "".join([
                            f'<span style="background:{b["bg"]};color:{b["col"]};padding:2px 7px;border-radius:20px;font-size:11px;font-weight:600;margin-right:4px;">{b["icon"]} {b["name"]}</span>'
                            for b in _earned_badges
                        ])
                        _bar_pct = int(_lpts / max(_max_pts, 1) * 100)
                        st.markdown(
                            '<div style="background:#1A1D27;' + _border + 'border-radius:10px;padding:12px 16px;margin-bottom:6px;">'
                            '<div style="display:flex;align-items:center;gap:12px;">'
                            '<div style="font-size:1.1rem;width:28px;text-align:center;">' + str(_medal) + '</div>'
                            '<div style="flex:1;font-size:0.92rem;font-weight:700;">' + _lname + '</div>'
                            '<div style="color:#FFD700;font-weight:900;font-size:1rem;">' + f"{_lpts:,}" + ' pts</div>'
                            '<div style="color:#A8ABB8;font-size:0.78rem;margin-left:8px;">' + str(_lq) + ' Q</div>'
                            '</div>'
                            + (f'<div style="margin-top:6px;">{_badges_html}</div>' if _badges_html else '') +
                            '<div style="margin-top:7px;background:#0E1117;border-radius:4px;height:4px;">'
                            '<div style="background:#FFD700;width:' + str(_bar_pct) + '%;height:4px;border-radius:4px;"></div>'
                            '</div></div>',
                            unsafe_allow_html=True
                        )
                else:
                    st.info("No Snuggy Bug activity yet — be the first to ask a question!")
            else:
                st.info("No activity data yet.")
        except Exception as _e:
            st.info("Leaderboard will appear once players start asking questions.")

    # ════════════════════════════════════════════════════════════════════
    # TAB 3 — MY STATS
    # ════════════════════════════════════════════════════════════════════
    with _sb_tab3:
        _sq = st.session_state.sb_questions
        _sp = st.session_state.sb_points
        _spl = len(st.session_state.sb_players_asked)

        st.markdown('<div style="color:#C8CBD8;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;">Your Snuggy Bug stats this session</div>', unsafe_allow_html=True)

        _sc1, _sc2, _sc3, _sc4 = st.columns(4)
        _sc1.metric("Points", f"{_sp:,}")
        _sc2.metric("Questions", _sq)
        _sc3.metric("Players asked about", _spl)
        _sc4.metric("Session streak", st.session_state.sb_session_count)

        # Earned badges
        _my_badges = get_earned_badges(_sq, _spl, 1, st.session_state.sb_session_count)
        if _my_badges:
            st.markdown("---")
            st.markdown('<div style="color:#C8CBD8;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Badges earned this session</div>', unsafe_allow_html=True)
            _bh = "".join([
                f'<span style="background:{b["bg"]};color:{b["col"]};padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600;margin-right:6px;margin-bottom:6px;display:inline-block;">{b["icon"]} {b["name"]}</span>'
                for b in _my_badges
            ])
            st.markdown(_bh, unsafe_allow_html=True)

        # Next badge
        _next = get_next_badge(_sq, _spl, 1)
        if _next:
            st.markdown("---")
            st.markdown('<div style="color:#C8CBD8;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Next badge</div>', unsafe_allow_html=True)
            _prog_pct = int(_next["progress"] / max(_next["target"], 1) * 100)
            st.markdown(
                '<div style="background:#12151E;border:1px solid #2A2D3A;border-radius:10px;padding:14px 16px;">'
                '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">'
                '<span style="background:' + _next["bg"] + ';color:' + _next["col"] + ';padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;">' + _next["icon"] + ' ' + _next["name"] + '</span>'
                '<div style="flex:1;background:#0E1117;border-radius:3px;height:6px;">'
                '<div style="background:' + _next["col"] + ';width:' + str(_prog_pct) + '%;height:6px;border-radius:3px;"></div>'
                '</div>'
                '<div style="color:#C8CBD8;font-size:0.72rem;min-width:80px;text-align:right;">' + _next["label"] + '</div>'
                '</div>'
                '<div style="color:#A8ABB8;font-size:0.72rem;">' + _next["desc"] + '</div>'
                '</div>',
                unsafe_allow_html=True
            )

        # All badges reference
        st.markdown("---")
        st.markdown('<div style="color:#C8CBD8;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">All badges</div>', unsafe_allow_html=True)
        for _b in BADGES:
            _earned = _b in _my_badges
            _opacity = "1" if _earned else "0.35"
            st.markdown(
                '<div style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid #1A1D27;opacity:' + _opacity + ';">'
                '<span style="background:' + _b["bg"] + ';color:' + _b["col"] + ';padding:2px 9px;border-radius:20px;font-size:11px;font-weight:600;">' + _b["icon"] + ' ' + _b["name"] + '</span>'
                '<div style="color:#C8CBD8;font-size:0.78rem;">' + _b["desc"] + '</div>'
                + ('<div style="margin-left:auto;color:#2ECC71;font-size:0.72rem;font-weight:700;">✓ earned</div>' if _earned else '') +
                '</div>',
                unsafe_allow_html=True
            )

    _render_footer()

elif page == "🏅 Competitions":
    from modules.competitions import COMP_DIR
    st.markdown("# 🏅 Competitions")
    st.markdown('<div style="color:#A8ABB8;font-size:0.85rem;margin-bottom:20px;">Active and past guild competitions</div>', unsafe_allow_html=True)

    # ── Load competitions ─────────────────────────────────────────────────
    _all_comps = list_competitions()
    _active    = [c for c in _all_comps if c.get("active", True)]
    _inactive  = [c for c in _all_comps if not c.get("active", True)]

    # ── Competition selector ──────────────────────────────────────────────
    if "comp_selected" not in st.session_state:
        st.session_state.comp_selected = _active[0]["_id"] if _active else None

    if _all_comps:
        _comp_names = {c["_id"]: c.get("name", c["_id"]) for c in _all_comps}
        _sel_cols   = st.columns([3, 1])
        with _sel_cols[0]:
            _sel_id = st.selectbox(
                "Select competition",
                options=list(_comp_names.keys()),
                format_func=lambda x: _comp_names[x],
                key="comp_selector",
                label_visibility="collapsed"
            )
            st.session_state.comp_selected = _sel_id

    # ── Password gate for officer actions ─────────────────────────────────
    if "comp_auth" not in st.session_state:
        st.session_state.comp_auth = False

    with st.sidebar:
        if not st.session_state.comp_auth:
            _cp = st.text_input("Officer password", type="password", key="comp_pw")
            if _cp and _cp == st.secrets.get("IMPORT_PASSWORD", "guild2024"):
                st.session_state.comp_auth = True
                st.rerun()

    # ── New competition form (officer only) ───────────────────────────────
    with st.expander("➕ Create New Competition", expanded=not _all_comps):
        if st.session_state.comp_auth:
            nc1, nc2 = st.columns(2)
            with nc1:
                _nc_name  = st.text_input("Competition name", placeholder="e.g. Blackcong GBG March 2026", key="nc_name")
                _nc_org   = st.text_input("Organiser", placeholder="e.g. Blackcong", key="nc_org")
                _nc_snaps = st.number_input("Expected total snapshots", min_value=2, max_value=20, value=8, key="nc_snaps")
            with nc2:
                st.markdown('<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:6px;">Win rewards — tier 1 (e.g. 5000+ fights)</div>', unsafe_allow_html=True)
                _nc_w1_min  = st.number_input("Win tier 1 min fights", value=5000, key="nc_w1_min")
                _nc_w1_base = st.number_input("Win tier 1 base FP", value=10000, key="nc_w1_base")
                _nc_w1_p100 = st.number_input("Win tier 1 FP per 100 extra", value=1000, key="nc_w1_p100")
                _nc_w1_max  = st.number_input("Win tier 1 max FP", value=50000, key="nc_w1_max")
                st.markdown('<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:6px;">Win rewards — tier 2 (e.g. 3000+ fights)</div>', unsafe_allow_html=True)
                _nc_w2_min  = st.number_input("Win tier 2 min fights", value=3000, key="nc_w2_min")
                _nc_w2_base = st.number_input("Win tier 2 base FP", value=5000, key="nc_w2_base")
                st.markdown('<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:6px;">Lose rewards</div>', unsafe_allow_html=True)
                _nc_l1_base = st.number_input("Lose tier 1 (5k+) base FP", value=5000, key="nc_l1_base")
                _nc_l1_p100 = st.number_input("Lose tier 1 FP per 100 extra", value=1000, key="nc_l1_p100")
                _nc_l1_max  = st.number_input("Lose tier 1 max FP", value=30000, key="nc_l1_max")
                _nc_l2_base = st.number_input("Lose tier 2 (3k+) base FP", value=3000, key="nc_l2_base")

            if st.button("✅ Create Competition", key="nc_create") and _nc_name:
                import re as _re_comp
                _nc_id  = _re_comp.sub(r"[^a-z0-9_]", "_", _nc_name.lower())[:40]
                _nc_cfg = {
                    "name":             _nc_name,
                    "organiser":        _nc_org,
                    "active":           True,
                    "total_snapshots":  int(_nc_snaps),
                    "win": {
                        "tiers": [
                            {"min_fights": int(_nc_w1_min), "base_fp": int(_nc_w1_base), "per_100": int(_nc_w1_p100), "max_fp": int(_nc_w1_max)},
                            {"min_fights": int(_nc_w2_min), "base_fp": int(_nc_w2_base), "per_100": 0, "max_fp": int(_nc_w2_base)},
                        ]
                    },
                    "lose": {
                        "tiers": [
                            {"min_fights": int(_nc_w1_min), "base_fp": int(_nc_l1_base), "per_100": int(_nc_l1_p100), "max_fp": int(_nc_l1_max)},
                            {"min_fights": int(_nc_w2_min), "base_fp": int(_nc_l2_base), "per_100": 0, "max_fp": int(_nc_l2_base)},
                        ]
                    }
                }
                ok, msg = save_competition(_nc_id, _nc_cfg)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        else:
            st.info("🔒 Enter officer password in the sidebar to create competitions.")

    # ── Active competition view ───────────────────────────────────────────
    _cid = st.session_state.get("comp_selected")
    if not _cid:
        st.info("No competitions yet. Create one above.")
    else:
        _cfg = get_competition(_cid)
        if not _cfg:
            st.error("Competition not found.")
        else:
            # Header
            _snaps = list_snapshots(_cid)
            _snap_count = len(_snaps)
            _last_snap_time = ""
            if _snaps:
                import os as _os_c
                _snap_path = COMP_DIR / _cid / _snaps[-1]
                if _snap_path.exists():
                    _mtime = _snap_path.stat().st_mtime
                    import datetime as _dt_c
                    _last_snap_time = _dt_c.datetime.fromtimestamp(_mtime).strftime("%-d %b %Y %H:%M")

            _hc1, _hc2 = st.columns([3, 1])
            with _hc1:
                st.markdown(
                    '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:12px;padding:14px 18px;margin-bottom:12px;">'
                    '<div style="color:#FFD700;font-size:1.1rem;font-weight:900;margin-bottom:4px;">' + _cfg.get("name", _cid) + '</div>'
                    '<div style="color:#C8CBD8;font-size:0.78rem;">Organised by ' + _cfg.get("organiser", "—") +
                    ' &nbsp;·&nbsp; Snapshot ' + str(_snap_count) + ' of ' + str(_cfg.get("total_snapshots", "?")) +
                    (' &nbsp;·&nbsp; Last updated: ' + _last_snap_time if _last_snap_time else '') +
                    '</div></div>',
                    unsafe_allow_html=True
                )
            with _hc2:
                _status = "Active" if _cfg.get("active", True) else "Ended"
                _scol   = "#2ECC71" if _status == "Active" else "#E74C3C"
                _sbg    = "#1A3A1A" if _status == "Active" else "#2A1A1A"
                st.markdown(
                    f'<div style="background:{_sbg};border:1px solid #2A2D3A;border-radius:12px;'
                    f'padding:14px 18px;text-align:center;margin-bottom:12px;">'
                    f'<div style="color:{_scol};font-weight:700;font-size:0.9rem;">{_status}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

            # Import snapshot (officer only)
            if st.session_state.comp_auth:
                with st.expander("📥 Import New Snapshot"):
                    _snap_file = st.file_uploader("Upload GBG CSV snapshot", type=["csv"], key=f"snap_upload_{_cid}")
                    if _snap_file:
                        import io as _io_c
                        _raw_s = _snap_file.read().decode("utf-8-sig")
                        _sep_s = ";" if _raw_s.count(";") > _raw_s.count(",") else ","
                        _df_snap = pd.read_csv(_io_c.StringIO(_raw_s), sep=_sep_s)
                        st.dataframe(_df_snap[["Player_ID","Player","Fights"]].head(8) if "Fights" in _df_snap.columns else _df_snap.head(8),
                                     hide_index=True, width="stretch")
                        if st.button("✅ Save Snapshot", key=f"snap_confirm_{_cid}"):
                            _ok_s, _msg_s = save_snapshot(_cid, _df_snap)
                            st.success(_msg_s) if _ok_s else st.error(_msg_s)
                            if _ok_s:
                                st.rerun()

            # Rules panel
            with st.expander("📋 Competition Rules", expanded=True):
                _rc1, _rc2 = st.columns(2)
                with _rc1:
                    st.markdown('<div style="background:#1A3A1A;color:#2ECC71;padding:4px 10px;border-radius:6px;font-size:0.78rem;font-weight:700;display:inline-block;margin-bottom:8px;">🏆 If we WIN</div>', unsafe_allow_html=True)
                    for _t in _cfg.get("win", {}).get("tiers", []):
                        _desc = f"{_t['min_fights']:,}+ fights: {_t['base_fp']:,} FP"
                        if _t.get("per_100", 0) > 0:
                            _desc += f" + {_t['per_100']:,} FP per 100 extra (max {_t['max_fp']:,})"
                        st.markdown(f'<div style="color:#C8C8C8;font-size:0.78rem;padding:3px 0;border-bottom:1px solid #1A2A1A;">{_desc}</div>', unsafe_allow_html=True)
                with _rc2:
                    st.markdown('<div style="background:#2A1A1A;color:#E74C3C;padding:4px 10px;border-radius:6px;font-size:0.78rem;font-weight:700;display:inline-block;margin-bottom:8px;">💀 If we LOSE</div>', unsafe_allow_html=True)
                    for _t in _cfg.get("lose", {}).get("tiers", []):
                        _desc = f"{_t['min_fights']:,}+ fights: {_t['base_fp']:,} FP"
                        if _t.get("per_100", 0) > 0:
                            _desc += f" + {_t['per_100']:,} FP per 100 extra (max {_t['max_fp']:,})"
                        st.markdown(f'<div style="color:#C8C8C8;font-size:0.78rem;padding:3px 0;border-bottom:1px solid #2A1A1A;">{_desc}</div>', unsafe_allow_html=True)

            if not _snaps:
                st.info("No snapshots yet. Import the first snapshot above.")
            else:
                _df_latest = load_latest_snapshot(_cid)
                if "Fights" not in _df_latest.columns and "fights" in _df_latest.columns:
                    _df_latest = _df_latest.rename(columns={"fights": "Fights"})
                if "Player" not in _df_latest.columns and "player" in _df_latest.columns:
                    _df_latest = _df_latest.rename(columns={"player": "Player"})
                _df_latest = _df_latest.sort_values("Fights", ascending=False).reset_index(drop=True)
                _max_fights = int(_df_latest["Fights"].max()) if not _df_latest.empty else 1
                _df_momentum = get_momentum(_cid)
                _df_fp       = get_fp_projections(_cid, _cfg)
                _df_forecast = get_forecast(_cid, _cfg)

                # Tabs
                _ct1, _ct2, _ct3, _ct4 = st.tabs(["🏆 Leaderboard", "⚡ Momentum", "💰 FP Projections", "🔮 Forecast"])

                # ── Tab 1: Leaderboard ────────────────────────────────────
                with _ct1:
                    st.markdown(f'<div style="color:#A8ABB8;font-size:0.72rem;margin-bottom:10px;">Snapshot {_snap_count} · delta vs previous snapshot</div>', unsafe_allow_html=True)
                    _medal_map = {0:"🥇", 1:"🥈", 2:"🥉"}
                    _tier_5k = sorted([t["min_fights"] for t in _cfg.get("win",{}).get("tiers",[])], reverse=True)[0] if _cfg.get("win",{}).get("tiers") else 5000
                    _tier_3k = sorted([t["min_fights"] for t in _cfg.get("win",{}).get("tiers",[])], reverse=True)[-1] if _cfg.get("win",{}).get("tiers") else 3000

                    _lb_rows = list(_df_latest.itertuples(index=True))
                    def _lb_card(rank_idx, row):
                        fights   = int(getattr(row, "Fights", 0))
                        player   = str(getattr(row, "Player", "?"))
                        medal    = _medal_map.get(rank_idx, f"#{rank_idx+1}")
                        bar_pct  = int(fights / max(_max_fights, 1) * 100)
                        m3_pct   = int(_tier_3k / max(_max_fights, 1) * 100)
                        m5_pct   = int(_tier_5k / max(_max_fights, 1) * 100)
                        bar_col  = "#FFD700" if fights >= _tier_5k else "#F39C12" if fights >= _tier_3k else "#E74C3C"

                        # Delta
                        _delta_html = ""
                        if not _df_momentum.empty and "Player" in _df_momentum.columns:
                            _dm = _df_momentum[_df_momentum["Player"] == player]
                            if not _dm.empty:
                                _d = int(_dm["Delta"].iloc[0])
                                _dc = "#2ECC71" if _d >= 0 else "#E74C3C"
                                _delta_html = f'<span style="color:{_dc};font-size:0.78rem;min-width:60px;text-align:right;">{_d:+,}</span>'

                        return (
                            '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;padding:12px 16px;margin-bottom:6px;">'
                            '<div style="display:flex;align-items:center;gap:12px;">'
                            '<div style="font-size:1.1rem;width:28px;text-align:center;">' + str(medal) + '</div>'
                            '<div style="flex:1;font-size:0.92rem;font-weight:700;color:#E8E8E8;">' + player + '</div>'
                            '<div style="color:#FFD700;font-weight:900;font-size:1rem;min-width:60px;text-align:right;">' + f"{fights:,}" + '</div>'
                            + _delta_html +
                            '</div>'
                            '<div style="margin-top:7px;background:#0E1117;border-radius:4px;height:6px;position:relative;">'
                            '<div style="background:' + bar_col + ';width:' + str(bar_pct) + '%;height:6px;border-radius:4px;"></div>'
                            '<div style="position:absolute;top:-3px;left:' + str(m3_pct) + '%;width:2px;height:12px;background:#C8CBD8;border-radius:1px;"></div>'
                            '<div style="position:absolute;top:-3px;left:' + str(m5_pct) + '%;width:2px;height:12px;background:#C8CBD8;border-radius:1px;"></div>'
                            '</div>'
                            '</div>'
                        )

                    for i, row in enumerate(_lb_rows[:3]):
                        st.markdown(_lb_card(i, row), unsafe_allow_html=True)
                    if len(_lb_rows) > 3:
                        with st.expander(f"Show {len(_lb_rows)-3} more players"):
                            for i, row in enumerate(_lb_rows[3:], 3):
                                st.markdown(_lb_card(i, row), unsafe_allow_html=True)

                # ── Tab 2: Momentum ───────────────────────────────────────
                with _ct2:
                    if _df_momentum.empty or _snap_count < 2:
                        st.info("Need at least 2 snapshots to show momentum.")
                    else:
                        _mc1, _mc2 = st.columns(2)
                        with _mc1:
                            st.markdown('<div style="color:#C8CBD8;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Top 10 — Biggest Increase</div>', unsafe_allow_html=True)
                            _top_abs = _df_momentum.sort_values("Delta", ascending=False).head(10)
                            for i, (_, row) in enumerate(_top_abs.iterrows()):
                                _medal = _medal_map.get(i, f"#{i+1}")
                                _dc = "#2ECC71" if row["Delta"] >= 0 else "#E74C3C"
                                st.markdown(
                                    '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;padding:10px 14px;margin-bottom:5px;display:flex;align-items:center;gap:10px;">'
                                    '<div style="font-size:1rem;width:24px;">' + str(_medal) + '</div>'
                                    '<div style="flex:1;font-size:0.88rem;font-weight:700;">' + str(row["Player"]) + '</div>'
                                    '<div style="color:' + _dc + ';font-size:0.88rem;font-weight:700;">' + f"{int(row['Delta']):+,}" + ' fights</div>'
                                    '</div>', unsafe_allow_html=True)
                        with _mc2:
                            st.markdown('<div style="color:#C8CBD8;font-size:0.68rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Top 10 — Biggest % Increase</div>', unsafe_allow_html=True)
                            _top_pct = _df_momentum.sort_values("Pct", ascending=False).head(10)
                            for i, (_, row) in enumerate(_top_pct.iterrows()):
                                _medal = _medal_map.get(i, f"#{i+1}")
                                _dc = "#2ECC71" if row["Pct"] >= 0 else "#E74C3C"
                                st.markdown(
                                    '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;padding:10px 14px;margin-bottom:5px;display:flex;align-items:center;gap:10px;">'
                                    '<div style="font-size:1rem;width:24px;">' + str(_medal) + '</div>'
                                    '<div style="flex:1;font-size:0.88rem;font-weight:700;">' + str(row["Player"]) + '</div>'
                                    '<div style="color:' + _dc + ';font-size:0.88rem;font-weight:700;">' + f"{float(row['Pct']):+.1f}%" + '</div>'
                                    '</div>', unsafe_allow_html=True)

                # ── Tab 3: FP Projections ─────────────────────────────────
                with _ct3:
                    if _df_fp.empty:
                        st.info("No snapshot data yet.")
                    else:
                        _total_win  = int(_df_fp["Win FP"].sum())
                        _total_lose = int(_df_fp["Lose FP"].sum())
                        st.markdown(
                            '<div style="background:#1A2A1A;border:1px solid #2A3A2A;border-radius:8px;padding:10px 14px;margin-bottom:12px;font-size:0.82rem;">'
                            '<span style="color:#C8CBD8;">💰 Total guild FP payout &nbsp;·&nbsp; </span>'
                            '<span style="color:#2ECC71;font-weight:700;">Win: ' + f"{_total_win:,}" + ' FP</span>'
                            '&nbsp;&nbsp;·&nbsp;&nbsp;'
                            '<span style="color:#E74C3C;font-weight:700;">Lose: ' + f"{_total_lose:,}" + ' FP</span>'
                            '</div>',
                            unsafe_allow_html=True
                        )
                        # Header
                        st.markdown(
                            '<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr;gap:8px;padding:6px 16px;'
                            'border-bottom:1px solid #2A2D3A;margin-bottom:4px;">'
                            '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;">Player</div>'
                            '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;">Fights</div>'
                            '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;">Win FP</div>'
                            '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;">Lose FP</div>'
                            '<div style="color:#C8CBD8;font-size:0.65rem;text-transform:uppercase;">To next tier</div>'
                            '</div>',
                            unsafe_allow_html=True
                        )
                        _fp_rows = list(_df_fp.itertuples(index=False))
                        def _fp_card(row):
                            _need = f"+{int(row._4):,} fights" if pd.notna(row._4) and row._4 else "—"
                            _win_col  = "#2ECC71" if row._2 > 0 else "#A8ABB8"
                            _lose_col = "#E74C3C" if row._3 > 0 else "#A8ABB8"
                            return (
                                '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;padding:10px 16px;'
                                'margin-bottom:5px;display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr;gap:8px;align-items:center;">'
                                '<div style="font-size:0.88rem;font-weight:700;color:#E8E8E8;">' + str(row._0) + '</div>'
                                '<div style="color:#FFD700;font-size:0.88rem;font-weight:700;">' + f"{int(row._1):,}" + '</div>'
                                '<div style="color:' + _win_col + ';font-size:0.88rem;font-weight:700;">' + f"{int(row._2):,}" + '</div>'
                                '<div style="color:' + _lose_col + ';font-size:0.88rem;font-weight:700;">' + f"{int(row._3):,}" + '</div>'
                                '<div style="color:#C8CBD8;font-size:0.78rem;">' + _need + '</div>'
                                '</div>'
                            )
                        for row in _fp_rows[:3]:
                            st.markdown(_fp_card(row), unsafe_allow_html=True)
                        if len(_fp_rows) > 3:
                            with st.expander(f"Show {len(_fp_rows)-3} more"):
                                for row in _fp_rows[3:]:
                                    st.markdown(_fp_card(row), unsafe_allow_html=True)

                # ── Tab 4: Forecast ───────────────────────────────────────
                with _ct4:
                    if _df_forecast.empty:
                        st.info("Need at least 1 snapshot to forecast.")
                    else:
                        _at_risk = _df_forecast[_df_forecast["Tier"] == "Below 3k"]
                        if not _at_risk.empty:
                            st.markdown(
                                '<div style="background:#2A1A1A;border:1px solid #3A2A2A;border-radius:8px;padding:10px 14px;margin-bottom:12px;color:#E74C3C;font-size:0.82rem;">'
                                '⚠️ ' + str(len(_at_risk)) + ' player' + ('s' if len(_at_risk) > 1 else '') +
                                ' currently projected to miss the ' + f"{_tier_3k:,}" + ' fight minimum'
                                '</div>',
                                unsafe_allow_html=True
                            )
                        st.markdown(f'<div style="color:#A8ABB8;font-size:0.72rem;margin-bottom:10px;">Based on avg fights per snapshot · {_snap_count} snapshots imported · {_cfg.get("total_snapshots",8) - _snap_count} remaining</div>', unsafe_allow_html=True)

                        _fc_rows = list(_df_forecast.itertuples(index=False))
                        def _fc_card(i, row):
                            _tier_col = "#FFD700" if "5,000" in row.Tier else "#2ECC71" if "3,000" in row.Tier else "#E74C3C"
                            _tier_bg  = "#2A2A1A" if "5,000" in row.Tier else "#1A2A1A" if "3,000" in row.Tier else "#2A1A1A"
                            return (
                                '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;padding:12px 16px;'
                                'margin-bottom:6px;display:flex;align-items:center;gap:12px;">'
                                '<div style="color:#C8CBD8;font-size:0.85rem;width:28px;text-align:center;">#' + str(i+1) + '</div>'
                                '<div style="flex:1;font-size:0.9rem;font-weight:700;">' + str(row.Player) + '</div>'
                                '<div style="color:#C8CBD8;font-size:0.82rem;margin-right:8px;">~' + f"{int(row.Projected):,}" + ' projected</div>'
                                '<div style="background:' + _tier_bg + ';color:' + _tier_col + ';padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;">' + row.Tier + '</div>'
                                '</div>'
                            )
                        for i, row in enumerate(_fc_rows[:3]):
                            st.markdown(_fc_card(i, row), unsafe_allow_html=True)
                        if len(_fc_rows) > 3:
                            with st.expander(f"Show {len(_fc_rows)-3} more"):
                                for i, row in enumerate(_fc_rows[3:], 3):
                                    st.markdown(_fc_card(i, row), unsafe_allow_html=True)

            # Mark as ended / delete (officer only)
            if st.session_state.comp_auth:
                st.markdown("---")
                _oc1, _oc2 = st.columns(2)
                with _oc1:
                    if _cfg.get("active", True):
                        if st.button("🏁 Mark as Ended", key=f"end_{_cid}"):
                            _cfg["active"] = False
                            save_competition(_cid, _cfg)
                            st.rerun()
                with _oc2:
                    if st.button("🗑️ Delete Competition", key=f"del_comp_{_cid}"):
                        delete_competition(_cid)
                        st.session_state.comp_selected = None
                        st.rerun()

    _render_footer()

elif page == "📥 Data Import":
    st.title("📥 Data Import")

    # ── Password gate ─────────────────────────────────────────────────────
    if not st.session_state.import_authenticated:
        st.markdown("### 🔒 Import area is password protected")
        pwd_input = st.text_input("Enter import password", type="password", key="import_pwd")
        if st.button("Unlock"):
            if pwd_input == IMPORT_PASS:
                st.session_state.import_authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.info("Contact your guild administrator for the import password.")
        st.stop()

    # Authenticated ────────────────────────────────────────────────────────
    st.success("🔓 Import unlocked")
    if st.button("🔒 Lock import"):
        st.session_state.import_authenticated = False
        st.rerun()

    tab_gbg_imp, tab_qi_imp, tab_mem_imp, tab_manage, tab_sample = st.tabs(
        ["⚔️ Import GBG", "🌀 Import QI", "👥 Import Members", "🗂️ Manage Seasons", "📄 Sample CSVs"]
    )

    with tab_gbg_imp:
        st.subheader("Import GBG Season")
        st.markdown(
            "Upload the CSV exported from **FoE Helper**. "
            "The export date is read from the filename — adjust the season date range below if needed."
        )
        gbg_file = st.file_uploader("Upload GBG CSV", type=["csv"], key="gbg_upload")
        if gbg_file:
            try:
                import io as _io_g, re as _re_g, datetime as _dt_g
                _raw_g = gbg_file.read().decode("utf-8-sig")
                _sep_g = ";" if _raw_g.count(";") > _raw_g.count(",") else ","
                df_gbg_raw = pd.read_csv(_io_g.StringIO(_raw_g), sep=_sep_g)

                # Auto-detect date from filename
                _dm_g = _re_g.search(r"(\d{4})-(\d{2})-(\d{2})", gbg_file.name)
                if _dm_g:
                    _end_g   = _dt_g.date(int(_dm_g.group(1)), int(_dm_g.group(2)), int(_dm_g.group(3)))
                    _start_g = _end_g - _dt_g.timedelta(days=11)
                else:
                    _end_g   = _dt_g.date.today()
                    _start_g = _end_g - _dt_g.timedelta(days=11)

                # Info strip
                cg1, cg2, cg3 = st.columns(3)
                cg1.metric("Players detected", len(df_gbg_raw))
                cg2.metric("Separator", "Semicolon" if _sep_g == ";" else "Comma")
                cg3.metric("Extra columns", ", ".join(c for c in df_gbg_raw.columns
                           if c not in ["Player_ID","Player","Negotiations","Fights","Total"]) or "None")

                # Date range editor
                st.markdown('<div class="section-title">Season date range</div>', unsafe_allow_html=True)
                dc1, dc2 = st.columns(2)
                with dc1:
                    _s_start = st.date_input("Season start", value=_start_g, key="gbg_start")
                with dc2:
                    _s_end   = st.date_input("Season end",   value=_end_g,   key="gbg_end")

                _season_name_g = _s_start.strftime("%-d %b %Y") + " - " + _s_end.strftime("%-d %b %Y")
                st.markdown(f'Season name: **`{_season_name_g}`**')

                # Preview
                _prev_cols_g = [c for c in ["Player_ID","Player","Negotiations","Fights","Total"]
                                if c in df_gbg_raw.columns]
                st.dataframe(df_gbg_raw[_prev_cols_g].head(8), width="stretch", hide_index=True)

                if st.button("✅ Confirm Import", key="gbg_confirm"):
                    ok, msg = import_gbg(df_gbg_raw, _season_name_g)
                    st.success(msg) if ok else st.error(msg)
                    if ok:
                        log_event(st.session_state.get("current_user",""), "Data Import", f"imported:GBG:{_season_name_g}")
                        st.cache_data.clear()
                        st.rerun()
            except Exception as e:
                st.error(f"Error reading file: {e}")

    with tab_qi_imp:
        st.subheader("Import QI Season")
        st.markdown(
            "Upload the CSV exported from **FoE Helper**. "
            "The export date is read from the filename — adjust the season date range below if needed."
        )
        qi_file = st.file_uploader("Upload QI CSV", type=["csv"], key="qi_upload")
        if qi_file:
            try:
                import io as _io_q, re as _re_q, datetime as _dt_q
                _raw_q = qi_file.read().decode("utf-8-sig")
                _sep_q = ";" if _raw_q.count(";") > _raw_q.count(",") else ","
                df_qi_raw = pd.read_csv(_io_q.StringIO(_raw_q), sep=_sep_q)

                # Auto-detect date from filename
                _dm_q = _re_q.search(r"(\d{4})-(\d{2})-(\d{2})", qi_file.name)
                if _dm_q:
                    _end_q   = _dt_q.date(int(_dm_q.group(1)), int(_dm_q.group(2)), int(_dm_q.group(3)))
                    _start_q = _end_q - _dt_q.timedelta(days=11)
                else:
                    _end_q   = _dt_q.date.today()
                    _start_q = _end_q - _dt_q.timedelta(days=11)

                # Info strip
                cq1, cq2, cq3 = st.columns(3)
                cq1.metric("Players detected", len(df_qi_raw))
                cq2.metric("Separator", "Semicolon" if _sep_q == ";" else "Comma")
                cq3.metric("Columns", ", ".join(df_qi_raw.columns[:4].tolist()))

                # Date range editor
                st.markdown('<div class="section-title">Season date range</div>', unsafe_allow_html=True)
                qc1, qc2 = st.columns(2)
                with qc1:
                    _q_start = st.date_input("Season start", value=_start_q, key="qi_start")
                with qc2:
                    _q_end   = st.date_input("Season end",   value=_end_q,   key="qi_end")

                _season_name_q = _q_start.strftime("%-d %b %Y") + " - " + _q_end.strftime("%-d %b %Y")
                st.markdown(f'Season name: **`{_season_name_q}`**')

                # Preview
                _prev_cols_q = [c for c in ["Player_ID","Player","Actions","Progress"]
                                if c in df_qi_raw.columns]
                st.dataframe(df_qi_raw[_prev_cols_q].head(8), width="stretch", hide_index=True)

                if st.button("✅ Confirm Import", key="qi_confirm"):
                    ok, msg = import_qi(df_qi_raw, _season_name_q)
                    st.success(msg) if ok else st.error(msg)
                    if ok:
                        log_event(st.session_state.get("current_user",""), "Data Import", f"imported:QI:{_season_name_q}")
                        st.cache_data.clear()
                        st.rerun()
            except Exception as e:
                st.error(f"Error reading file: {e}")

    with tab_mem_imp:
        st.subheader("Import Guild Member Snapshot")
        st.markdown(
            "Upload the CSV exported directly from **FoE Helper**. "
            "The snapshot date is extracted automatically from the filename (e.g. `Member-2026-03-14.csv`)."
        )

        mem_file = st.file_uploader("Upload Members CSV", type=["csv"], key="mem_upload")

        if mem_file:
            try:
                # ── Auto-detect separator (FoE Helper uses semicolons) ──
                raw = mem_file.read().decode("utf-8-sig")
                mem_file.seek(0)
                sep = ";" if raw.count(";") > raw.count(",") else ","
                import io as _io
                df_raw = pd.read_csv(_io.StringIO(raw), sep=sep)

                # ── Extract snapshot date from filename ──────────────────
                import re as _re
                _fname = mem_file.name  # e.g. Member-2026-03-14.csv
                _date_match = _re.search(r"(\d{4})-(\d{2})-(\d{2})", _fname)
                if _date_match:
                    import datetime as _dt
                    _y, _m, _d = int(_date_match.group(1)), int(_date_match.group(2)), int(_date_match.group(3))
                    _snap = _dt.date(_y, _m, _d).strftime("%-d %b %Y")
                else:
                    _snap = None

                # ── Column normalisation ─────────────────────────────────
                _col_map = {}
                if "member_id" in df_raw.columns: _col_map["member_id"] = "member_id"
                if "member"    in df_raw.columns: _col_map["member"]    = "member"
                # Keep extra FoE Helper columns if present
                _extra_cols = ["activity_warnings", "gex_participation", "gbg_participation", "messages"]

                # Show detected info
                c_info1, c_info2, c_info3 = st.columns(3)
                c_info1.metric("Rows detected", len(df_raw))
                c_info2.metric("Separator", "Semicolon" if sep == ";" else "Comma")
                c_info3.metric("Snapshot date", _snap if _snap else "Not found in filename")

                if not _snap:
                    _snap = st.text_input("Snapshot name not found in filename — enter manually",
                                          placeholder="e.g. 14 Mar 2026", key="mem_snap_manual")

                # Preview
                _preview_cols = ["rank","member_id","member","points","eraName","guildgoods","won_battles"]
                _preview_cols = [c for c in _preview_cols if c in df_raw.columns]
                st.markdown('<div class="section-title">Preview</div>', unsafe_allow_html=True)
                st.dataframe(df_raw[_preview_cols].head(8), width="stretch", hide_index=True)

                # Extra columns notice
                _found_extras = [c for c in _extra_cols if c in df_raw.columns]
                if _found_extras:
                    st.info(f"Extra columns detected and will be saved: {', '.join('`' + c + '`' for c in _found_extras)}")

                if _snap and st.button("✅ Confirm Import", key="mem_confirm"):
                    ok, msg = import_members(df_raw, _snap.strip())
                    st.success(msg) if ok else st.error(msg)
                    if ok:
                        log_event(st.session_state.get("current_user",""), "Data Import", "imported:Members")
                        st.cache_data.clear()
                        st.rerun()

            except Exception as e:
                st.error(f"Error reading file: {e}")

    with tab_manage:
        st.subheader("Manage Imported Seasons")
        all_seas = get_all_seasons()
        col_g, col_q, col_m = st.columns(3)
        with col_g:
            st.markdown("**GBG Seasons**")
            for s in all_seas.get("gbg", []):
                c1, c2 = st.columns([3, 1])
                c1.write(s)
                if c2.button("🗑️", key=f"del_gbg_{s}"):
                    st.success(delete_season("gbg", s))
                    st.rerun()
            if not all_seas.get("gbg"):
                st.info("None imported.")
        with col_q:
            st.markdown("**QI Seasons**")
            for s in all_seas.get("qi", []):
                c1, c2 = st.columns([3, 1])
                c1.write(s)
                if c2.button("🗑️", key=f"del_qi_{s}"):
                    st.success(delete_season("qi", s))
                    st.rerun()
            if not all_seas.get("qi"):
                st.info("None imported.")
        with col_m:
            st.markdown("**Member Snapshots**")
            for s in all_seas.get("members", []):
                c1, c2 = st.columns([3, 1])
                c1.write(s)
                if c2.button("🗑️", key=f"del_mem_{s}"):
                    st.success(delete_season("members", s))
                    st.rerun()
            if not all_seas.get("members"):
                st.info("None imported.")

    with tab_sample:
        st.subheader("Download Sample CSV Templates")
        gbg_sample = "Player_ID,Player,Negotiations,Fights,Total\n854681998,Zodman,0,7097,7097\n1234051,Devils Deciple.,0,5744,5744\n7954450,Bloody Pastor,116,5451,5683\n"
        qi_sample  = "Player_ID,Player,Actions,Progress\n705849,lasherbob,4262800,12150\n853267111,Kuniggsbog,3855900,11000\n854719004,soldier00,3843900,10950\n"
        mem_sample = "rank,member_id,member,points,eraID,eraName,guildgoods,won_battles\n1,705849,lasherbob,9073312254,23,SASH,40000,1001205\n2,2277993,Crusaderx,8203612815,23,SASH,27040,1377990\n3,10593569,Badvok the Bold,7465202419,23,SASH,31400,914082\n"
        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button("⬇️ GBG Template", gbg_sample, "gbg_template.csv", "text/csv")
            st.code(gbg_sample)
        with c2:
            st.download_button("⬇️ QI Template", qi_sample, "qi_template.csv", "text/csv")
            st.code(qi_sample)
        with c3:
            st.download_button("⬇️ Members Template", mem_sample, "members_template.csv", "text/csv")
            st.code(mem_sample)
    _render_footer()


# ══════════════════════════════════════════════════════════════════════════
# PAGE: METRICS
# ══════════════════════════════════════════════════════════════════════════
elif page == "📊 Metrics":
    log_event(st.session_state.get("current_user",""), "Metrics", "visit")
    st.markdown("# 📊 Metrics")

    if gbg_df.empty and qi_df.empty:
        st.info("No data yet. Import a season in **📥 Data Import**.")
    else:
        # ── Guild Contribution Distribution ───────────────────────────────
        st.markdown('<div class="section-title">🥧 Guild Contribution Distribution</div>', unsafe_allow_html=True)

        _metric_tabs = st.tabs(["⚔️ GBG Fights", "🌀 QI Progress"])

        def _contribution_chart(df, value_col, season_label, colour_main, colour_rest):
            """Pie + breakdown cards for contribution share."""
            if df.empty:
                st.info("No data available.")
                return

            from modules.comparisons import sort_seasons as _ss
            _seasons = _ss(df["season"].unique().tolist())
            _latest  = df[df["season"] == _seasons[-1]].copy()

            # Current players only
            _curr_pids = set(df[df["season"] == _seasons[-1]]["Player_ID"].astype(str))
            _latest = _latest[_latest["Player_ID"].astype(str).isin(_curr_pids)]

            _total = _latest[value_col].sum()
            if _total == 0:
                st.info("No contributions recorded.")
                return

            _latest = _latest.sort_values(value_col, ascending=False).reset_index(drop=True)
            _latest["pct"] = _latest[value_col] / _total * 100

            top10   = _latest.head(10)
            rest    = _latest.iloc[10:]
            top10_pct  = top10["pct"].sum()
            rest_pct   = rest["pct"].sum()
            top10_val  = int(top10[value_col].sum())
            rest_val   = int(rest[value_col].sum())

            # ── Pie chart ──
            import plotly.graph_objects as _go
            _labels = top10["Player"].tolist()
            _values = top10[value_col].tolist()
            _colors_pie = [
                "#FFD700","#C0C0C0","#CD7F32",
                "#4A90D9","#9B59B6","#2ECC71",
                "#E74C3C","#F39C12","#1ABC9C","#E67E22",
            ]
            if rest_pct > 0:
                _labels.append(f"Rest of guild ({len(rest)} players)")
                _values.append(int(rest_val))
                _colors_pie.append("#2A2D3A")

            _fig = _go.Figure(_go.Pie(
                labels=_labels, values=_values,
                hole=0.52,
                marker=dict(colors=_colors_pie[:len(_labels)],
                            line=dict(color="#0E1117", width=2)),
                textinfo="label+percent",
                textfont=dict(size=11),
                hovertemplate="<b>%{label}</b><br>%{value:,}<br>%{percent}<extra></extra>",
            ))
            _fig.update_layout(
                paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
                font=dict(color="#E8E8E8", family="Inter, sans-serif"),
                margin=dict(l=10, r=10, t=40, b=10),
                height=420,
                title=dict(text=f"Contribution Share — {season_label}", font=dict(size=15)),
                showlegend=False,
            )
            st.plotly_chart(_fig, width="stretch")

            # ── Summary KPI strip ──
            k1, k2, k3 = st.columns(3)
            with k1:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-label">Total {value_col}</div>
                    <div class="metric-value">{int(_total):,}</div>
                </div>""", unsafe_allow_html=True)
            with k2:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-label">Top 10 Share</div>
                    <div class="metric-value" style="color:#FFD700;">{top10_pct:.1f}%</div>
                    <div style="color:#C8CBD8;font-size:0.8rem;">{top10_val:,} {value_col.lower()}</div>
                </div>""", unsafe_allow_html=True)
            with k3:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-label">Rest of Guild Share</div>
                    <div class="metric-value" style="color:#4A90D9;">{rest_pct:.1f}%</div>
                    <div style="color:#C8CBD8;font-size:0.8rem;">{rest_val:,} {value_col.lower()}</div>
                </div>""", unsafe_allow_html=True)

            # ── KPI strip only, no per-player breakdown ──
            pass  # breakdown removed — see Player Breakdown section below

        with _metric_tabs[0]:
            if not gbg_df.empty:
                _gbg_seasons = sort_seasons(gbg_df["season"].unique().tolist())
                _contribution_chart(gbg_df, "Fights", _gbg_seasons[-1], "#FFD700", "#2A2D3A")
            else:
                st.info("No GBG data yet.")

        with _metric_tabs[1]:
            if not qi_df.empty:
                _qi_seasons = sort_seasons(qi_df["season"].unique().tolist())
                _contribution_chart(qi_df, "Progress", _qi_seasons[-1], "#9B59B6", "#2A2D3A")
            else:
                st.info("No QI data yet.")

        st.markdown("---")

        # ── Guild Timeline ────────────────────────────────────────────────
        st.markdown('<div class="section-title">📅 Guild Season Timeline</div>', unsafe_allow_html=True)

        _tl_tabs = st.tabs(["⚔️ GBG Fights", "🌀 QI Progress"])

        def _timeline_chart(df, value_col, colour, min_line=None):
            if df.empty:
                st.info("No data yet.")
                return
            from modules.comparisons import sort_seasons as _ss
            import plotly.graph_objects as _go

            _seasons  = _ss(df["season"].unique().tolist())
            _totals   = [int(df[df["season"] == s][value_col].sum()) for s in _seasons]
            _max_val  = max(_totals) if _totals else 1

            fig = _go.Figure()

            # Bar chart
            _bar_colors = []
            for v in _totals:
                if min_line and v < min_line:
                    _bar_colors.append("#E74C3C")
                else:
                    _bar_colors.append(colour)

            fig.add_trace(_go.Bar(
                x=_seasons, y=_totals,
                marker=dict(color=_bar_colors, line=dict(width=0)),
                text=[f"{v/1e6:.1f}M" if v >= 1_000_000 else f"{v:,}" for v in _totals],
                textposition="outside",
                textfont=dict(color="#E8E8E8", size=11),
                hovertemplate="<b>%{x}</b><br>" + value_col + ": %{y:,}<extra></extra>",
                name=value_col,
            ))

            # Trend line
            if len(_totals) > 1:
                fig.add_trace(_go.Scatter(
                    x=_seasons, y=_totals,
                    mode="lines+markers",
                    line=dict(color="rgba(255,255,255,0.25)", width=2, dash="dot"),
                    marker=dict(size=6, color=colour),
                    showlegend=False,
                    hoverinfo="skip",
                ))

            fig.update_layout(
                paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
                font=dict(color="#E8E8E8", family="Inter, sans-serif"),
                margin=dict(l=20, r=20, t=30, b=60),
                height=320,
                xaxis=dict(
                    gridcolor="rgba(0,0,0,0)", linecolor="#2A2D3A",
                    tickangle=-30, tickfont=dict(size=11),
                ),
                yaxis=dict(gridcolor="#1A1D27", linecolor="#2A2D3A", tickformat=".2s"),
                bargap=0.25,
                showlegend=False,
            )
            st.plotly_chart(fig, width="stretch")

            # Season-by-season bar cards
            _prev = None
            _tl_cards_html = ""
            for s, v in zip(_seasons, _totals):
                _delta_html = ""
                if _prev is not None:
                    _d    = v - _prev
                    _sign = "+" if _d >= 0 else ""
                    _dc   = "#2ECC71" if _d >= 0 else "#E74C3C"
                    _delta_html = f'<span style="color:{_dc};font-size:0.8rem;font-weight:600;margin-left:10px;">{_sign}{_d:,}</span>'
                _bar_w = int(v / max(_max_val, 1) * 100)
                _bar_c = "#E74C3C" if (min_line and v < min_line) else colour
                _v_str = f"{v:,}"
                _tl_cards_html += (
                    '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;'
                    'padding:10px 16px;margin-bottom:5px;">'
                    '<div style="display:flex;align-items:center;justify-content:space-between;">'
                    f'<div style="color:#C8CBD8;font-weight:600;font-size:0.88rem;">{s}</div>'
                    '<div style="display:flex;align-items:center;">'
                    f'<span style="color:{_bar_c};font-weight:800;font-size:1rem;">{_v_str}</span>'
                    + _delta_html +
                    '</div>'
                    '</div>'
                    '<div style="background:#0E1117;border-radius:4px;height:5px;margin-top:8px;">'
                    f'<div style="background:{_bar_c};width:{_bar_w}%;height:5px;border-radius:4px;"></div>'
                    '</div>'
                    '</div>'
                )
                _prev = v
            st.markdown(_tl_cards_html, unsafe_allow_html=True)

        with _tl_tabs[0]:
            _timeline_chart(gbg_df, "Fights", "#FFD700")

        with _tl_tabs[1]:
            _timeline_chart(qi_df, "Progress", "#9B59B6")

        st.markdown("---")

        # ── Roster Boost Analysis ─────────────────────────────────────────
        if not guild_stats_df.empty and "gbg_attack" in guild_stats_df.columns:
            st.markdown('<div class="section-title">💪 Roster Boost Analysis</div>', unsafe_allow_html=True)
            _bdf = guild_stats_df.copy()
            if "status" in _bdf.columns:
                _bdf = _bdf[_bdf["status"] == "ok"]
            for _bcol in ["gbg_attack","gbg_defense","gbg_defending_units_attack","gbg_defending_units_defense","critical_hit"]:
                if _bcol in _bdf.columns:
                    _bdf[_bcol] = pd.to_numeric(_bdf[_bcol], errors="coerce")

            # ── Boost vs Fights scatter ───────────────────────────────────
            if not gbg_df.empty:
                _sc_lat = sort_seasons(gbg_df["season"].unique().tolist())[-1]
                _sc_fights = gbg_df[gbg_df["season"]==_sc_lat].groupby("Player")["Fights"].sum().reset_index()
                _sc_fights.columns = ["player_name", "Fights"]
                _sc_base = _bdf[["player_name","gbg_attack","gbg_defending_units_attack"]].merge(_sc_fights, on="player_name", how="inner").dropna(subset=["Fights"])
                if not _sc_base.empty:
                    import plotly.graph_objects as _go_sc
                    _sc_avg_fights = float(_sc_base["Fights"].mean())
                    _fig_sc = _go_sc.Figure()
                    # Red trace — attacking units
                    _sc_red = _sc_base.dropna(subset=["gbg_attack"])
                    if not _sc_red.empty:
                        _fig_sc.add_trace(_go_sc.Scatter(
                            x=_sc_red["gbg_attack"], y=_sc_red["Fights"],
                            mode="markers+text", name="Attacking Units",
                            text=_sc_red["player_name"], textposition="top center",
                            textfont=dict(size=8, color="#E74C3C"),
                            marker=dict(size=10, color="#E74C3C", opacity=0.85, line=dict(color="#0E1117", width=1)),
                            hovertemplate="<b>%{text}</b><br>Atk Units Attack: %{x:,}%<br>Fights: %{y:,}<extra></extra>",
                        ))
                        _fig_sc.add_vline(x=float(_sc_red["gbg_attack"].mean()), line_dash="dot", line_color="#E74C3C",
                                          opacity=0.4, annotation_text=f"avg atk {int(_sc_red['gbg_attack'].mean()):,}%", annotation_font_color="#E74C3C")
                    # Blue trace — defending units
                    _sc_blue = _sc_base.dropna(subset=["gbg_defending_units_attack"])
                    if not _sc_blue.empty:
                        _fig_sc.add_trace(_go_sc.Scatter(
                            x=_sc_blue["gbg_defending_units_attack"], y=_sc_blue["Fights"],
                            mode="markers+text", name="Defending Units",
                            text=_sc_blue["player_name"], textposition="bottom center",
                            textfont=dict(size=8, color="#4A90D9"),
                            marker=dict(size=10, color="#4A90D9", opacity=0.85, line=dict(color="#0E1117", width=1)),
                            hovertemplate="<b>%{text}</b><br>Def Units Attack: %{x:,}%<br>Fights: %{y:,}<extra></extra>",
                        ))
                        _fig_sc.add_vline(x=float(_sc_blue["gbg_defending_units_attack"].mean()), line_dash="dot", line_color="#4A90D9",
                                          opacity=0.4, annotation_text=f"avg def atk {int(_sc_blue['gbg_defending_units_attack'].mean()):,}%", annotation_font_color="#4A90D9")
                    _fig_sc.add_hline(y=_sc_avg_fights, line_dash="dash", line_color="#2A2D3A", opacity=0.6,
                                      annotation_text=f"avg fights {int(_sc_avg_fights):,}", annotation_font_color="#A8ABB8")
                    _fig_sc.update_layout(
                        title=dict(text=f"GBG Boost vs Fights — {_sc_lat}  🔴 Attacking Units  🔵 Defending Units", font=dict(size=13, color="#E8E8E8")),
                        xaxis=dict(title="Boost (%)", gridcolor="#1A1D27", color="#C8CBD8", zerolinecolor="#2A2D3A"),
                        yaxis=dict(title="Fights This Season", gridcolor="#1A1D27", color="#C8CBD8", zerolinecolor="#2A2D3A"),
                        paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
                        font=dict(color="#E8E8E8", family="Inter, sans-serif"),
                        legend=dict(bgcolor="#1A1D27", bordercolor="#2A2D3A", borderwidth=1),
                        margin=dict(l=10, r=10, t=50, b=10), height=500,
                    )
                    st.plotly_chart(_fig_sc, width="stretch")
                    st.markdown(
                        '<div style="color:#A8ABB8;font-size:0.72rem;margin-top:-8px;margin-bottom:16px;">'
                        '🔴 Attacking units · 🔵 Defending units. '
                        'Dashed line = avg fights. Dotted lines = avg boost per type. '
                        'Top-right: high boost + high output. Bottom-right: high boost, underperforming.'
                        '</div>', unsafe_allow_html=True)

            # ── Crit distribution + Top/Bottom 5 ─────────────────────────
            _bm1, _bm2 = st.columns(2)

            with _bm1:
                st.markdown('<div class="section-title">🎯 Crit Chance Distribution</div>', unsafe_allow_html=True)
                _crit_s = _bdf["critical_hit"].dropna()
                if not _crit_s.empty:
                    import plotly.graph_objects as _go_cr
                    _fig_cr = _go_cr.Figure(_go_cr.Histogram(
                        x=_crit_s, nbinsx=15,
                        marker=dict(color="#FFD700", opacity=0.85,
                                    line=dict(color="#0E1117", width=1)),
                        hovertemplate="Crit: %{x:.1f}%<br>Players: %{y}<extra></extra>",
                    ))
                    _fig_cr.update_layout(
                        xaxis=dict(title="Critical Hit %", gridcolor="#1A1D27", color="#C8CBD8"),
                        yaxis=dict(title="Players",         gridcolor="#1A1D27", color="#C8CBD8"),
                        paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
                        font=dict(color="#E8E8E8"), margin=dict(l=10, r=10, t=20, b=10), height=300,
                    )
                    st.plotly_chart(_fig_cr, width="stretch")
                    st.markdown(
                        f'<div style="display:flex;gap:20px;margin-top:4px;">'
                        f'<span style="color:#C8CBD8;font-size:0.78rem;">Avg: <b style="color:#FFD700;">{float(_crit_s.mean()):.2f}%</b></span>'
                        f'<span style="color:#C8CBD8;font-size:0.78rem;">Max: <b style="color:#FFD700;">{float(_crit_s.max()):.2f}%</b></span>'
                        f'<span style="color:#C8CBD8;font-size:0.78rem;">Players with crit: <b style="color:#FFD700;">{int((_crit_s > 0).sum())}</b></span>'
                        f'</div>', unsafe_allow_html=True)

            with _bm2:
                st.markdown('<div class="section-title">⚔️ GBG Attack — Top 5 & Bottom 5</div>', unsafe_allow_html=True)

                def _boost_rank_cards(df, col, unit_colour, label):
                    _ranked = df[["player_name", col]].dropna().sort_values(col, ascending=False).reset_index(drop=True)
                    if len(_ranked) < 2:
                        return
                    _col_max = float(_ranked[col].iloc[0])
                    def _rc(i, name, val):
                        _bar   = int(val / max(_col_max, 1) * 100)
                        _medal = {0:"🥇",1:"🥈",2:"🥉"}.get(i, f"#{i+1}")
                        return (
                            f'<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:7px;'
                            f'padding:6px 10px;margin-bottom:3px;">'
                            f'<div style="display:flex;align-items:center;justify-content:space-between;">'
                            f'<div style="display:flex;align-items:center;gap:5px;">'
                            f'<span style="font-size:0.78rem;">{_medal}</span>'
                            f'<span style="color:#E8E8E8;font-size:0.78rem;font-weight:600;">{name}</span>'
                            f'</div>'
                            f'<span style="color:{unit_colour};font-weight:700;font-size:0.78rem;">{int(val):,}%</span>'
                            f'</div>'
                            f'<div style="background:#0E1117;border-radius:3px;height:2px;margin-top:4px;">'
                            f'<div style="background:{unit_colour};width:{_bar}%;height:2px;border-radius:3px;"></div>'
                            f'</div></div>'
                        )
                    st.markdown(f'<div style="color:{unit_colour};font-size:0.72rem;font-weight:700;margin-bottom:3px;">{label} — Top 5</div>', unsafe_allow_html=True)
                    for _i, _r in _ranked.head(5).iterrows():
                        st.markdown(_rc(_i, _r["player_name"], float(_r[col])), unsafe_allow_html=True)
                    st.markdown(f'<div style="color:{unit_colour};font-size:0.72rem;font-weight:700;margin:6px 0 3px;">{label} — Bottom 5</div>', unsafe_allow_html=True)
                    for _i, _r in enumerate(_ranked.tail(5).iloc[::-1].itertuples()):
                        st.markdown(_rc(_i, _r.player_name, float(getattr(_r, col))), unsafe_allow_html=True)

                _br1, _br2 = st.columns(2)
                with _br1:
                    _boost_rank_cards(_bdf, "gbg_attack", "#E74C3C", "🔴 Attacking Units")
                with _br2:
                    _boost_rank_cards(_bdf, "gbg_defending_units_attack", "#4A90D9", "🔵 Defending Units")

            st.markdown("---")

        # ── Member leaderboards (Points / Goods / Battles / Streaks) ────────
        st.markdown('<div class="section-title">🏅 Member Leaderboards</div>', unsafe_allow_html=True)
        ml1, ml2, ml3, ml4 = st.columns(4)

        def _leaderboard_cards(title, icon, data, value_key, value_label, value_color, sub_key=None):
            st.markdown(f'<div class="section-title">{icon} {title}</div>', unsafe_allow_html=True)
            if not data:
                st.info("No member data yet.")
                return
            medal_map = {0:"🥇", 1:"🥈", 2:"🥉"}
            max_val   = data[0][value_key] if data else 1

            def _lb_row(i, row, show_avatar):
                medal   = medal_map.get(i, f"#{i+1}")
                bar_pct = int(row[value_key] / max(max_val, 1) * 100)
                bar_col = "#FFD700" if i==0 else "#C0C0C0" if i==1 else "#CD7F32" if i==2 else value_color
                val_str = f"{row[value_key]:,}"
                sub_str = row.get(sub_key, "") if sub_key else ""
                av      = get_avatar_html(row["player"], size=28) if show_avatar else ""
                av_html = '<div style="flex-shrink:0;">' + av + '</div>' if av else ""
                sub_html = '<div style="color:#C8CBD8;font-size:0.7rem;">' + sub_str + '</div>' if sub_str else ""
                return (
                    '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;'
                    'padding:10px 14px;margin-bottom:6px;">'
                    '<div style="display:flex;align-items:center;justify-content:space-between;">'
                    '<div style="display:flex;align-items:center;gap:8px;">'
                    '<span style="font-size:1rem;">' + medal + '</span>'
                    + av_html +
                    '<div>'
                    '<div style="color:#E8E8E8;font-weight:700;font-size:0.88rem;">' + row["player"] + '</div>'
                    + sub_html +
                    '</div>'
                    '</div>'
                    '<div style="text-align:right;">'
                    '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">' + value_label + '</div>'
                    '<div style="color:' + value_color + ';font-weight:800;font-size:0.9rem;">' + val_str + '</div>'
                    '</div>'
                    '</div>'
                    '<div style="background:#0E1117;border-radius:4px;height:3px;margin-top:7px;">'
                    '<div style="background:' + bar_col + ';width:' + str(bar_pct) + '%;height:3px;border-radius:4px;"></div>'
                    '</div>'
                    '</div>'
                )

            top_html = "".join(_lb_row(i, row, show_avatar=True) for i, row in enumerate(data[:5]))
            st.markdown(top_html, unsafe_allow_html=True)
            if len(data) > 5:
                with st.expander(f"Show more ({len(data) - 5} more)"):
                    rest_html = "".join(_lb_row(i, row, show_avatar=False) for i, row in enumerate(data[5:], 5))
                    st.markdown(rest_html, unsafe_allow_html=True)

        with ml1:
            pts_data = get_points_leaderboard(members_df, gbg_df, qi_df)
            _leaderboard_cards("Top Points", "🏅", pts_data, "points", "Points", "#FFD700", "eraName")
        with ml2:
            goods_data = get_goods_leaderboard(members_df, gbg_df, qi_df)
            _leaderboard_cards("Top Guild Goods Daily", "📦", goods_data, "guildgoods", "Goods/Day", "#4A90D9", "eraName")
        with ml3:
            battles_data = get_battles_leaderboard(members_df, gbg_df, qi_df)
            _leaderboard_cards("Top Won Battles", gbg_icon(20), battles_data, "won_battles", "Won Battles", "#2ECC71", "eraName")

        with ml4:
            st.markdown('<div class="section-title">🔥 Player Streaks</div>', unsafe_allow_html=True)
            st.markdown(
                '<div style="color:#C8CBD8;font-size:0.7rem;margin-bottom:8px;">'
                'Seasons with 4,000+ GBG fights</div>',
                unsafe_allow_html=True,
            )
            if gbg_df.empty:
                st.info("No GBG data yet.")
            else:
                # Current players only
                from modules.comparisons import sort_seasons as _ss4
                _latest_s4   = _ss4(gbg_df["season"].unique().tolist())[-1]
                _curr_pids4  = set(gbg_df[gbg_df["season"] == _latest_s4]["Player_ID"].astype(str))
                _streak_df   = gbg_df[gbg_df["Player_ID"].astype(str).isin(_curr_pids4)].copy()

                # Count seasons ≥ 4000 per player
                _counts = (
                    _streak_df[_streak_df["Fights"] >= 4000]
                    .groupby(["Player_ID", "Player"])
                    .size()
                    .reset_index(name="seasons_above")
                    .sort_values("seasons_above", ascending=False)
                    .head(10)
                    .reset_index(drop=True)
                )

                if _counts.empty:
                    st.info("No players with 4,000+ fights yet.")
                else:
                    _medal_map4 = {0:"🥇", 1:"🥈", 2:"🥉"}
                    _max4 = int(_counts["seasons_above"].iloc[0])

                    def _streak_row(_i, _r, show_avatar):
                        _medal4 = _medal_map4.get(_i, f"#{_i+1}")
                        _cnt    = int(_r["seasons_above"])
                        _bar_w4 = int(_cnt / max(_max4, 1) * 100)
                        _bar_c4 = "#FFD700" if _i==0 else "#C0C0C0" if _i==1 else "#CD7F32" if _i==2 else "#E74C3C"
                        _curr_fights = gbg_df[
                            (gbg_df["Player_ID"].astype(str) == str(_r["Player_ID"])) &
                            (gbg_df["season"] == _latest_s4)
                        ]["Fights"].sum()
                        _on_fire  = "🔥" if int(_curr_fights) >= 4000 else ""
                        _s4_av    = get_avatar_html(_r["Player"], size=28) if show_avatar else ""
                        _s4_avblk = '<div style="flex-shrink:0;">' + _s4_av + '</div>' if _s4_av else ""
                        return (
                            '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:10px;'
                            'padding:10px 14px;margin-bottom:6px;">'
                            '<div style="display:flex;align-items:center;justify-content:space-between;">'
                            '<div style="display:flex;align-items:center;gap:8px;">'
                            '<span style="font-size:1rem;">' + _medal4 + '</span>'
                            + _s4_avblk +
                            '<div style="color:#E8E8E8;font-weight:700;font-size:0.88rem;">'
                            + _r["Player"] + ' ' + _on_fire +
                            '</div>'
                            '</div>'
                            '<div style="text-align:right;">'
                            '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">Seasons</div>'
                            '<div style="color:#E74C3C;font-weight:800;font-size:0.9rem;">' + str(_cnt) + '</div>'
                            '</div>'
                            '</div>'
                            '<div style="background:#0E1117;border-radius:4px;height:3px;margin-top:7px;">'
                            '<div style="background:' + _bar_c4 + ';width:' + str(_bar_w4) + '%;height:3px;border-radius:4px;"></div>'
                            '</div>'
                            '</div>'
                        )

                    _counts_list = list(_counts.iterrows())
                    top_s_html = "".join(_streak_row(_i, _r, show_avatar=True) for _i, (_, _r) in enumerate(_counts_list[:5]))
                    st.markdown(top_s_html, unsafe_allow_html=True)
                    if len(_counts_list) > 5:
                        with st.expander(f"Show more ({len(_counts_list) - 5} more)"):
                            rest_s_html = "".join(_streak_row(_i, _r, show_avatar=False) for _i, (_, _r) in enumerate(_counts_list[5:], 5))
                            st.markdown(rest_s_html, unsafe_allow_html=True)

        st.markdown("---")

        # ── Season Activity Heatmap ───────────────────────────────────────
        st.markdown('<div class="section-title">🗓️ Season Activity Heatmap (GBG Fights)</div>', unsafe_allow_html=True)
        if not gbg_df.empty:
            st.plotly_chart(activity_heatmap(gbg_df), width="stretch")
        else:
            st.info("No GBG data yet.")
    _render_footer()


# ══════════════════════════════════════════════════════════════════════════
# PAGE: HALL OF FAME
# ══════════════════════════════════════════════════════════════════════════
elif page == "🏆 Hall of Fame":
    log_event(st.session_state.get("current_user",""), "Hall of Fame", "visit")
    st.markdown("# 🏆 Hall of Fame")

    # ── Helper: render one ranked card ───────────────────────────────────
    def _hof_card(rank, name, primary_val, primary_label, primary_colour,
                  sub_lines=None, bar_pct=100, avatar_html=""):
        """Returns an HTML string — caller is responsible for rendering."""
        medal   = {1:"🥇", 2:"🥈", 3:"🥉"}.get(rank, f"#{rank}")
        bar_col = "#FFD700" if rank==1 else "#C0C0C0" if rank==2 else "#CD7F32" if rank==3 else "#4A90D9"
        subs    = "".join(
            '<div style="color:#C8CBD8;font-size:0.75rem;margin-top:3px;">' + l + '</div>'
            for l in (sub_lines or [])
        )
        av_block = '<div style="flex-shrink:0;">' + avatar_html + '</div>' if avatar_html else ""
        return (
            '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:12px;'
            'padding:14px 18px;margin-bottom:8px;">'
            '<div style="display:flex;align-items:center;gap:12px;">'
            '<div style="font-size:1.5rem;min-width:34px;">' + medal + '</div>'
            + av_block +
            '<div style="flex:1;">'
            '<div style="color:#E8E8E8;font-weight:800;font-size:1rem;">' + name + '</div>'
            + subs +
            '</div>'
            '<div style="text-align:right;">'
            '<div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;'
            'letter-spacing:0.5px;">' + primary_label + '</div>'
            '<div style="color:' + primary_colour + ';font-weight:800;font-size:1.15rem;">' + str(primary_val) + '</div>'
            '</div>'
            '</div>'
            '<div style="background:#0E1117;border-radius:4px;height:4px;margin-top:10px;">'
            '<div style="background:' + bar_col + ';width:' + str(bar_pct) + '%;height:4px;border-radius:4px;"></div>'
            '</div>'
            '</div>'
        )

    # ── Helper: render top-3 visible, rest in expander ───────────────────
    def _hof_section(rows, render_fn, empty_msg="No data yet."):
        """rows: list of dicts. render_fn(rank, row) returns HTML string."""
        if not rows:
            st.info(empty_msg)
            return
        top_html = "".join(render_fn(rank, row) for rank, row in enumerate(rows[:5], 1))
        st.markdown(top_html, unsafe_allow_html=True)
        if len(rows) > 5:
            with st.expander(f"Show more ({len(rows) - 5} more)"):
                rest_html = "".join(render_fn(rank, row) for rank, row in enumerate(rows[5:], 6))
                st.markdown(rest_html, unsafe_allow_html=True)

    # ── Compute current player set ────────────────────────────────────────
    if not gbg_df.empty:
        from modules.comparisons import sort_seasons as _ss_hof
        _hof_gbg_seasons = _ss_hof(gbg_df["season"].unique().tolist())
        _hof_latest      = _hof_gbg_seasons[-1]
        _hof_curr_pids   = set(gbg_df[gbg_df["season"] == _hof_latest]["Player_ID"].astype(str))
    else:
        _hof_curr_pids = set()

    # ── Row 1: All-Time #1 Finishers + Iron Player ────────────────────────
    row1_col1, row1_col2 = st.columns(2)

    with row1_col1:
        st.markdown('<div class="section-title">🏆 All-Time #1 Finishers</div>', unsafe_allow_html=True)
        hof_data = _load_hall_of_fame(gbg_df, qi_df)
        _max_hof = hof_data[0]["total"] if hof_data else 1
        def _render_hof(rank, row):
            gbg_b = f'{gbg_icon(14)} {row["gbg_wins"]}× GBG' if row["gbg_wins"] else ""
            qi_b  = f'{qi_icon(14)} {row["qi_wins"]}× QI'   if row["qi_wins"]  else ""
            av = get_avatar_html(row["player"], size=36) if rank <= 5 else ""
            return _hof_card(rank, row["player"], f'{row["total"]} 🥇', "Season Wins", "#FFD700",
                             sub_lines=[s for s in [gbg_b, qi_b] if s],
                             bar_pct=int(row["total"] / max(_max_hof, 1) * 100),
                             avatar_html=av)
        _hof_section(hof_data, _render_hof, "No season winners recorded yet.")

    with row1_col2:
        st.markdown('<div class="section-title">🛡️ Iron Player</div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:10px;">'
            'Most seasons played without missing GBG or QI</div>',
            unsafe_allow_html=True)
        if gbg_df.empty or qi_df.empty:
            st.info("Need both GBG and QI data.")
        else:
            from modules.comparisons import sort_seasons as _ss_iron
            _gbg_s   = set(_ss_iron(gbg_df["season"].unique().tolist()))
            _qi_s    = set(_ss_iron(qi_df["season"].unique().tolist()))
            _shared_s = _gbg_s & _qi_s   # seasons that appear in both

            _iron_rows = []
            for _pid in _hof_curr_pids:
                _pid_gbg     = set(gbg_df[gbg_df["Player_ID"].astype(str) == _pid]["season"])
                _pid_qi      = set(qi_df[qi_df["Player_ID"].astype(str) == _pid]["season"])
                _played_both = _shared_s & _pid_gbg & _pid_qi
                _name = (gbg_df[gbg_df["Player_ID"].astype(str) == _pid]["Player"].iloc[0]
                         if not gbg_df[gbg_df["Player_ID"].astype(str) == _pid].empty else _pid)
                # Total activity for tiebreaking
                _total_f = int(gbg_df[gbg_df["Player_ID"].astype(str) == _pid]["Fights"].sum())
                _total_q = int(qi_df[qi_df["Player_ID"].astype(str) == _pid]["Progress"].sum())
                _iron_rows.append({
                    "player": _name,
                    "seasons": len(_played_both),
                    "gbg_seasons": len(_pid_gbg),
                    "qi_seasons": len(_pid_qi),
                    "total_fights": _total_f,
                    "total_progress": _total_q,
                })

            _iron_rows = sorted(
                _iron_rows,
                key=lambda x: (x["seasons"], x["total_fights"] + x["total_progress"]),
                reverse=True
            )[:10]
            _max_iron = _iron_rows[0]["seasons"] if _iron_rows else 1
            def _render_iron(rank, row):
                av = get_avatar_html(row["player"], size=36) if rank <= 5 else ""
                return _hof_card(rank, row["player"], str(row["seasons"]), "Both Rounds", "#4A90D9",
                                 sub_lines=[
                                     f'{gbg_icon(14)} {row["gbg_seasons"]} GBG · {qi_icon(14)} {row["qi_seasons"]} QI seasons',
                                     f'Total: {row["total_fights"]:,} fights · {row["total_progress"]:,} progress',
                                 ],
                                 bar_pct=int(row["seasons"] / max(_max_iron, 1) * 100),
                                 avatar_html=av)
            _hof_section(_iron_rows, _render_iron)

    st.markdown("---")

    # ── Row 2: Double Threat + Guild MVP ─────────────────────────────────
    row2_col1, row2_col2 = st.columns(2)

    with row2_col1:
        st.markdown('<div class="section-title">⚡ Double Threat</div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:10px;">'
            'Highest combined all-time GBG fights + QI progress</div>',
            unsafe_allow_html=True)
        if gbg_df.empty or qi_df.empty:
            st.info("Need both GBG and QI data.")
        else:
            _gbg_totals = (gbg_df[gbg_df["Player_ID"].astype(str).isin(_hof_curr_pids)]
                           .groupby(["Player_ID","Player"])["Fights"].sum()
                           .reset_index().rename(columns={"Fights":"total_fights"}))
            _qi_totals  = (qi_df[qi_df["Player_ID"].astype(str).isin(_hof_curr_pids)]
                           .groupby(["Player_ID","Player"])["Progress"].sum()
                           .reset_index().rename(columns={"Progress":"total_progress"}))
            _dt = _gbg_totals.merge(_qi_totals, on="Player_ID", how="outer", suffixes=("","_qi"))
            _dt["Player"]         = _dt["Player"].fillna(_dt["Player_qi"])
            _dt["total_fights"]   = _dt["total_fights"].fillna(0).astype(int)
            _dt["total_progress"] = _dt["total_progress"].fillna(0).astype(int)
            # Normalise each to 0-100 then sum for combined score
            _f_max = max(_dt["total_fights"].max(), 1)
            _p_max = max(_dt["total_progress"].max(), 1)
            _dt["score"] = (_dt["total_fights"] / _f_max * 50 +
                            _dt["total_progress"] / _p_max * 50)
            _dt = _dt.sort_values("score", ascending=False).head(10).reset_index(drop=True)
            _max_score = _dt["score"].iloc[0] if not _dt.empty else 1
            def _render_dt(rank, row):
                av = get_avatar_html(row["Player"], size=36) if rank <= 5 else ""
                return _hof_card(rank, row["Player"], f'{row["score"]:.0f} pts', "Combined Score", "#9B59B6",
                                 sub_lines=[f'{gbg_icon(14)} {int(row["total_fights"]):,} fights · {qi_icon(14)} {int(row["total_progress"]):,} progress'],
                                 bar_pct=int(row["score"] / max(_max_score, 1) * 100),
                                 avatar_html=av)
            _hof_section(_dt.to_dict("records"), _render_dt)

    with row2_col2:
        st.markdown('<div class="section-title">👑 Guild MVP</div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:10px;">'
            'Composite score: GBG fights + QI progress + guild points + goods</div>',
            unsafe_allow_html=True)

        _mvp_rows = []
        for _pid in _hof_curr_pids:
            _pid_s = str(_pid)
            # GBG fights (normalised)
            _f = int(gbg_df[gbg_df["Player_ID"].astype(str) == _pid_s]["Fights"].sum()) if not gbg_df.empty else 0
            # QI progress (normalised)
            _q = int(qi_df[qi_df["Player_ID"].astype(str) == _pid_s]["Progress"].sum()) if not qi_df.empty else 0
            # Member stats
            _mem = get_latest_member_stats(members_df, _pid_s)
            _pts = int(_mem.get("points", 0))    if _mem else 0
            _gg  = int(_mem.get("guildgoods", 0)) if _mem else 0
            _name = (gbg_df[gbg_df["Player_ID"].astype(str) == _pid_s]["Player"].iloc[0]
                     if not gbg_df[gbg_df["Player_ID"].astype(str) == _pid_s].empty else _pid_s)
            _mvp_rows.append({"player": _name, "fights": _f, "progress": _q,
                              "points": _pts, "goods": _gg})

        if not _mvp_rows:
            st.info("No data yet.")
        else:
            import pandas as _pd_mvp
            _mvp = _pd_mvp.DataFrame(_mvp_rows)
            # Normalise each component 0-100, weighted sum
            def _norm(s): return (s / s.max() * 100) if s.max() > 0 else s
            _mvp["score"] = (
                _norm(_mvp["fights"])   * 0.35 +
                _norm(_mvp["progress"]) * 0.30 +
                _norm(_mvp["points"])   * 0.20 +
                _norm(_mvp["goods"])    * 0.15
            )
            _mvp = _mvp.sort_values("score", ascending=False).head(10).reset_index(drop=True)
            _max_mvp = _mvp["score"].iloc[0]
            def _render_mvp(rank, row):
                av = get_avatar_html(row["player"], size=36) if rank <= 5 else ""
                return _hof_card(rank, row["player"], f'{row["score"]:.0f} pts', "MVP Score", "#FFD700",
                                 sub_lines=[
                                     f'{gbg_icon(14)} {int(row["fights"]):,} fights · {qi_icon(14)} {int(row["progress"]):,} QI',
                                     f'🏅 {int(row["points"]):,} pts · 📦 {int(row["goods"]):,} goods',
                                 ],
                                 bar_pct=int(row["score"] / max(_max_mvp, 1) * 100),
                                 avatar_html=av)
            _hof_section(_mvp.to_dict("records"), _render_mvp)

    st.markdown("---")

    # ── Row 3: Century Club + Elite Fighter + QI Legend ──────────────────
    row3_col1, row3_col2, row3_col3 = st.columns(3)

    with row3_col1:
        st.markdown('<div class="section-title">💯 Century Club</div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:10px;">'
            'Players who\'ve crossed lifetime fight milestones</div>',
            unsafe_allow_html=True)
        if gbg_df.empty:
            st.info("No GBG data yet.")
        else:
            _cc_totals = (
                gbg_df[gbg_df["Player_ID"].astype(str).isin(_hof_curr_pids)]
                .groupby(["Player_ID", "Player"])["Fights"]
                .sum().reset_index()
                .rename(columns={"Fights": "total_fights"})
                .sort_values("total_fights", ascending=False)
                .reset_index(drop=True)
            )

            def _milestone_badge(v):
                if v >= 1_000_000:
                    return "1M+ 🌟", "#FFD700"
                elif v >= 500_000:
                    return "500K+ 💎", "#9B59B6"
                elif v >= 100_000:
                    return "100K+ 🔥", "#E74C3C"
                else:
                    return None, None

            _cc_shown = _cc_totals[_cc_totals["total_fights"] >= 100_000].reset_index(drop=True)
            if _cc_shown.empty:
                st.info("No players have reached 100,000 lifetime fights yet.")
            else:
                def _render_cc(rank, row):
                    _tf = int(row["total_fights"])
                    _badge, _badge_col = _milestone_badge(_tf)
                    if _tf >= 1_000_000:
                        _next, _prev = None, 1_000_000
                    elif _tf >= 500_000:
                        _next, _prev = 1_000_000, 500_000
                    else:
                        _next, _prev = 500_000, 100_000
                    _prog_to_next = int((_tf - _prev) / max((_next or _tf) - _prev, 1) * 100) if _next else 100
                    _next_label   = f"→ {_next//1000}K" if _next else "✅ Max tier"
                    _cc_medal     = {1:"🥇",2:"🥈",3:"🥉"}.get(rank, f"#{rank}")
                    _cc_av        = get_avatar_html(row["Player"], size=36) if rank <= 5 else ""
                    _cc_av_block  = '<div style="flex-shrink:0;">' + _cc_av + '</div>' if _cc_av else ""
                    return (
                        '<div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:12px;'
                        'padding:14px 18px;margin-bottom:8px;">'
                        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">'
                        '<div style="font-size:1.3rem;min-width:30px;">' + _cc_medal + '</div>'
                        + _cc_av_block +
                        '<div style="flex:1;">'
                        '<div style="color:#E8E8E8;font-weight:800;font-size:0.95rem;">' + row["Player"] + '</div>'
                        '<div style="color:#C8CBD8;font-size:0.75rem;margin-top:2px;">' + f'{_tf:,}' + ' lifetime fights</div>'
                        '</div>'
                        '<div style="background:#0E1117;border-radius:20px;padding:4px 10px;">'
                        '<span style="color:' + _badge_col + ';font-weight:800;font-size:0.85rem;">' + _badge + '</span>'
                        '</div>'
                        '</div>'
                        '<div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
                        '<div style="color:#A8ABB8;font-size:0.68rem;">Progress to next tier</div>'
                        '<div style="color:#A8ABB8;font-size:0.68rem;">' + _next_label + '</div>'
                        '</div>'
                        '<div style="background:#0E1117;border-radius:4px;height:5px;">'
                        '<div style="background:' + _badge_col + ';width:' + str(_prog_to_next) + '%;height:5px;border-radius:4px;"></div>'
                        '</div>'
                        '</div>'
                    )
                _hof_section(_cc_shown.to_dict("records"), _render_cc)

    with row3_col2:
        st.markdown(f'<div class="section-title">{gbg_icon(20)} Elite Fighter</div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:10px;">'
            'Most seasons with 5,000+ GBG fights</div>',
            unsafe_allow_html=True)
        if gbg_df.empty:
            st.info("No GBG data yet.")
        else:
            _ef = (
                gbg_df[gbg_df["Player_ID"].astype(str).isin(_hof_curr_pids)]
                [gbg_df["Fights"] >= 5000]
                .groupby(["Player_ID", "Player"])
                .agg(elite_seasons=("Fights", "count"),
                     best_season=("Fights", "max"))
                .reset_index()
                .sort_values(["elite_seasons", "best_season"], ascending=False)
                .head(10).reset_index(drop=True)
            )
            if _ef.empty:
                st.info("No players have 5,000+ fights in a season yet.")
            else:
                _max_ef = int(_ef["elite_seasons"].iloc[0])
                def _render_ef(rank, row):
                    av = get_avatar_html(row["Player"], size=36) if rank <= 5 else ""
                    return _hof_card(rank, row["Player"], str(int(row["elite_seasons"])), "Elite Seasons", "#FFD700",
                                     sub_lines=[f'Best season: {int(row["best_season"]):,} fights'],
                                     bar_pct=int(int(row["elite_seasons"]) / max(_max_ef, 1) * 100),
                                     avatar_html=av)
                _hof_section(_ef.to_dict("records"), _render_ef,
                             "No players have 5,000+ fights in a season yet.")

    with row3_col3:
        st.markdown(f'<div class="section-title">{qi_icon(20)} QI Legend</div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:10px;">'
            'Most seasons with 10,000+ QI progress</div>',
            unsafe_allow_html=True)
        if qi_df.empty:
            st.info("No QI data yet.")
        else:
            _ql = (
                qi_df[qi_df["Player_ID"].astype(str).isin(_hof_curr_pids)]
                [qi_df["Progress"] >= 10000]
                .groupby(["Player_ID", "Player"])
                .agg(legend_seasons=("Progress", "count"),
                     best_season=("Progress", "max"))
                .reset_index()
                .sort_values(["legend_seasons", "best_season"], ascending=False)
                .head(10).reset_index(drop=True)
            )
            if _ql.empty:
                st.info("No players have 10,000+ QI progress in a season yet.")
            else:
                _max_ql = int(_ql["legend_seasons"].iloc[0])
                def _render_ql(rank, row):
                    av = get_avatar_html(row["Player"], size=36) if rank <= 5 else ""
                    return _hof_card(rank, row["Player"], str(int(row["legend_seasons"])), "Legend Seasons", "#9B59B6",
                                     sub_lines=[f'Best season: {int(row["best_season"]):,} progress'],
                                     bar_pct=int(int(row["legend_seasons"]) / max(_max_ql, 1) * 100),
                                     avatar_html=av)
                _hof_section(_ql.to_dict("records"), _render_ql,
                             "No players have 10,000+ QI progress in a season yet.")

    st.markdown("---")

    _gs4 = guild_stats_df.copy() if guild_stats_df is not None and not guild_stats_df.empty else None

    # ── Most Balanced — compact full-width strip ──────────────────────────
    st.markdown('<div class="section-title">⚖️ Most Balanced GBG Stats</div>', unsafe_allow_html=True)
    _bal_cols = ["gbg_attack", "gbg_defense", "gbg_defending_units_attack", "gbg_defending_units_defense"]
    if _gs4 is not None and all(c in _gs4.columns for c in _bal_cols):
        _bal = _gs4[["player_name"] + _bal_cols].dropna().copy()
        _bal["_red_gap"]  = (_bal["gbg_attack"]                - _bal["gbg_defense"]).abs()
        _bal["_blue_gap"] = (_bal["gbg_defending_units_attack"] - _bal["gbg_defending_units_defense"]).abs()
        _bal["_balance"]  = (_bal["_red_gap"] + _bal["_blue_gap"]) / 2
        _bal = _bal.sort_values("_balance").reset_index(drop=True)
        _bal_colours = ["#FFD700", "#C0C0C0", "#CD7F32", "#4A90D9", "#4A90D9"]
        _bal_html = '<div style="display:flex;flex-wrap:wrap;gap:6px 10px;padding:6px 0 12px;">'
        for i, (_, r) in enumerate(_bal.head(5).iterrows()):
            _gap = float(r["_balance"])
            _col = _bal_colours[i]
            _bal_html += (
                f'<span style="font-size:0.82rem;">'
                f'<span style="color:{_col};font-weight:700;">{r["player_name"]}</span>'
                f'<span style="color:#A8ABB8;margin-left:4px;">{_gap:.0f}% gap</span>'
                f'</span>'
                f'<span style="color:#2A2D3A;margin:0 4px;">·</span>'
            )
        _bal_html += '</div>'
        st.markdown(_bal_html, unsafe_allow_html=True)
    else:
        st.info("No boost data yet.")

    st.markdown("---")

    # ── Row 4: Best GBG Attack + Best GBG Defence ─────────────────────────
    row4_col1, row4_col2 = st.columns(2)

    with row4_col1:
        st.markdown('<div class="section-title">⚔️ Best GBG Attack</div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:10px;">'
            'Highest GBG attack boosts — 🔴 attacking units · 🔵 defending units</div>',
            unsafe_allow_html=True,
        )
        if _gs4 is None or "gbg_attack" not in _gs4.columns:
            st.info("No boost data yet.")
        else:
            # Red: attacking units attack
            _atk_red = _gs4[["player_name", "gbg_attack"]].dropna().sort_values("gbg_attack", ascending=False)
            st.markdown("**🔴 Attacking Units — Attack**", unsafe_allow_html=False)
            _max_atk_red = float(_atk_red["gbg_attack"].iloc[0]) if not _atk_red.empty else 1
            def _render_atk_red(rank, row):
                av = get_avatar_html(row["player_name"], size=36) if rank <= 5 else ""
                return _hof_card(rank, row["player_name"], f'{float(row["gbg_attack"]):.0f}%', "Attack Boost",
                                 "#E74C3C",
                                 bar_pct=int(float(row["gbg_attack"]) / max(_max_atk_red, 1) * 100),
                                 avatar_html=av)
            _hof_section(_atk_red.to_dict("records"), _render_atk_red, "No data.")

            # Blue: defending units attack
            if "gbg_defending_units_attack" in _gs4.columns:
                _atk_blue = _gs4[["player_name", "gbg_defending_units_attack"]].dropna().sort_values("gbg_defending_units_attack", ascending=False)
                st.markdown("**🔵 Defending Units — Attack**", unsafe_allow_html=False)
                _max_atk_blue = float(_atk_blue["gbg_defending_units_attack"].iloc[0]) if not _atk_blue.empty else 1
                def _render_atk_blue(rank, row):
                    av = get_avatar_html(row["player_name"], size=36) if rank <= 5 else ""
                    return _hof_card(rank, row["player_name"], f'{float(row["gbg_defending_units_attack"]):.0f}%', "Attack Boost",
                                     "#4A90D9",
                                     bar_pct=int(float(row["gbg_defending_units_attack"]) / max(_max_atk_blue, 1) * 100),
                                     avatar_html=av)
                _hof_section(_atk_blue.to_dict("records"), _render_atk_blue, "No data.")

    with row4_col2:
        st.markdown('<div class="section-title">🛡️ Best GBG Defence</div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:10px;">'
            'Highest GBG defence boosts — 🔴 attacking units · 🔵 defending units</div>',
            unsafe_allow_html=True,
        )
        if _gs4 is None or "gbg_defense" not in _gs4.columns:
            st.info("No boost data yet.")
        else:
            # Red: attacking units defence
            _def_red = _gs4[["player_name", "gbg_defense"]].dropna().sort_values("gbg_defense", ascending=False)
            st.markdown("**🔴 Attacking Units — Defence**", unsafe_allow_html=False)
            _max_def_red = float(_def_red["gbg_defense"].iloc[0]) if not _def_red.empty else 1
            def _render_def_red(rank, row):
                av = get_avatar_html(row["player_name"], size=36) if rank <= 5 else ""
                return _hof_card(rank, row["player_name"], f'{float(row["gbg_defense"]):.0f}%', "Defence Boost",
                                 "#E74C3C",
                                 bar_pct=int(float(row["gbg_defense"]) / max(_max_def_red, 1) * 100),
                                 avatar_html=av)
            _hof_section(_def_red.to_dict("records"), _render_def_red, "No data.")

            # Blue: defending units defence
            if "gbg_defending_units_defense" in _gs4.columns:
                _def_blue = _gs4[["player_name", "gbg_defending_units_defense"]].dropna().sort_values("gbg_defending_units_defense", ascending=False)
                st.markdown("**🔵 Defending Units — Defence**", unsafe_allow_html=False)
                _max_def_blue = float(_def_blue["gbg_defending_units_defense"].iloc[0]) if not _def_blue.empty else 1
                def _render_def_blue(rank, row):
                    av = get_avatar_html(row["player_name"], size=36) if rank <= 5 else ""
                    return _hof_card(rank, row["player_name"], f'{float(row["gbg_defending_units_defense"]):.0f}%', "Defence Boost",
                                     "#4A90D9",
                                     bar_pct=int(float(row["gbg_defending_units_defense"]) / max(_max_def_blue, 1) * 100),
                                     avatar_html=av)
                _hof_section(_def_blue.to_dict("records"), _render_def_blue, "No data.")


    st.markdown("---")

    # ── Row 5: Production metrics ─────────────────────────────────────────
    row5_col1, row5_col2, row5_col3 = st.columns(3)

    _gs5 = guild_stats_df.copy() if guild_stats_df is not None and not guild_stats_df.empty else None

    def _render_prod_col(col_title, col_key, colour, value_label, halve=False):
        st.markdown(f'<div class="section-title">{col_title}</div>', unsafe_allow_html=True)
        if _gs5 is None or col_key not in _gs5.columns:
            st.info("No production data yet.")
            return
        _prod_df = _gs5[["player_name", col_key]].copy()
        _prod_df[col_key] = pd.to_numeric(_prod_df[col_key], errors="coerce")
        if halve:
            _prod_df.loc[_prod_df["player_name"].str.strip().str.lower() != "kuniggsbog", col_key] /= 2
        _prod_df = _prod_df.dropna().sort_values(col_key, ascending=False).reset_index(drop=True)
        _max_prod = float(_prod_df[col_key].iloc[0]) if not _prod_df.empty else 1
        def _render_prod(rank, row):
            av = get_avatar_html(row["player_name"], size=36) if rank <= 5 else ""
            return _hof_card(rank, row["player_name"], f'{int(row[col_key]):,}', value_label, colour,
                             bar_pct=int(int(row[col_key]) / max(_max_prod, 1) * 100),
                             avatar_html=av)
        _hof_section(_prod_df.to_dict("records"), _render_prod, "No data.")

    with row5_col1:
        st.markdown(
            '<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:10px;">'
            'Highest daily forge point production</div>', unsafe_allow_html=True)
        _render_prod_col(
            f'{icon_html("forge_points.png", 18)} Best FP Production',
            "fp_production", "#E8E8E8", "FP / day", halve=True,
        )

    with row5_col2:
        st.markdown(
            '<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:10px;">'
            'Highest daily guild goods production</div>', unsafe_allow_html=True)
        _render_prod_col(
            f'{icon_html("guild_goods.png", 18)} Best Guild Goods',
            "guild_goods_production", "#4A90D9", "Guild Goods / day",
        )

    with row5_col3:
        st.markdown(
            '<div style="color:#C8CBD8;font-size:0.75rem;margin-bottom:10px;">'
            'Highest daily goods production</div>', unsafe_allow_html=True)
        _render_prod_col(
            f'{icon_html("Goods.webp", 18)} Best Goods Production',
            "goods_production", "#F39C12", "Goods / day",
        )

    _render_footer()


# ══════════════════════════════════════════════════════════════════════════
# PAGE: GUILD MINIMUMS
# ══════════════════════════════════════════════════════════════════════════
elif page == "⚠️ Guild Minimums":
    st.markdown("# ⚠️ Guild Minimums")
    st.markdown(
        '<div style="color:#C8CBD8;font-size:0.88rem;margin-bottom:20px;">'
        'Players with <b>more than 2 seasons</b> below the guild minimum. '
        'GBG minimum: <span style="color:#F39C12;font-weight:700;">1,000 fights</span> · '
        'QI minimum: <span style="color:#E67E22;font-weight:700;">3,000 progress</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── GBG last-season fights bar chart ─────────────────────────────────
    if not gbg_df.empty:
        import plotly.graph_objects as _go_mins
        from modules.comparisons import sort_seasons as _ss_mins

        _mins_seasons = _ss_mins(gbg_df["season"].unique().tolist())
        _mins_latest  = _mins_seasons[-1]
        _mins_df = (
            gbg_df[gbg_df["season"] == _mins_latest]
            .groupby("Player", as_index=False)["Fights"].sum()
            .sort_values("Fights", ascending=False)
        )
        _mins_colors = [
            "#2ECC71" if f >= 1000 else "#E74C3C" for f in _mins_df["Fights"]
        ]

        _fig_mins = _go_mins.Figure()
        _fig_mins.add_trace(_go_mins.Bar(
            x=_mins_df["Player"],
            y=_mins_df["Fights"],
            marker_color=_mins_colors,
            hovertemplate="%{x}: %{y:,} fights<extra></extra>",
        ))
        _fig_mins.add_hline(
            y=1000, line_width=3, line_color="#E74C3C", line_dash="solid",
            annotation_text="Min 1,000",
            annotation_position="right",
            annotation_font_size=13,
            annotation_font_color="#E74C3C",
        )
        _fig_mins.update_layout(
            title=f"GBG Fights — {_mins_latest}",
            title_font_color="#E8E8E8",
            xaxis_title=None,
            yaxis_title="Fights",
            plot_bgcolor="#0E1117",
            paper_bgcolor="#0E1117",
            font_color="#C8CBD8",
            height=500,
            margin=dict(l=60, r=40, t=50, b=120),
            xaxis=dict(tickangle=-45, gridcolor="#1A1D27"),
            yaxis=dict(gridcolor="#1A1D27"),
        )
        st.plotly_chart(_fig_mins, use_container_width=True)
        st.markdown("---")

    # ── QI last-season progress bar chart ─────────────────────────────────
    if not qi_df.empty:
        import plotly.graph_objects as _go_qi_mins
        from modules.comparisons import sort_seasons as _ss_qi_mins

        _qi_mins_seasons = _ss_qi_mins(qi_df["season"].unique().tolist())
        _qi_mins_latest  = _qi_mins_seasons[-1]
        _qi_mins_df = (
            qi_df[qi_df["season"] == _qi_mins_latest]
            .groupby("Player", as_index=False)["Progress"].sum()
            .sort_values("Progress", ascending=False)
        )
        _qi_mins_colors = [
            "#2ECC71" if p >= 3000 else "#E74C3C" for p in _qi_mins_df["Progress"]
        ]

        _fig_qi_mins = _go_qi_mins.Figure()
        _fig_qi_mins.add_trace(_go_qi_mins.Bar(
            x=_qi_mins_df["Player"],
            y=_qi_mins_df["Progress"],
            marker_color=_qi_mins_colors,
            hovertemplate="%{x}: %{y:,} progress<extra></extra>",
        ))
        _fig_qi_mins.add_hline(
            y=3000, line_width=3, line_color="#E74C3C", line_dash="solid",
            annotation_text="Min 3,000",
            annotation_position="right",
            annotation_font_size=13,
            annotation_font_color="#E74C3C",
        )
        _fig_qi_mins.update_layout(
            title=f"QI Progress — {_qi_mins_latest}",
            title_font_color="#E8E8E8",
            xaxis_title=None,
            yaxis_title="Progress",
            plot_bgcolor="#0E1117",
            paper_bgcolor="#0E1117",
            font_color="#C8CBD8",
            height=500,
            margin=dict(l=60, r=40, t=50, b=120),
            xaxis=dict(tickangle=-45, gridcolor="#1A1D27"),
            yaxis=dict(gridcolor="#1A1D27"),
        )
        st.plotly_chart(_fig_qi_mins, use_container_width=True)
        st.markdown("---")

    def _minimums_section(df, value_col, min_val, section_colour, section_label, season_label, icon):
        """Render top-10 offenders card list for one activity type."""
        st.markdown(f'<div class="section-title">{icon} {section_label} — Minimum {min_val:,}</div>',
                    unsafe_allow_html=True)
        if df.empty:
            st.info("No data yet.")
            return

        from modules.comparisons import sort_seasons as _ssm
        _seasons_m  = _ssm(df["season"].unique().tolist())
        _latest_m   = _seasons_m[-1]
        _curr_pids_m = set(df[df["season"] == _latest_m]["Player_ID"].astype(str))
        _df_curr    = df[df["Player_ID"].astype(str).isin(_curr_pids_m)].copy()

        # Count seasons below minimum per player
        _below = (
            _df_curr[_df_curr[value_col] < min_val]
            .groupby(["Player_ID", "Player"])
            .agg(
                seasons_below=(value_col, "count"),
                avg_value=(value_col, "mean"),
                min_value=(value_col, "min"),
                worst_season=("season", lambda s: _df_curr.loc[s.index].loc[
                    _df_curr.loc[s.index, value_col].idxmin(), "season"
                ]),
            )
            .reset_index()
            .query("seasons_below > 2")
            .sort_values("seasons_below", ascending=False)
            .head(10)
            .reset_index(drop=True)
        )

        if _below.empty:
            st.markdown(
                f'<div style="background:#1A3A1A;border:1px solid #2A4A2A;border-radius:10px;'
                f'padding:14px 18px;color:#2ECC71;font-weight:600;">✅ No current players have '
                f'more than 2 seasons below the {section_label} minimum.</div>',
                unsafe_allow_html=True,
            )
            return

        _max_below = int(_below["seasons_below"].iloc[0])
        _total_seasons = len(_seasons_m)

        for _i, (_, _r) in enumerate(_below.iterrows()):
            _medal   = {0:"🥇",1:"🥈",2:"🥉"}.get(_i, f"#{_i+1}")
            _cnt     = int(_r["seasons_below"])
            _avg     = int(_r["avg_value"])
            _worst_s = str(_r["worst_season"])
            _bar_w   = int(_cnt / max(_max_below, 1) * 100)
            _pct_seasons = int(_cnt / max(_total_seasons, 1) * 100)

            # Get current season value for this player
            _pid_str  = str(_r["Player_ID"])
            _curr_val = df[(df["Player_ID"].astype(str) == _pid_str) &
                           (df["season"] == _latest_m)][value_col].sum()
            _curr_val = int(_curr_val)
            _is_curr_below = _curr_val < min_val and _curr_val > 0
            _curr_badge = (
                f'<span style="background:#3A1A1A;color:#E74C3C;padding:2px 8px;'
                f'border-radius:12px;font-size:0.72rem;font-weight:700;margin-left:6px;">'
                f'⚠️ {_curr_val:,} this season</span>'
            ) if _is_curr_below else (
                f'<span style="background:#1A3A1A;color:#2ECC71;padding:2px 8px;'
                f'border-radius:12px;font-size:0.72rem;font-weight:700;margin-left:6px;">'
                f'✅ {_curr_val:,} this season</span>'
            ) if _curr_val > 0 else ""

            # Per-season mini breakdown for this player
            _player_seasons = _df_curr[_df_curr["Player_ID"].astype(str) == _pid_str].sort_values("season")
            _season_bars = ""
            for _, _ps in _player_seasons.iterrows():
                _sv   = int(_ps[value_col])
                _sc   = "#2ECC71" if _sv >= min_val else "#E74C3C"
                _sw   = int(_sv / max(min_val * 1.5, 1) * 100)
                _sw   = min(_sw, 100)
                _season_bars += (
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:3px;">'
                    f'<div style="color:#A8ABB8;font-size:0.68rem;min-width:110px;white-space:nowrap;">'
                    f'{str(_ps["season"])[:14]}</div>'
                    f'<div style="flex:1;background:#0E1117;border-radius:3px;height:6px;">'
                    f'<div style="background:{_sc};width:{_sw}%;height:6px;border-radius:3px;"></div></div>'
                    f'<div style="color:{_sc};font-size:0.72rem;font-weight:700;min-width:50px;'
                    f'text-align:right;">{_sv:,}</div>'
                    f'</div>'
                )

            st.markdown(f"""
            <div style="background:#1A1D27;border:1px solid #2A2D3A;border-radius:12px;
                        padding:16px 20px;margin-bottom:10px;">
              <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px;">
                <div>
                  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                    <span style="font-size:1.2rem;">{_medal}</span>
                    <span style="color:#E8E8E8;font-weight:800;font-size:1.05rem;">{_r['Player']}</span>
                    {_curr_badge}
                  </div>
                  <div style="margin-top:6px;display:flex;gap:20px;flex-wrap:wrap;">
                    <div>
                      <span style="color:#C8CBD8;font-size:0.68rem;text-transform:uppercase;">Seasons below</span>
                      <span style="color:#E74C3C;font-weight:800;font-size:1rem;margin-left:6px;">{_cnt}</span>
                      <span style="color:#A8ABB8;font-size:0.72rem;"> / {_total_seasons} total ({_pct_seasons}%)</span>
                    </div>
                    <div>
                      <span style="color:#C8CBD8;font-size:0.68rem;text-transform:uppercase;">Avg when below</span>
                      <span style="color:#F39C12;font-weight:700;font-size:0.9rem;margin-left:6px;">{_avg:,}</span>
                    </div>
                    <div>
                      <span style="color:#C8CBD8;font-size:0.68rem;text-transform:uppercase;">Worst season</span>
                      <span style="color:#C8CBD8;font-size:0.82rem;margin-left:6px;">{_worst_s}</span>
                    </div>
                  </div>
                </div>
                <div style="text-align:right;min-width:60px;">
                  <div style="color:#C8CBD8;font-size:0.62rem;text-transform:uppercase;">Offence rate</div>
                  <div style="color:#E74C3C;font-weight:800;font-size:1.3rem;">{_pct_seasons}%</div>
                </div>
              </div>
              <div style="background:#0E1117;border-radius:4px;height:4px;margin-bottom:12px;">
                <div style="background:#E74C3C;width:{_bar_w}%;height:4px;border-radius:4px;"></div>
              </div>
              <div style="border-top:1px solid #2A2D3A;padding-top:10px;">
                <div style="color:#C8CBD8;font-size:0.68rem;text-transform:uppercase;
                            letter-spacing:0.5px;margin-bottom:6px;">Season breakdown</div>
                {_season_bars}
              </div>
            </div>""", unsafe_allow_html=True)

    _min_gbg_col, _min_qi_col = st.columns(2)
    with _min_gbg_col:
        _minimums_section(gbg_df, "Fights",   1000, "#F39C12", "GBG Fights",   "GBG",  gbg_icon(20))
    with _min_qi_col:
        _minimums_section(qi_df,  "Progress", 3000, "#E67E22", "QI Progress",  "QI",   qi_icon(20))

    st.markdown("---")

    # ── Players below boost threshold ─────────────────────────────────────
    st.markdown('<div class="section-title">⚔️ Players Below Attack Threshold</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="color:#C8CBD8;font-size:0.78rem;margin-bottom:14px;">'
        'Members whose GBG attack boost is below <b style="color:#E74C3C;">500%</b> — '
        'may struggle to consistently hit fight minimums.</div>',
        unsafe_allow_html=True)

    if guild_stats_df.empty or "gbg_attack" not in guild_stats_df.columns:
        st.info("No boost data available. Upload guild_stats_final_named.csv to enable this section.")
    else:
        _thresh_atk = 500
        _bt = guild_stats_df[["player_name","gbg_attack","gbg_defense","critical_hit"]].copy()
        _bt["gbg_attack"]   = pd.to_numeric(_bt["gbg_attack"],   errors="coerce")
        _bt["gbg_defense"]  = pd.to_numeric(_bt["gbg_defense"],  errors="coerce")
        _bt["critical_hit"] = pd.to_numeric(_bt["critical_hit"], errors="coerce")
        _bt_below = _bt[_bt["gbg_attack"] < _thresh_atk].sort_values("gbg_attack").reset_index(drop=True)

        if _bt_below.empty:
            st.markdown(
                '<div style="background:#1A3A1A;border:1px solid #2A4A2A;border-radius:10px;'
                'padding:14px 18px;color:#2ECC71;font-weight:600;">'
                '✅ All members are above the 500% GBG attack threshold.</div>',
                unsafe_allow_html=True)
        else:
            _guild_avg_atk = float(_bt["gbg_attack"].dropna().mean())
            _bt_cols = st.columns(3)
            for _bti, (_, _btr) in enumerate(_bt_below.iterrows()):
                _atk_v  = float(_btr["gbg_attack"])  if pd.notna(_btr["gbg_attack"])  else 0
                _def_v  = float(_btr["gbg_defense"]) if pd.notna(_btr["gbg_defense"]) else 0
                _crit_v = float(_btr["critical_hit"])if pd.notna(_btr["critical_hit"])else 0
                _gap    = _guild_avg_atk - _atk_v
                _bar    = int(_atk_v / _thresh_atk * 100)
                _av     = get_avatar_html(_btr["player_name"], size=36)
                with _bt_cols[_bti % 3]:
                    st.markdown(
                        '<div style="background:#1A1D27;border:1px solid #3A2A2A;border-radius:10px;'
                        'padding:12px 14px;margin-bottom:8px;">'
                        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">'
                        + _av +
                        '<div style="flex:1;min-width:0;">'
                        f'<div style="color:#E8E8E8;font-weight:700;font-size:0.88rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_btr["player_name"]}</div>'
                        f'<div style="color:#E74C3C;font-size:0.75rem;font-weight:700;">{int(_atk_v):,}% GBG Atk</div>'
                        '</div></div>'
                        f'<div style="background:#0E1117;border-radius:4px;height:4px;margin-bottom:8px;">'
                        f'<div style="background:#E74C3C;width:{_bar}%;height:4px;border-radius:4px;"></div>'
                        f'</div>'
                        f'<div style="display:flex;gap:12px;flex-wrap:wrap;">'
                        f'<span style="color:#C8CBD8;font-size:0.72rem;">Gap to avg: <b style="color:#E74C3C;">−{int(_gap):,}%</b></span>'
                        + (f'<span style="color:#C8CBD8;font-size:0.72rem;">Def: <b style="color:#4A90D9;">{int(_def_v):,}%</b></span>' if _def_v else '')
                        + (f'<span style="color:#C8CBD8;font-size:0.72rem;">Crit: <b style="color:#FFD700;">{_crit_v:.1f}%</b></span>' if _crit_v else '')
                        + f'</div>'
                        '</div>',
                        unsafe_allow_html=True)

    _render_footer()
