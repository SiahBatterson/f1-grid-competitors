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

def clean_gp_name(gp_name):
    if gp_name.endswith("Grand Prix Grand Prix"):
        return gp_name.replace("Grand Prix Grand Prix", "Grand Prix")
    elif gp_name.count("Grand Prix") > 1:
        return gp_name.replace(" Grand Prix", "", gp_name.count("Grand Prix") - 1)
    return gp_name


def apply_boosts(df, race_name, year):
    from app import db
    users = User.query.all()
    
    for user in users:
        user_drivers = user.drivers.split(",")
        user_boosts = {
            b.split(":")[0]: b.split(":")[1]
            for b in user.boosts.split(";") if ":" in b
        }

        for driver in user_drivers:
            row = df[df["Driver"] == driver]
            if row.empty:
                continue

            # Skip if driver is not rostered for this user
            user_driver = RosteredDrivers.query.filter_by(user_id=user.id, driver=driver).first()
            if not user_driver:
                print(f"⚠️ Skipping boost for {driver} - not rostered by user {user.username}")
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

            # Save the race result
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

            # Update RosteredDrivers DB entry
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
    from core_utils import get_most_recent_race_by_event_date
    from fastf1 import get_event_schedule

    last_race_info = get_most_recent_race_by_event_date()
    if not last_race_info:
        return False, "⚠️ No races with EventDate found in cache."

    year = int(last_race_info["year"])
    gp_name = clean_gp_name(last_race_info["gp_name"])

    if not is_race_cached(year, gp_name):
        return False, f"❌ Race not cached: {year} - {gp_name}"

    df = get_cached_race(year, gp_name)
    if df.empty:
        return False, f"❌ Empty data for {gp_name}"

    apply_boosts(df, gp_name, year)

    # Regenerate driver ratings and leaderboard to reflect boosts and race impact
    generate_all_driver_ratings()

    return True, f"✅ Boosts applied and stats updated for {gp_name}"


def process_single_race_and_apply_boosts(driver_code, year, gp_name):
    df = get_cached_race(year, gp_name)
    if df.empty or driver_code not in df["Driver"].values:
        raise ValueError("Driver or race not found in cache")

    points = df[df["Driver"] == driver_code]["Total Points"].values[0]

    # Apply boosts
    rostered = RosteredDrivers.query.filter_by(driver=driver_code).all()
    for r in rostered:
        user = User.query.get(r.user_id)
        if user and user.boosts:
            boost_type = user.boosts.get("type")
            if boost_type and not user.boosts.get("used", False):
                if should_boost_apply(boost_type, gp_name):  # implement this
                    r.boost_points += points  # simple example
                    user.boosts["used"] = True
    db.session.commit()

    return points


def calculate_fantasy_value(career_avg, season_avg, last3_avg):
    if career_avg is None or season_avg is None or last3_avg is None:
        return None
    return round((career_avg * 0.05 + season_avg * 0.85 + last3_avg * 0.1) * 250000)

