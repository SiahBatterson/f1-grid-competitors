import fastf1
import pandas as pd
import os
import time

CACHE_DIR = "/mnt/f1_cache"
fastf1.Cache.enable_cache(CACHE_DIR)

def calculate_points(year, gp_name):
    cache_path = os.path.join(CACHE_DIR, f"{year} - {gp_name}.csv")
    if os.path.exists(cache_path):
        return pd.read_csv(cache_path)

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

        df.to_csv(cache_path, index=False)
        return df[['Driver', 'Quali', 'Race', '+Pos', 'Q/R/+O', 'Total Points']]
    except Exception as e:
        print(f"⚠️ Error: {e}")
        return pd.DataFrame()

def generate_driver_rating(driver_abbr):
    output_path = os.path.join(CACHE_DIR, f"Driver Rating - {driver_abbr}.csv")
    if os.path.exists(output_path):
        print(f"📂 Using cached driver rating for {driver_abbr}")
        return pd.read_csv(output_path)

    print(f"🧮 Generating fresh driver rating for {driver_abbr}")
    all_driver_races = []
    years = [2025, 2024, 2023, 2022, 2021]

    for year in years:
        try:
            schedule = fastf1.get_event_schedule(year)
            time.sleep(1)
            for _, row in schedule.iterrows():
                gp_name = row["EventName"]
                df = calculate_points(year, gp_name)
                if not df.empty and driver_abbr in df["Driver"].values:
                    row_df = df[df["Driver"] == driver_abbr].copy()
                    row_df["Year"] = year
                    row_df["Grand Prix"] = gp_name
                    all_driver_races.append(row_df)
        except Exception as e:
            print(f"⚠️ Skipping {year}: {e}")

    if not all_driver_races:
        return pd.DataFrame([{"Error": f"❌ No valid data for {driver_abbr}"}])

    full_df = pd.concat(all_driver_races, ignore_index=True)
    full_df = full_df.sort_values(by=["Year", "Grand Prix"], ascending=[False, False])

    last_3 = full_df.head(3)
    last_3_avg = pd.DataFrame([{
        "Driver": driver_abbr,
        "Scope": "Last 3 Races Avg",
        "Quali": round(last_3["Quali"].mean(), 2),
        "Race": round(last_3["Race"].mean(), 2),
        "+Pos": round(last_3["+Pos"].mean(), 2),
        "Q/R/+O": None,
        "Total Points": round(last_3["Total Points"].mean(), 2),
        "Year": None,
        "Grand Prix": None
    }])

    seasonal_avg = pd.DataFrame([{
        "Driver": driver_abbr,
        "Scope": "Seasonal Average",
        "Quali": round(full_df["Quali"].mean(), 2),
        "Race": round(full_df["Race"].mean(), 2),
        "+Pos": round(full_df["+Pos"].mean(), 2),
        "Q/R/+O": None,
        "Total Points": round(full_df["Total Points"].mean(), 2),
        "Year": None,
        "Grand Prix": None
    }])

    last_race = full_df.head(1)
    if not last_race.empty:
        weighted_total = round(
            (seasonal_avg["Total Points"].values[0] * 0.6) +
            (last_3_avg["Total Points"].values[0] * 0.2) +
            (last_race["Total Points"].values[0] * 0.2), 2
        )
        weighted_row = pd.DataFrame([{
            "Driver": driver_abbr,
            "Weighted Avg": weighted_total
        }])

        weighted_path = os.path.join(CACHE_DIR, "Weighted Driver Averages.csv")
        if os.path.exists(weighted_path):
            existing = pd.read_csv(weighted_path)
            existing = existing[existing["Driver"] != driver_abbr]
            updated = pd.concat([existing, weighted_row], ignore_index=True)
        else:
            updated = weighted_row
        updated = updated.sort_values(by="Weighted Avg", ascending=False)
        updated.to_csv(weighted_path, index=False)

    full_out = pd.concat([seasonal_avg, last_3, last_3_avg], ignore_index=True)
    full_out.to_csv(output_path, index=False)

    # Compute fantasy value
    fantasy_value = None
    if not last_race.empty:
        hype = weighted_total
        avg = seasonal_avg["Total Points"].values[0]
        fantasy_value = round(((avg * 0.9) + (hype * 0.1)) * 250000, 2)

    return full_out, weighted_total if not last_race.empty else None, fantasy_value

def get_all_cached_drivers():
    drivers = set()

    for year in [2025, 2024, 2023, 2022, 2021]:
        schedule_path = os.path.join(CACHE_DIR, f"averages_{year}.csv")
        if os.path.exists(schedule_path):
            df = pd.read_csv(schedule_path)
            drivers.update(df["Driver"].dropna().unique())

    for fname in os.listdir(CACHE_DIR):
        if fname.startswith("Driver Rating - ") and fname.endswith(".csv"):
            driver = fname.replace("Driver Rating - ", "").replace(".csv", "").strip()
            if driver:
                drivers.add(driver)

    if not drivers:
        # Fallback list of known F1 abbreviations (as of 2023–2025)
        drivers.update([
            "VER", "PER", "HAM", "RUS", "NOR", "LEC", "SAI", "ALO", "OCO",
            "GAS", "PIA", "BOT", "ZHO", "MAG", "HUL", "TSU", "ALB", "SAR"
        ])

    return sorted(drivers)


def generate_all_driver_ratings():
    drivers = get_all_cached_drivers()
    print(f"🔁 Generating full driver rating files for {len(drivers)} drivers...")

    weighted_path = os.path.join(CACHE_DIR, "Weighted Driver Averages.csv")
    if os.path.exists(weighted_path):
        os.remove(weighted_path)

    for driver in drivers:
        try:
            generate_driver_rating(driver, force=True)
            print(f"✅ Cached {driver}")
        except Exception as e:
            print(f"❌ Failed to generate for {driver}: {e}")

    if os.path.exists(weighted_path):
        df = pd.read_csv(weighted_path)
        df = df.sort_values(by="Weighted Avg", ascending=False)
        df.to_csv(weighted_path, index=False)
        print(f"✅ Final weighted driver list saved to: {weighted_path}")
    else:
        print("⚠️ No weighted data generated.")


