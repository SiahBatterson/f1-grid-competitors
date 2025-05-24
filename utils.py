import fastf1
import pandas as pd
import os
import time

CACHE_DIR = "/mnt/f1_cache"
fastf1.Cache.enable_cache(CACHE_DIR)

def calculate_points(year, gp_name):
    try:
        event = fastf1.get_event(year, gp_name)
        quali = event.get_session('Qualifying')
        race = event.get_session('Race')
        quali.load(telemetry=False, weather=False, laps=False)
        race.load(telemetry=False, weather=False, laps=False)

        q_results = quali.results
        r_results = race.results

        if q_results is None or r_results is None:
            return pd.DataFrame()

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
        return df[['Driver', 'Quali', 'Race', '+Pos', 'Q/R/+O', 'Total Points']]
    except Exception as e:
        print(f"⚠️ Error: {e}")
        return pd.DataFrame()

def generate_driver_rating(driver_abbr):
    recent_races = []
    years = [2025, 2024, 2023, 2022, 2021]

    for year in years:
        try:
            schedule = fastf1.get_event_schedule(year)
            for _, row in reversed(schedule.iterrows()):
                gp_name = row["EventName"]
                df = calculate_points(year, gp_name)
                if not df.empty and driver_abbr in df["Driver"].values:
                    df = df[df["Driver"] == driver_abbr]
                    df["Season"] = year
                    df["Grand Prix"] = gp_name
                    recent_races.append(df)
                    if len(recent_races) == 3:
                        break
            if len(recent_races) == 3:
                break
        except Exception as e:
            print(f"⚠️ Skipping {year}: {e}")

    if not recent_races:
        return f"❌ No valid data for {driver_abbr}"

    combined = pd.concat(recent_races)
    recent_avg = combined["Total Points"].mean()
    last_race_points = combined.iloc[0]["Total Points"]

    # Get seasonal average from available averages
    seasonal_avg = None
    for year in years:
        avg_path = os.path.join(CACHE_DIR, f"averages_{year}.csv")
        if os.path.exists(avg_path):
            avg_df = pd.read_csv(avg_path)
            match = avg_df[avg_df["Driver"] == driver_abbr]
            if not match.empty:
                seasonal_avg = match["Total Points"].values[0]
                break

    summary = {
        "Driver": driver_abbr,
        "Seasonal Average": round(seasonal_avg, 2) if seasonal_avg else "N/A",
        "Last 3 Race Avg": round(recent_avg, 2),
        "Last Race Points": round(last_race_points, 2)
    }

    for _, row in combined.iterrows():
        summary[f"{row['Season']} - {row['Grand Prix']}"] = row["Total Points"]

    output_path = os.path.join(CACHE_DIR, f"Driver Rating - {driver_abbr}.csv")
    pd.DataFrame([summary]).to_csv(output_path, index=False)
    return pd.DataFrame([summary])

def get_all_cached_drivers():
    drivers = set()
    for year in [2025, 2024, 2023, 2022, 2021]:
        path = os.path.join(CACHE_DIR, f"averages_{year}.csv")
        if os.path.exists(path):
            df = pd.read_csv(path)
            drivers.update(df["Driver"].dropna().unique())
    return sorted(drivers)
