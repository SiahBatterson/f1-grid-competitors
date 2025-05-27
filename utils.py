import fastf1
import pandas as pd
import os
import time

CACHE_DIR = "/mnt/f1_cache"
fastf1.Cache.enable_cache(CACHE_DIR)

def calculate_points(year, gp_name):
    if (year > 2025) or (year == 2025 and gp_name.lower() > "miami"):
        print(f"⛔ Skipping {year} - {gp_name}: after 2025 Miami")
        return pd.DataFrame()
    cache_path = os.path.join(CACHE_DIR, f"{year} - {gp_name}.csv")
    if os.path.exists(cache_path):
        cached_df = pd.read_csv(cache_path)
        # Check for minimal validity (non-empty + expected columns)
        required_cols = {'Driver', 'Quali', 'Race', '+Pos', 'Q/R/+O', 'Total Points'}
        if not cached_df.empty and required_cols.issubset(set(cached_df.columns)):
            last_race_path = os.path.join(CACHE_DIR, "LastProcessedRace.txt")
            with open(last_race_path, "w") as f:
                f.write(f"{year} - {gp_name}")
            return cached_df
        else:
            print(f"⚠️ Cache for {year} - {gp_name} is invalid. Refetching...")


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
        last_race_path = os.path.join(CACHE_DIR, "LastProcessedRace.txt")
        with open(last_race_path, "w") as f:
            f.write(f"{year} - {gp_name}")
        return df[['Driver', 'Quali', 'Race', '+Pos', 'Q/R/+O', 'Total Points']]
    except Exception as e:
        print(f"⚠️ Error: {e}")
        # Update the last processed race file

        return pd.DataFrame()

