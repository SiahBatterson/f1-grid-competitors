import os
import pandas as pd
from datetime import datetime
from core_utils import get_cached_race, is_race_cached, get_all_cached_drivers
from model import User, UserRaceResult, RosteredDrivers

CACHE_DIR = "/mnt/f1_cache"

def calculate_points_from_df(df):
    df['positions_gained'] = df['Quali'] - df['Race']
    df['positions_gained'] = df['positions_gained'].apply(lambda x: max(0, x))
    df['points_from_race'] = 21 - df['Race']
    df['points_from_gain'] = df['positions_gained'] * 2
    df['points_from_quali'] = (21 - df['Quali']) * 3
    df['Total Points'] = df['points_from_race'] + df['points_from_gain'] + df['points_from_quali']
    df['Q/R/+O'] = df.apply(
        lambda row: f"{row['points_from_quali']}/{row['points_from_race']}/{row['points_from_gain']}", axis=1
    )
    return df[['Driver', 'Quali', 'Race', '+Pos', 'Q/R/+O', 'Total Points']]

def apply_boosts(df, race_name, year):
    from app import db
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
            bonus = 0

            if boost_type == "qualifying":
                bonus = (21 - int(row["Quali"])) * 3
            elif boost_type == "race":
                bonus = (21 - int(row["Race"]))
            elif boost_type == "pass":
                bonus = int(row["+Pos"]) * 2

            total = base_points + bonus
            boosted = bool(boost_type)

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
    return "✅ Boosts applied and driver stats updated"

def process_latest_race_and_apply_boosts():
    from fastf1 import get_event_schedule
    schedule = get_event_schedule(datetime.now().year)
    past_races = schedule[schedule["EventDate"] < pd.Timestamp.now()]
    if past_races.empty:
        return False, "⚠️ No races found."

    latest = past_races.iloc[-1]
    year = latest["EventDate"].year
    gp_name = latest["EventName"]

    if not is_race_cached(year, gp_name):
        return False, f"❌ Race not cached: {year} - {gp_name}"

    df = get_cached_race(year, gp_name)
    if df.empty:
        return False, f"❌ Empty data for {gp_name}"

    apply_boosts(df, gp_name, year)
    return True, f"✅ Boosts applied for {gp_name}"

def process_single_race_and_apply_boosts(year, gp_name):
    from core_utils import fetch_and_cache_race
    if not is_race_cached(year, gp_name):
        fetch_and_cache_race(year, gp_name)

    df = get_cached_race(year, gp_name)
    if df.empty:
        return False, f"❌ Failed to calculate {gp_name}"

    apply_boosts(df, gp_name, year)
    return True, f"✅ Processed and applied boosts for {gp_name}"

def generate_driver_rating(driver):
    all_dfs = []
    for year in [2021, 2022, 2023, 2024, 2025]:
        from fastf1 import get_event_schedule
        try:
            schedule = schedule[schedule["EventDate"] < pd.Timestamp.now()]
            for _, row in schedule.iterrows():
                gp_name = row["EventName"]
                if is_race_cached(year, gp_name):
                    df = get_cached_race(year, gp_name)
                    if not df.empty and driver in df["Driver"].values:
                        row_df = df[df["Driver"] == driver].copy()
                        row_df["Year"] = year
                        row_df["Grand Prix"] = gp_name
                        all_dfs.append(row_df)
        except Exception as e:
            print(f"❌ Failed {year}: {e}")

    if not all_dfs:
        return pd.DataFrame(), None, None, None

    full_df = pd.concat(all_dfs).sort_values(["Year", "Grand Prix"], ascending=[False, False])
    last_3 = full_df.head(3)
    prev_3 = full_df.iloc[1:4]

    seasonal_avg = full_df["Total Points"].mean()
    last_3_avg = last_3["Total Points"].mean()
    last_race = full_df.iloc[0]["Total Points"]
    prev_last = full_df.iloc[1]["Total Points"] if len(full_df) > 1 else last_race

    weighted_total = round(seasonal_avg * 0.6 + last_3_avg * 0.2 + last_race * 0.2, 2)
    previous_weighted = round(seasonal_avg * 0.6 + prev_3["Total Points"].mean() * 0.2 + prev_last * 0.2, 2)
    fantasy_value = round(((seasonal_avg * 0.9) + (weighted_total * 0.1)) * 250000, 2)

    return full_df, weighted_total, fantasy_value, previous_weighted

def generate_all_driver_ratings():
    drivers = get_all_cached_drivers()
    for driver in drivers:
        try:
            generate_driver_rating(driver)
            print(f"✅ Generated: {driver}")
        except Exception as e:
            print(f"❌ Failed: {driver}: {e}")