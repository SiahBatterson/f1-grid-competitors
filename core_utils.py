import os
import time
import pandas as pd
import fastf1
from datetime import datetime

CACHE_DIR = "/mnt/f1_cache"
fastf1.Cache.enable_cache(CACHE_DIR)

def is_race_cached(year, gp_name):
    return os.path.exists(os.path.join(CACHE_DIR, f"{year} - {gp_name}.csv"))

def get_cached_race(year, gp_name):
    path = os.path.join(CACHE_DIR, f"{year} - {gp_name}.csv")
    if os.path.exists(path):
        try:
            return pd.read_csv(path)
        except Exception as e:
            print(f"❌ Failed to read cache: {e}")
    return pd.DataFrame()

def get_last_processed_race():
    latest_file = None
    latest_time = 0

    for file in os.listdir(CACHE_DIR):
        if file.endswith(".csv") and " - " in file and not file.startswith("averages") and not file.startswith("Driver Rating"):
            path = os.path.join(CACHE_DIR, file)
            modified = os.path.getmtime(path)
            if modified > latest_time:
                latest_time = modified
                latest_file = file

    if latest_file:
        return latest_file.replace(".csv", "")
    return None


def fetch_and_cache_race(year, gp_name):
    try:
        event = fastf1.get_event(year, gp_name)
        quali = event.get_session('Qualifying')
        race = event.get_session('Race')
        quali.load(telemetry=False, weather=False, laps=False, messages=False)
        time.sleep(1)
        race.load(telemetry=False, weather=False, laps=False, messages=False)
        time.sleep(1)

        q_results = quali.results
        r_results = race.results
        if q_results is None or r_results is None:
            return False

        df = pd.merge(
            q_results[['Abbreviation', 'Position']].rename(columns={'Position': 'position_quali'}),
            r_results[['Abbreviation', 'Position']].rename(columns={'Position': 'position_race'}),
            on='Abbreviation'
        )

        df['positions_gained'] = df['position_quali'] - df['position_race']
        df['positions_gained'] = df['positions_gained'].apply(lambda x: max(0, x))
        df['points_from_race'] = 21 - df['position_race']
        df['points_from_gain'] = df['positions_gained'] * 2
        df['points_from_quali'] = (21 - df['position_quali']) * 3
        df['total_points'] = df['points_from_race'] + df['points_from_gain'] + df['points_from_quali']

        df = df.rename(columns={
            'Abbreviation': 'Driver',
            'position_quali': 'Quali',
            'position_race': 'Race',
            'positions_gained': '+Pos',
            'total_points': 'Total Points'
        })

        df['Q/R/+O'] = df.apply(
            lambda row: f"{row['points_from_quali']}/{row['points_from_race']}/{row['points_from_gain']}", axis=1
        )

        df.to_csv(os.path.join(CACHE_DIR, f"{year} - {gp_name}.csv"), index=False)
        print(f"✅ Fetched and cached: {year} - {gp_name}")
        return True
    except Exception as e:
        print(f"❌ Error caching {year} - {gp_name}: {e}")
        return False

def preload_race_data_until(year_limit=2025, stop_gp="Miami Grand Prix"):
    print(f"🔁 Preloading races up to {year_limit} - {stop_gp}")
    for year in range(2021, year_limit + 1):
        try:
            schedule = fastf1.get_event_schedule(year)
            if year == year_limit:
                if stop_gp in schedule["EventName"].values:
                    stop_index = schedule[schedule["EventName"] == stop_gp].index[0]
                    schedule = schedule.loc[:stop_index - 1]
            else:
                schedule = schedule[schedule["EventDate"] < pd.Timestamp.now()]
        except Exception as e:
            print(f"⚠️ Failed to get schedule for {year}: {e}")
            continue

        for _, row in schedule.iterrows():
            gp_name = row["EventName"]
            if not is_race_cached(year, gp_name):
                fetch_and_cache_race(year, gp_name)
    print("✅ Preload complete.")


def get_all_cached_drivers():
    latest_file = None
    latest_time = 0

    for file in os.listdir(CACHE_DIR):
        if file.endswith(".csv") and " - " in file and not file.startswith("averages") and not file.startswith("Driver Rating"):
            path = os.path.join(CACHE_DIR, file)
            modified = os.path.getmtime(path)
            if modified > latest_time:
                latest_time = modified
                latest_file = path

    if not latest_file:
        print("⚠️ No valid race files found.")
        return []

    try:
        df = pd.read_csv(latest_file)
        if "Driver" in df.columns:
            return sorted(df["Driver"].dropna().unique())
        else:
            print(f"⚠️ 'Driver' column missing in {latest_file}")
            return []
    except Exception as e:
        print(f"❌ Failed to load latest race file: {e}")
        return []

def clean_gp_name(gp_name):
    if gp_name.endswith("Grand Prix Grand Prix"):
        return gp_name.replace("Grand Prix Grand Prix", "Grand Prix")
    elif gp_name.count("Grand Prix") > 1:
        return gp_name.replace(" Grand Prix", "", gp_name.count("Grand Prix") - 1)
    return gp_name


def delete_duplicate_grand_prix_files():
    seen = {}
    to_delete = []
    renamed = []

    for file in os.listdir(CACHE_DIR):
        if not file.endswith(".csv") or " - " not in file:
            continue

        try:
            year, raw_gp = file.replace(".csv", "").split(" - ", 1)
            clean_name = clean_gp_name(raw_gp)
            clean_filename = f"{year} - {clean_name}.csv"

            original_path = os.path.join(CACHE_DIR, file)
            clean_path = os.path.join(CACHE_DIR, clean_filename)

            # Case 1: Needs renaming due to duplicate 'Grand Prix'
            if raw_gp != clean_name and not os.path.exists(clean_path):
                os.rename(original_path, clean_path)
                renamed.append((file, clean_filename))
                seen[clean_filename] = clean_path

            # Case 2: Duplicate — delete
            elif clean_filename in seen or os.path.exists(clean_path):
                to_delete.append(original_path)

            else:
                seen[clean_filename] = original_path

        except Exception as e:
            print(f"❌ Error processing {file}: {e}")

    for path in to_delete:
        try:
            os.remove(path)
            print(f"🗑️ Deleted duplicate: {os.path.basename(path)}")
        except Exception as e:
            print(f"❌ Failed to delete {path}: {e}")

    for old, new in renamed:
        print(f"🔁 Renamed: {old} ➡️ {new}")

    print(f"\n✅ Cleanup complete. {len(renamed)} renamed, {len(to_delete)} deleted.")