def generate_driver_rating(driver):
    print(f"\n🔍 Generating driver rating for: {driver}")
    all_dfs = []
    for year in range(2021, 2026):
        from fastf1 import get_event_schedule
        try:
            schedule = get_event_schedule(year)
            schedule = schedule[schedule["EventDate"] < pd.Timestamp.now()]
            for _, row in schedule.iterrows():
                gp_name = clean_gp_name(row["EventName"])
                if is_race_cached(year, gp_name):
                    df = get_cached_race(year, gp_name)
                    if not df.empty and driver in df["Driver"].values:
                        row_df = df[df["Driver"] == driver].copy()
                        row_df["Year"] = year
                        row_df["Grand Prix"] = gp_name
                        row_df["EventDate"] = row["EventDate"]
                        all_dfs.append(row_df)
        except Exception as e:
            print(f"❌ Failed {year}: {e}")
    if not all_dfs:
        print("⚠️ No race data found.")
        return pd.DataFrame(), None, None, None
    full_df = pd.concat(all_dfs).sort_values("EventDate", ascending=True)
    full_df["Scope"] = None

    df_2025 = full_df[(full_df["Year"] == 2025) & (full_df["Scope"].isna())]
    df_2025 = df_2025.sort_values("EventDate", ascending=True)
    last_3 = df_2025.tail(3)
    prev_3 = df_2025.iloc[-4:-1] if len(df_2025) >= 4 else last_3

    seasonal_avg = df_2025["Total Points"].mean()
    career_avg = full_df["Total Points"].mean()
    last_3_avg = last_3["Total Points"].mean()
    prev_3_avg = prev_3["Total Points"].mean()

    weighted_total = round(career_avg * 0.1 + seasonal_avg * 0.7 + last_3_avg * 0.2, 2)
    previous_weighted = round(career_avg * 0.1 + seasonal_avg * 0.7 + prev_3_avg * 0.2, 2)
    fantasy_value = calculate_fantasy_value(career_avg,seasonal_avg,last_3_avg)

    scope_rows = []
    if not last_3.empty:
        row = last_3.mean(numeric_only=True)
        row["Scope"] = "Last 3 Races Avg"
        row["Driver"] = driver
        scope_rows.append(row)
    if not prev_3.empty:
        row = prev_3.mean(numeric_only=True)
        row["Scope"] = "Prev 3 Races Avg"
        row["Driver"] = driver
        scope_rows.append(row)
    if not df_2025.empty:
        row = df_2025.mean(numeric_only=True)
        row["Scope"] = "Seasonal Average"
        row["Driver"] = driver
        scope_rows.append(row)

    if scope_rows:
        full_df = pd.concat([full_df, pd.DataFrame(scope_rows)], ignore_index=True)
    return full_df, weighted_total, fantasy_value, previous_weighted


def generate_all_driver_ratings():
    drivers = get_all_cached_drivers()
    all_driver_dfs = []
    rating_summary = []

    for driver in drivers:
        try:
            df, weighted_total, fantasy_value, previous_weighted = generate_driver_rating(driver)
            if df.empty:
                print(f"⚠️ Skipping {driver}: empty data.")
                continue

            df = df.copy()

            if "Year" not in df.columns or "EventDate" not in df.columns:
                print(f"❌ Skipping {driver}: 'Year' or 'EventDate' column missing.")
                continue

            # Ensure 'Scope' column exists to avoid KeyError
            if "Scope" not in df.columns:
                df["Scope"] = None

            # Only use real races (exclude scoped rows)
            df_2025 = df[(df["Year"] == 2025) & (df["Scope"].isna())]
            df_2025 = df_2025.sort_values("EventDate", ascending=True)
            print(f"{driver}: {len(df_2025)} races in 2025")

            if df_2025.empty:
                continue

            # Add scope rows
            scope_rows = []

            df_2025_real = df[(df["Year"] == 2025) & (df["Scope"].isna())].sort_values("EventDate", ascending=True)

            last_3 = df_2025_real.tail(3)
            prev_3 = df_2025_real.iloc[-4:-1]


            if not last_3.empty:
                row = last_3.mean(numeric_only=True)
                row["Scope"] = "Last 3 Races Avg"
                row["Driver"] = driver
                row["Year"] = 2025
                scope_rows.append(row)

            if not prev_3.empty:
                row = prev_3.mean(numeric_only=True)
                row["Scope"] = "Prev 3 Races Avg"
                row["Driver"] = driver
                row["Year"] = 2025
                scope_rows.append(row)

            real_races = df[df["Scope"].isna()].sort_values("EventDate", ascending=True)
            career_avg = real_races["Total Points"].mean() if not real_races.empty else None

            if career_avg is not None:
                row = real_races.mean(numeric_only=True)
                row["Scope"] = "Career Average"
                row["Driver"] = driver
                row["Year"] = real_races["Year"].max()  # or use row["Year"] = real_races["Year"].max() if needed
                scope_rows.append(row)


            season_row = df_2025.mean(numeric_only=True)
            season_row["Scope"] = "Seasonal Average"
            season_row["Driver"] = driver
            season_row["Year"] = 2025
            scope_rows.append(season_row)

            if scope_rows:
                df = pd.concat([df, pd.DataFrame(scope_rows)], ignore_index=True)

            # Save enriched CSV for this driver
            df.to_csv(os.path.join(CACHE_DIR, f"Driver Rating - {driver}.csv"), index=False)

            # Build summary row if valid
            if all(pd.notna([weighted_total, fantasy_value, previous_weighted])):
                rating_summary.append({
                    "Driver": driver,
                    "Weighted Total": weighted_total,
                    "Fantasy Value": fantasy_value,
                    "Previous Weighted": previous_weighted
                })
            else:
                print(f"⚠️ Skipping summary for {driver}: NaN in stats.")

            # For leaderboard CSV (includes scoped rows)
            all_driver_dfs.append(df[df["Year"] == 2025].copy())

            print(f"✅ Generated: {driver}")

        except Exception as e:
            print(f"❌ Failed: {driver}: {e}")

    # Save quick lookup table for homepage driver stats
    summary_path = os.path.join(CACHE_DIR, "driver_rating_summary.csv")
    if rating_summary:
        summary_df = pd.DataFrame(rating_summary)
        summary_df = summary_df.sort_values("Weighted Total", ascending=False)
        summary_df.to_csv(summary_path, index=False)
        print(f"📊 Saved driver_rating_summary.csv with {len(summary_df)} entries.")
    else:
        print("❌ No summary entries generated. Check why df_2025 or values were empty.")

    # Save per-driver 2025 average stats
    if all_driver_dfs:
        combined = pd.concat(all_driver_dfs)
        combined = combined.drop_duplicates(subset=["Driver", "Grand Prix"])
        avg_df = combined.groupby("Driver")[["Quali", "Race", "+Pos", "Total Points"]].mean().round(2).reset_index()
        avg_df = avg_df.sort_values("Total Points", ascending=False)
        avg_df.to_csv(os.path.join(CACHE_DIR, "averages_2025.csv"), index=False)
        print("📊 Saved averages_2025.csv")





