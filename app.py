from flask import Flask, render_template, request
import pandas as pd
import os
from utils import calculate_points
from utils import generate_driver_rating
import fastf1
import time

fastf1.Cache.enable_cache("/mnt/f1_cache")
app = Flask(__name__)

CACHE_DIR = "/mnt/f1_cache"

@app.route("/")
def home():
    from utils import get_all_cached_drivers, generate_driver_rating

    drivers = get_all_cached_drivers()
    top_drivers = []

    for d in drivers:
        try:
            df, hype, value = generate_driver_rating(d)
            last_3_avg = df[df["Scope"] == "Last 3 Races Avg"]
            if not last_3_avg.empty:
                top_drivers.append({
                    "driver": d,
                    "points": last_3_avg["Total Points"].values[0],
                    "value": f"${value:,.0f}" if value else "N/A"
                })
        except Exception:
            continue

    top_drivers = sorted(top_drivers, key=lambda x: x["points"], reverse=True)[:3]
    return render_template("home.html", drivers=drivers, top_drivers=top_drivers)



from flask import request

@app.route("/clear_driver_ratings", methods=["POST"])
def clear_driver_ratings():
    deleted = []
    for file in os.listdir("/mnt/f1_cache"):
        if file.startswith("Driver Rating -") and file.endswith(".csv"):
            try:
                os.remove(os.path.join("/mnt/f1_cache", file))
                deleted.append(file)
            except Exception as e:
                print(f"❌ Failed to delete {file}: {e}")
    return f"<h2>🧹 Cleared {len(deleted)} driver rating files.</h2><a href='/'>⬅ Back</a>"

@app.route("/generate_driver_rating", methods=["POST"])
def generate_driver_rating_route():
    driver = request.form.get("driver", "").upper().strip()

    if not driver:
        return "<h2>⚠️ Please enter a valid driver abbreviation.</h2><a href='/'>⬅ Back</a>"

    try:
        df, _, _ = generate_driver_rating(driver)
        return render_template("driver_rating.html", table=df.to_html(classes="table table-bordered text-center", index=False), driver=driver)
    except Exception as e:
        return f"<h2>❌ Failed to generate rating: {e}</h2><a href='/'>⬅ Back</a>", 500


@app.route("/weighted")
def weighted():
    weighted_path = os.path.join(CACHE_DIR, "Weighted Driver Averages.csv")
    if not os.path.exists(weighted_path):
        return "<h2>⚠️ No weighted data found. Generate driver ratings first.</h2>"

    df = pd.read_csv(weighted_path)
    df = df.rename(columns={"Weighted Avg": "Hype"})  # Rename column
    df = df.sort_values(by="Hype", ascending=False)   # Sort by Hype descending

    table = df.to_html(classes="table table-hover table-striped text-center", index=False)
    return render_template("weighted.html", table=table)


@app.route("/generate_driver_rating", methods=["POST"])
def generate_driver_rating_route():
    driver = request.form.get("driver", "").upper().strip()

    if not driver:
        return "<h2>⚠️ Please enter a valid driver abbreviation.</h2><a href='/'>⬅ Back</a>"

    try:
        df = generate_driver_rating(driver)
        return render_template("driver_rating.html", table=df.to_html(classes="table table-bordered text-center", index=False), driver=driver)
    except Exception as e:
        return f"<h2>❌ Failed to generate rating: {e}</h2><a href='/'>⬅ Back</a>", 500





@app.route("/preload", methods=["POST"])
def preload():
    year = int(request.form.get("year", 2023))
    print(f"🔁 Manually triggered preload for {year}")

    try:
        schedule = fastf1.get_event_schedule(year)
    except Exception as e:
        return f"<h2>Failed to get schedule for {year}: {e}</h2>", 500

    all_results = []
    for _, row in schedule.iterrows():
        df = calculate_points(year, row["EventName"])
        if not df.empty:
            all_results.append(df)
        time.sleep(1)  # throttle

    if all_results:
        avg_cache_file = f"/mnt/f1_cache/averages_{year}.csv"
        df = pd.concat(all_results)
        drivers = df["Driver"].value_counts()
        df = df[df["Driver"].isin(drivers[drivers >= 5].index)]
        avg_df = df.groupby("Driver")[["Quali", "Race", "+Pos", "Total Points"]].mean().round(2).reset_index()
        avg_df = avg_df.sort_values("Total Points", ascending=False)
        avg_df.to_csv(avg_cache_file, index=False)
        return f"<h2>✅ Preloaded and cached averages for {year}</h2><a href='/'>⬅ Back</a>"
    else:
        return f"<h2>⚠️ No valid data for {year}</h2><a href='/'>⬅ Back</a>"


