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
