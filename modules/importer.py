"""
importer.py - CSV-based data loader for Guild Tracker
Reads CSV files directly from the data/ folders in the repo.
No master.json needed — just drop CSVs into the right folder and push to GitHub.

Folder structure:
  data/
    gbg/        ← one CSV per GBG season, filename = season name
    qi/         ← one CSV per QI season,  filename = season name
    members/    ← one CSV per member snapshot, filename = snapshot name
"""

import pandas as pd
from pathlib import Path

# ── Data directories ───────────────────────────────────────────────────────
DATA_DIR         = Path("data")
GBG_DIR          = DATA_DIR / "gbg"
QI_DIR           = DATA_DIR / "qi"
MEMBERS_DIR      = DATA_DIR / "members"
GUILD_STATS_FILE = DATA_DIR / "members_stats" / "guild_stats_final_named.csv"

# ── Required columns ───────────────────────────────────────────────────────
GBG_REQUIRED_COLS    = {"Player_ID", "Player", "Negotiations", "Fights", "Total"}
QI_REQUIRED_COLS     = {"Player_ID", "Player", "Actions", "Progress"}
MEMBER_REQUIRED_COLS = {"member_id", "member", "points", "eraName", "guildgoods", "won_battles"}


# ── Validation ─────────────────────────────────────────────────────────────

def validate_gbg(df: pd.DataFrame) -> tuple[bool, str]:
    missing = GBG_REQUIRED_COLS - set(df.columns)
    if missing:
        return False, f"Missing columns: {missing}"
    return True, "OK"


def validate_qi(df: pd.DataFrame) -> tuple[bool, str]:
    missing = QI_REQUIRED_COLS - set(df.columns)
    if missing:
        return False, f"Missing columns: {missing}"
    return True, "OK"


def validate_members(df: pd.DataFrame) -> tuple[bool, str]:
    missing = MEMBER_REQUIRED_COLS - set(df.columns)
    if missing:
        return False, f"Missing columns: {missing}"
    return True, "OK"


# ── Helpers ────────────────────────────────────────────────────────────────

def _season_from_filename(path: Path) -> str:
    """Convert filename back to season name (underscores → spaces)."""
    return path.stem.replace("_", " ")


def _filename_from_season(season: str) -> str:
    """Convert season name to safe filename (spaces → underscores)."""
    return season.strip().replace(" ", "_") + ".csv"


def _ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def _load_csv_folder(folder: Path, id_col: str = "Player_ID") -> pd.DataFrame:
    """Load all CSVs in a folder, adding a 'season' column from the filename."""
    if not folder.exists():
        return pd.DataFrame()

    frames = []

    for csv_file in sorted(folder.glob("*.csv")):
        if csv_file.name.startswith("."):
            continue

        try:
            raw = csv_file.read_text(encoding="utf-8-sig")

            # Detect separator
            sep = ";" if raw.count(";") > raw.count(",") else ","

            df = pd.read_csv(csv_file, sep=sep, encoding="utf-8-sig")

            # Clean column names aggressively
            df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

            # If the file still loaded as a single merged column, try the other separator once
            if len(df.columns) == 1:
                alt_sep = "," if sep == ";" else ";"
                df = pd.read_csv(csv_file, sep=alt_sep, encoding="utf-8-sig")
                df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

            # Normalise common alias columns so downstream code can rely on Player_ID / Player
            col_map = {}
            if "member_id" in df.columns and "Player_ID" not in df.columns:
                col_map["member_id"] = "Player_ID"
            if "member" in df.columns and "Player" not in df.columns:
                col_map["member"] = "Player"
            if col_map:
                df = df.rename(columns=col_map)

            # Clean string values in key identity columns if present
            for col in ["Player_ID", "Player", "member_id", "member"]:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.replace("\ufeff", "", regex=False).str.strip()

            df["season"] = _season_from_filename(csv_file)
            frames.append(df)

        except Exception as e:
            print(f"Failed to load {csv_file.name}: {e}")
            continue

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # Final column cleanup after concat
    combined.columns = [str(c).replace("\ufeff", "").strip() for c in combined.columns]

    # Final alias normalization after concat
    col_map = {}
    if "member_id" in combined.columns and "Player_ID" not in combined.columns:
        col_map["member_id"] = "Player_ID"
    if "member" in combined.columns and "Player" not in combined.columns:
        col_map["member"] = "Player"
    if col_map:
        combined = combined.rename(columns=col_map)

    if id_col in combined.columns:
        combined[id_col] = combined[id_col].astype(str).str.replace("\ufeff", "", regex=False).str.strip()

    return combined


# ── Save CSV (used by the in-app import form) ──────────────────────────────