def generate_driver_rating(driver_abbr, force=False):
    output_path = os.path.join(CACHE_DIR, f"Driver Rating - {driver_abbr}.csv")

    if os.path.exists(output_path) and not force:
        print(f"📂 Using cached driver rating for {driver_abbr}")
        df = pd.read_csv(output_path)

        try:
            avg = df[df["Scope"] == "Seasonal Average"]["Total Points"].values[0]
            last3 = df[df["Scope"] == "Last 3 Races Avg"]["Total Points"].values[0]
            prev3 = df[df["Scope"] == "Prev 3 Races Avg"]["Total Points"].values[0]
            last_race = df[df["Scope"].isna()]["Total Points"].iloc[0]
            prev_race = df[df["Scope"].isna()]["Total Points"].iloc[1] if len(df[df["Scope"].isna()]) > 1 else last_race

            weighted_total = round(avg * 0.5 + last3 * 0.2 + last_race * 0.3, 2)
            previous_weighted = round(avg * 0.5 + prev3 * 0.2 + prev_race * 0.3, 2)
            fantasy_value = round(((avg * 0.7) + (weighted_total * 0.3)) * 250000, 2)
        except Exception as e:
            print(f"⚠️ Failed to compute value from cached file: {e}")
            weighted_total = fantasy_value = previous_weighted = None

        return df, weighted_total, fantasy_value, previous_weighted


    print(f"🧲 Generating fresh driver rating for {driver_abbr}")
    all_driver_races = []
    years = [2025, 2024, 2023, 2022, 2021]

    for year in years:
        try:
            schedule = fastf1.get_event_schedule(year)
            schedule = schedule[schedule['EventDate'] < pd.Timestamp.now()]  # Only past races
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
        return pd.DataFrame([{"Error": f"❌ No valid data for {driver_abbr}"}]), None, None, None

    full_df = pd.concat(all_driver_races, ignore_index=True)
    full_df = full_df.sort_values(by=["Year", "Grand Prix"], ascending=[False, False])

    last_3 = full_df.head(3)
    prev_3 = full_df.iloc[1:4]

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

    prev_3_avg = pd.DataFrame([{ 
        "Driver": driver_abbr,
        "Scope": "Prev 3 Races Avg",
        "Quali": round(prev_3["Quali"].mean(), 2),
        "Race": round(prev_3["Race"].mean(), 2),
        "+Pos": round(prev_3["+Pos"].mean(), 2),
        "Q/R/+O": None,
        "Total Points": round(prev_3["Total Points"].mean(), 2),
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

    weighted_total = round(
        seasonal_avg["Total Points"].values[0] * 0.6 +
        last_3_avg["Total Points"].values[0] * 0.2 +
        last_race["Total Points"].values[0] * 0.2,
        2
    )

    previous_weighted = round(
        seasonal_avg["Total Points"].values[0] * 0.6 +
        prev_3_avg["Total Points"].values[0] * 0.2 +
        full_df.iloc[1:2]["Total Points"].values[0] * 0.2,
        2
    ) if len(full_df) > 3 else weighted_total

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

    full_out = pd.concat([seasonal_avg, last_3, last_3_avg, prev_3_avg], ignore_index=True)
    full_out.to_csv(output_path, index=False)

    avg = seasonal_avg["Total Points"].values[0]
    fantasy_value = round(((avg * 0.9) + (weighted_total * 0.1)) * 250000, 2)
    print(f"\n🔢 CALCULATION DEBUG for {driver_abbr}:")
    print(f"  Seasonal Avg: {seasonal_avg['Total Points'].values[0]}")
    print(f"  Last 3 Avg  : {last_3_avg['Total Points'].values[0]}")
    print(f"  Prev 3 Avg  : {prev_3_avg['Total Points'].values[0]}")
    print(f"  Last Race   : {full_df.iloc[0]['Total Points']}")
    print(f"  Prev Last   : {full_df.iloc[1]['Total Points']}")
    print(f"\n🎯 Weighted: {weighted_total}")
    print(f"🎯 Previous: {previous_weighted}")
    print(f"🎯 Fantasy : {fantasy_value}")
    return full_out, weighted_total, fantasy_value, previous_weighted

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
        drivers.update([
            "VER", "PER", "HAM", "RUS", "NOR", "LEC", "SAI", "ALO", "OCO",
            "GAS", "PIA", "BOT", "ZHO", "MAG", "HUL", "TSU", "ALB", "SAR"
        ])

    return sorted(drivers)

from model import User, UserRaceResult, RosteredDrivers

def apply_boosts(df, race_name, year):
    users = User.query.all()
    for user in users:
        user_drivers = user.drivers.split(",")
        user_boosts = {b.split(":")[0]: b.split(":")[1] for b in user.boosts.split(";") if ":" in b}

        for driver in user_drivers:
            row = df[df["Driver"] == driver]
            if row.empty:
                continue

            base_points = float(row["Total Points"])
            boost_type = user_boosts.get(driver)
            boost_multiplier = 1.0

            if boost_type == "qualifying":
                base = (21 - int(row["Quali"])) * 3
                bonus = base
            elif boost_type == "race":
                base = (21 - int(row["Race"]))
                bonus = base
            elif boost_type == "pass":
                base = int(row["+Pos"]) * 2
                bonus = base
            else:
                bonus = 0

            total = base_points + bonus
            boosted = bool(boost_type)

            # Record result
            result = UserRaceResult(
                user_id=user.id,
                driver=driver,
                year=year,
                race=race_name,
                base_points=base_points,
                category=boost_type or "",
                boosted=boosted,
                total_points=total,
            )
            db.session.add(result)

            # Update UserDriver stats
            user_driver = RosteredDrivers.query.filter_by(user_id=user.id, driver=driver).first()
            if user_driver:
                user_driver.races_owned += 1
                user_driver.boost_points += bonus
                try:
                    _, _, current_value, _ = generate_driver_rating(driver)
                    user_driver.current_value = current_value
                except Exception as e:
                    print(f"⚠️ Failed to update value for {driver}: {e}")

        user.boosts = ""
    db.session.commit()
    return "Boosts applied and driver stats updated"




def get_last_processed_race():
    path = os.path.join(CACHE_DIR, "LastProcessedRace.txt")
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return f.read().strip()
        except Exception:
            return "N/A"
    return "N/A"

    

def process_latest_race_and_apply_boosts():
    from datetime import datetime
    from model import User, UserRaceResult

    current_year = datetime.now().year
    schedule = fastf1.get_event_schedule(current_year)
    past_races = schedule[schedule['EventDate'] < pd.Timestamp.now()]

    if past_races.empty:
        return False, "⚠️ No races have occurred yet this season."

    latest_race = past_races.iloc[-1]
    race_name = latest_race["EventName"]
    print(f"🔄 Processing latest race: {race_name}")

    df = calculate_points(current_year, race_name)
    if df.empty:
        return False, f"⚠️ Failed to calculate points for {race_name}."

    for driver in df["Driver"].unique():
        try:
            generate_driver_rating(driver, force=True)
            print(f"✅ Updated rating for {driver}")
        except Exception as e:
            print(f"❌ Failed to update {driver}: {e}")

    apply_boosts(df, race_name, current_year)
    return True, f"✅ Latest race ({race_name}) processed and boosts applied."


def calculate_single_race(year, gp_name):
    """
    Calculate fantasy points for a specific race without updating global last-race tracking.
    """
    cache_path = os.path.join(CACHE_DIR, f"{year} - {gp_name}.csv")

    # Use valid cached data if available
    if os.path.exists(cache_path):
        cached_df = pd.read_csv(cache_path)
        required_cols = {'Driver', 'Quali', 'Race', '+Pos', 'Q/R/+O', 'Total Points'}
        if not cached_df.empty and required_cols.issubset(cached_df.columns):
            return cached_df

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
        last_race_path = os.path.join(CACHE_DIR, f"{year} - LastProcessedRace.txt")
        with open(last_race_path, "w") as f:
            f.write(f"{year} - {gp_name}")
        return df[['Driver', 'Quali', 'Race', '+Pos', 'Q/R/+O', 'Total Points']]

    except Exception as e:
        print(f"❌ Error loading race data: {e}")
        return pd.DataFrame()

def generate_all_driver_ratings():
    from datetime import datetime

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