@app.route("/season")
def season():
    year = 2023
    schedule = fastf1.get_event_schedule(year)
    all_results = []
    for _, row in schedule.iterrows():
        df = calculate_points(year, row["EventName"])
        if not df.empty:
            df["Race ID"] = row["EventName"]
            all_results.append(df)

    if not all_results:
        return "<h2>No valid race data for this season.</h2>"

    season_df = pd.concat(all_results)
    return render_template("season.html", table=season_df.to_html(classes="table table-bordered text-center", index=False))

@app.route("/test_race")
def test_race():
    df = calculate_points(2023, "Australian Grand Prix")
    return df.to_html() if not df.empty else "⚠️ No data"


@app.route("/averages")
def averages():
    year = int(request.args.get("year", 2023))
    cache_path = f"/mnt/f1_cache/averages_{year}.csv"

    if os.path.exists(cache_path):
        avg_df = pd.read_csv(cache_path)
        print(f"✅ Loaded cached averages for {year}")
    else:
        print(f"🧮 Calculating averages for {year}")
        try:
            schedule = fastf1.get_event_schedule(year)
        except Exception as e:
            return f"<h2>Failed to load schedule for {year}: {e}</h2>", 500

        all_results = []
        for _, row in schedule.iterrows():
            df = calculate_points(year, row["EventName"])
            if not df.empty:
                all_results.append(df)
            time.sleep(1)


        if not all_results:
            return "<h2>No data to average.</h2>"

        df = pd.concat(all_results)
        drivers = df["Driver"].value_counts()
        df = df[df["Driver"].isin(drivers[drivers >= 5].index)]
        avg_df = df.groupby("Driver")[["Quali", "Race", "+Pos", "Total Points"]].mean().round(2).reset_index()
        avg_df = avg_df.sort_values("Total Points", ascending=False)

        avg_df.to_csv(cache_path, index=False)

    html_table = avg_df.to_html(classes="table table-bordered text-center", index=False)
    return render_template("averages.html", table=html_table, year=year, race_count=len(avg_df))


@app.route("/delete_averages")
def delete_averages():
    year = request.args.get("year")

    if not year or not year.isdigit():
        return "⚠️ Please provide a valid year (e.g., /delete_averages?year=2023)", 400

    cache_path = f"/mnt/f1_cache/averages_{year}.csv"

    try:
        if os.path.exists(cache_path):
            os.remove(cache_path)
            return f"🗑️ Deleted cached averages for {year}"
        else:
            return f"ℹ️ No cached file found for year {year}"
    except Exception as e:
        return f"❌ Error deleting file: {e}", 500


def preload_all_data(years=[2021, 2022, 2023, 2024, 2025]):
    session_types = ['Qualifying', 'Race']
    for year in years:
        print(f"🔍 Checking cache for season {year}")
        try:
            schedule = fastf1.get_event_schedule(year)
        except Exception as e:
            print(f"❌ Failed to get schedule for {year}: {e}")
            continue

        for _, row in schedule.iterrows():
            event_name = row["EventName"]
            for session_type in session_types:
                try:
                    event = fastf1.get_event(year, event_name)
                    session = event.get_session(session_type)

                    print(f"⬇️ Loading {year} {event_name} {session_type}")
                    session.load(telemetry=False, weather=False, laps=False)
                    print(f"✅ Cached: {year} {event_name} {session_type}")

                except Exception as e:
                    print(f"⚠️ Skipped {year} {event_name} {session_type}: {e}")

        # Cache averages if not already cached
        avg_cache_file = f"/mnt/f1_cache/averages_{year}.csv"
        if os.path.exists(avg_cache_file):
            print(f"✅ Averages already cached for {year}")
            continue

        print(f"🧮 Generating averages for {year}")
        all_results = []
        for _, row in schedule.iterrows():
            df = calculate_points(year, row["EventName"])
            if not df.empty:
                all_results.append(df)

        if all_results:
            df = pd.concat(all_results)
            drivers = df["Driver"].value_counts()
            df = df[df["Driver"].isin(drivers[drivers >= 5].index)]
            avg_df = df.groupby("Driver")[["Quali", "Race", "+Pos", "Total Points"]].mean().round(2).reset_index()
            avg_df = avg_df.sort_values("Total Points", ascending=False)
            avg_df.to_csv(avg_cache_file, index=False)
            print(f"📦 Averages saved to {avg_cache_file}")
        else:
            print(f"⚠️ No data to compute averages for {year}")


if __name__ == "__main__":
    #preload_all_data()  # 🧠 Preload everything on cold start
    app.run(host="0.0.0.0", port=5000)