def save_gbg_csv(df: pd.DataFrame, season: str) -> tuple[bool, str]:
    ok, msg = validate_gbg(df)
    if not ok:
        return False, msg
    _ensure_dir(GBG_DIR)
    df = df.copy()
    df["Player_ID"] = df["Player_ID"].astype(str)
    for col in ["Negotiations", "Fights", "Total"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    path = GBG_DIR / _filename_from_season(season)
    df.to_csv(path, index=False)
    return True, f"Saved {len(df)} GBG records → data/gbg/{path.name}"


def save_qi_csv(df: pd.DataFrame, season: str) -> tuple[bool, str]:
    ok, msg = validate_qi(df)
    if not ok:
        return False, msg
    _ensure_dir(QI_DIR)
    df = df.copy()
    df["Player_ID"] = df["Player_ID"].astype(str)
    for col in ["Actions", "Progress"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    path = QI_DIR / _filename_from_season(season)
    df.to_csv(path, index=False)
    return True, f"Saved {len(df)} QI records → data/qi/{path.name}"


def save_members_csv(df: pd.DataFrame, snapshot: str) -> tuple[bool, str]:
    ok, msg = validate_members(df)
    if not ok:
        return False, msg
    _ensure_dir(MEMBERS_DIR)
    df = df.copy()
    # Normalise column names
    col_map = {}
    if "member_id" in df.columns: col_map["member_id"] = "Player_ID"
    if "member"    in df.columns: col_map["member"]    = "Player"
    df = df.rename(columns=col_map)
    df["Player_ID"] = df["Player_ID"].astype(str)
    for col in ["points", "guildgoods", "won_battles"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    if "rank" in df.columns:
        df["rank"] = pd.to_numeric(df["rank"], errors="coerce").fillna(0).astype(int)
    # Preserve extra FoE Helper columns if present
    for col in ["activity_warnings", "gex_participation", "gbg_participation", "messages"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    path = MEMBERS_DIR / _filename_from_season(snapshot)
    df.to_csv(path, index=False)
    return True, f"Saved {len(df)} member records → data/members/{path.name}"


# ── Read ───────────────────────────────────────────────────────────────────

def get_gbg_df() -> pd.DataFrame:
    df = _load_csv_folder(GBG_DIR)
    if df.empty:
        return pd.DataFrame(columns=["Player_ID", "Player", "Negotiations", "Fights", "Total", "season"])
    for col in ["Negotiations", "Fights", "Total"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["Player_ID"] = df["Player_ID"].astype(str)
    return df


def get_qi_df() -> pd.DataFrame:
    df = _load_csv_folder(QI_DIR)
    if df.empty:
        return pd.DataFrame(columns=["Player_ID", "Player", "Actions", "Progress", "season"])
    for col in ["Actions", "Progress"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["Player_ID"] = df["Player_ID"].astype(str)
    return df


def get_members_df() -> pd.DataFrame:
    df = _load_csv_folder(MEMBERS_DIR)
    if df.empty:
        return pd.DataFrame(columns=["Player_ID", "Player", "points", "eraName", "guildgoods", "won_battles", "snapshot"])
    # Normalise column names if raw CSV used member_id/member
    col_map = {}
    if "member_id" in df.columns and "Player_ID" not in df.columns:
        col_map["member_id"] = "Player_ID"
    if "member" in df.columns and "Player" not in df.columns:
        col_map["member"] = "Player"
    if col_map:
        df = df.rename(columns=col_map)
    # season column becomes snapshot for members
    if "season" in df.columns and "snapshot" not in df.columns:
        df = df.rename(columns={"season": "snapshot"})
    for col in ["points", "guildgoods", "won_battles"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    if "rank" in df.columns:
        df["rank"] = pd.to_numeric(df["rank"], errors="coerce").fillna(0).astype(int)
    df["Player_ID"] = df["Player_ID"].astype(str)
    return df


def get_member_snapshots() -> list[str]:
    from modules.comparisons import sort_seasons
    df = get_members_df()
    if df.empty or "snapshot" not in df.columns:
        return []
    return sort_seasons(df["snapshot"].unique().tolist(), descending=True)


def get_all_seasons() -> dict:
    from modules.comparisons import sort_seasons
    gbg_df  = get_gbg_df()
    qi_df   = get_qi_df()
    mem_df  = get_members_df()
    gbg_seasons = sort_seasons(gbg_df["season"].unique().tolist())          if not gbg_df.empty and "season"   in gbg_df.columns  else []
    qi_seasons  = sort_seasons(qi_df["season"].unique().tolist())           if not qi_df.empty  and "season"   in qi_df.columns   else []
    mem_snaps   = sort_seasons(mem_df["snapshot"].unique().tolist(), descending=True) if not mem_df.empty and "snapshot" in mem_df.columns else []
    return {"gbg": gbg_seasons, "qi": qi_seasons, "members": mem_snaps}


# ── Delete (removes the CSV file) ──────────────────────────────────────────

def delete_season(section: str, season: str) -> str:
    folder_map = {"gbg": GBG_DIR, "qi": QI_DIR, "members": MEMBERS_DIR}
    folder = folder_map.get(section.lower())
    if not folder:
        return f"Unknown section: {section}"
    path = folder / _filename_from_season(season)
    if path.exists():
        path.unlink()
        return f"Deleted {path.name}"
    return f"File not found: {path.name}"


# ── Guild Stats (scraped boosts/production) ────────────────────────────────

_GUILD_STATS_DROP = ["attempt", "failed_reason", "popup_name_debug"]


def get_guild_stats_df() -> pd.DataFrame:
    """Load guild_stats_final_named.csv, drop ignored columns, drop missing rows."""
    if not GUILD_STATS_FILE.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(GUILD_STATS_FILE, encoding="utf-8-sig")
        df.columns = [str(c).strip() for c in df.columns]
        df = df[df["status"] != "missing"].copy()
        df = df.drop(columns=[c for c in _GUILD_STATS_DROP if c in df.columns])
        df["player_name"] = df["player_name"].astype(str).str.strip()
        return df
    except Exception as e:
        print(f"Failed to load guild stats: {e}")
        return pd.DataFrame()


# ── Legacy aliases so nothing else breaks ─────────────────────────────────
import_gbg     = save_gbg_csv
import_qi      = save_qi_csv
import_members = save_members_csv