def regenerate_driver_rating_summary():
    files = [f for f in os.listdir(CACHE_DIR) if f.startswith("Driver Rating - ")]
    rows = []
    for file in files:
        path = os.path.join(CACHE_DIR, file)
        try:
            df = pd.read_csv(path)
            driver = df["Driver"].dropna().iloc[0]
            df["Scope"] = df.get("Scope", None)
            real_races = df[df["Scope"].isna()].sort_values("EventDate", ascending=True)
            if real_races.empty:
                continue
            seasonal_row = df[df["Scope"] == "Seasonal Average"]
            last3_row = df[df["Scope"] == "Last 3 Races Avg"]
            prev3_row = df[df["Scope"] == "Prev 3 Races Avg"]

            avg = seasonal_row["Total Points"].values[0] if not seasonal_row.empty else real_races["Total Points"].mean()
            career = real_races["Total Points"].mean()
            last3 = last3_row["Total Points"].values[0] if not last3_row.empty else avg
            prev3 = prev3_row["Total Points"].values[0] if not prev3_row.empty else last3

            weighted_total = round(career * 0.1 + avg * 0.7 + last3 * 0.2, 2)
            previous_weighted = round(career * 0.1 + avg * 0.7 + prev3 * 0.2, 2)
            fantasy_value = calculate_fantasy_value(career_avg,seasonal_avg,last_3_avg)

            rows.append({
                "Driver": driver,
                "Weighted Total": weighted_total,
                "Fantasy Value": fantasy_value,
                "Previous Weighted": previous_weighted
            })
        except Exception as e:
            print(f"❌ Failed to parse {file}: {e}")
    if rows:
        summary_df = pd.DataFrame(rows)
        summary_df = summary_df.sort_values("Weighted Total", ascending=False)
        summary_df.to_csv(os.path.join(CACHE_DIR, "driver_rating_summary.csv"), index=False)
        print("✅ Rebuilt driver_rating_summary.csv")
    else:
        print("⚠️ No rows to write.")
