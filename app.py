from flask import Flask, render_template, request, Response
import pandas as pd
import os
import fastf1
import time

from utils import (
    calculate_points,
    generate_driver_rating,
    generate_all_driver_ratings,
    get_all_cached_drivers,
    get_last_processed_race
)

fastf1.Cache.enable_cache("/mnt/f1_cache")
app = Flask(__name__)

CACHE_DIR = "/mnt/f1_cache"

@app.route("/")
def home():
    drivers = get_all_cached_drivers()
    driver_name_map = {
        "VER": "Max Verstappen",
        "TSU": "Yuki Tsunoda",
        "LEC": "Charles Leclerc",
        "HAM": "Lewis Hamilton",
        "RUS": "George Russell",
        "ANT": "Andrea Kimi Antonelli",
        "NOR": "Lando Norris",
        "PIA": "Oscar Piastri",
        "ALO": "Fernando Alonso",
        "STR": "Lance Stroll",
        "GAS": "Pierre Gasly",
        "COL": "Franco Colapinto",
        "OCO": "Esteban Ocon",
        "BEA": "Oliver Bearman",
        "ALB": "Alex Albon",
        "SAI": "Carlos Sainz",
        "HUL": "Nico Hülkenberg",
        "BOR": "Gabriel Bortoleto",
        "HAD": "Isack Hadjar",
        "LAW": "Liam Lawson"
    }

    # Only show drivers with results from 2025
    try:
        df_2025 = pd.read_csv(os.path.join(CACHE_DIR, "averages_2025.csv"))
        drivers_2025 = set(df_2025["Driver"].dropna().unique())
        drivers = [d for d in drivers if d in drivers_2025]
    except Exception as e:
        print(f"⚠️ Couldn't load 2025 driver list: {e}")
        drivers = []

    top_drivers = []
    for d in drivers:
        try:
            df, hype, value, _ = generate_driver_rating(d)
            if "Scope" in df.columns:
                last_3_avg = df[df["Scope"].astype(str).str.strip() == "Last 3 Races Avg"]
                if not last_3_avg.empty:
                    top_drivers.append({
                        "driver": d,
                        "points": float(last_3_avg["Total Points"].values[0]),
                        "hype": round(float(hype), 2) if hype else 0,
                        "value": f"${round(float(value)):,.0f}" if value else "N/A"
                    })
        except Exception as e:
            print(f"❌ Failed to process driver {d}: {e}")
            continue

    top_drivers = sorted(top_drivers, key=lambda x: x["points"], reverse=True)[:3]
    print(f"🏆 Top drivers selected: {top_drivers}")
    last_race_used = get_last_processed_race()
    return render_template("home.html", drivers=drivers, driver_name_map=driver_name_map, top_drivers=top_drivers, last_race_used=last_race_used)


@app.route("/generate_all_driver_ratings", methods=["GET", "POST"])
def generate_all_driver_ratings_route():
    print("🚀 POST /generate_all_driver_ratings triggered")
    generate_all_driver_ratings()
    return "<h2>✅ Driver ratings generated.</h2><a href='/'>⬅ Back</a>"


@app.route("/clear_driver_ratings", methods=["POST"])
def clear_driver_ratings():
    def generate():
        yield "<h2>🪝 Clearing driver rating files...</h2><ul>"
        for file in os.listdir(CACHE_DIR):
            if file.startswith("Driver Rating -") and file.endswith(".csv"):
                try:
                    os.remove(os.path.join(CACHE_DIR, file))
                    yield f"<li>✅ Deleted {file}</li>"
                except Exception as e:
                    yield f"<li>❌ Failed to delete {file}: {e}</li>"
        yield "</ul><a href='/'>⬅ Back</a>"
    return Response(generate(), mimetype='text/html')


@app.route("/weighted")
def weighted():
    weighted_path = os.path.join(CACHE_DIR, "Weighted Driver Averages.csv")
    if not os.path.exists(weighted_path):
        return "<h2>⚠️ No weighted data found. Generate driver ratings first.</h2>"

    df = pd.read_csv(weighted_path)
    df = df.rename(columns={"Weighted Avg": "Hype"})
    df = df.sort_values(by="Hype", ascending=False)
    table = df.to_html(classes="table table-hover table-striped text-center", index=False)
    return render_template("weighted.html", table=table)

@app.route("/generate_driver_rating", methods=["GET", "POST"])
def generate_driver_rating_route():
    if request.method == "POST":
        driver = request.form.get("driver", "").upper().strip()
        if not driver:
            return "<h2>⚠️ Please enter a valid driver abbreviation.</h2><a href='/'>⬅ Back</a>"
        try:
            df, weighted_avg, fantasy_value, previous_weighted_avg = generate_driver_rating(driver)
            season_avg = df[df["Scope"].astype(str).str.strip() == "Seasonal Average"]
            season_avg_pts = float(season_avg["Total Points"].values[0]) if not season_avg.empty else 0.0
            fantasy_value_display = f"${round(fantasy_value):,}" if fantasy_value else "N/A"
            previous_value = round((season_avg_pts * 0.9 + previous_weighted_avg * 0.1) * 250000) if previous_weighted_avg else None
            previous_value_display = f"${previous_value:,}" if previous_value is not None else "N/A"
            # After previous_value and fantasy_value are calculated:
            if previous_weighted_avg:
                previous_value = round((season_avg_pts * 0.9 + previous_weighted_avg * 0.1) * 250000)
                percent_change = round(((fantasy_value - previous_value) / previous_value) * 100, 2)
                is_higher = fantasy_value > previous_value
                value_color = "green" if is_higher else "red"
                percent_display = f"{'▲' if is_higher else '▼'} {abs(percent_change)}%"
            else:
                previous_value = None
                percent_display = ""
                value_color = "black"


            return render_template(
            "driver_rating.html",
            table=df,  # Pass the actual DataFrame, not HTML
            driver=driver,
            season_avg=season_avg_pts,
            hype=weighted_avg,
            fantasy_value=f"${round(fantasy_value):,}",
            previous_value=f"${previous_value:,}" if previous_value else "N/A",
            weighted_avg=weighted_avg,
            previous_weighted=previous_weighted_avg,
            value_color=value_color,
            percent_display=percent_display
        )
        except Exception as e:
            return f"<h2>❌ Failed to generate rating: {e}</h2><a href='/'>⬅ Back</a>", 500
    return "<h2>Use the form to POST a driver abbreviation.</h2>"



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
        time.sleep(1)

    if all_results:
        avg_cache_file = os.path.join(CACHE_DIR, f"averages_{year}.csv")
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


@app.route("/averages")
def averages():
    year = int(request.args.get("year", 2023))
    cache_path = os.path.join(CACHE_DIR, f"averages_{year}.csv")

    if os.path.exists(cache_path):
        avg_df = pd.read_csv(cache_path)
        print(f"✅ Loaded cached averages for {year}")
    else:
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

    cache_path = os.path.join(CACHE_DIR, f"averages_{year}.csv")

    try:
        if os.path.exists(cache_path):
            os.remove(cache_path)
            return f"🗑️ Deleted cached averages for {year}"
        else:
            return f"ℹ️ No cached file found for year {year}"
    except Exception as e:
        return f"❌ Error deleting file: {e}", 500


@app.route("/season/<driver>")
def driver_season_view(driver):
    all_races = []
    for year in [2025, 2024, 2023, 2022, 2021]:
        try:
            schedule = fastf1.get_event_schedule(year)
            for _, row in schedule.iterrows():
                df = calculate_points(year, row["EventName"])
                if not df.empty and driver in df["Driver"].values:
                    row_df = df[df["Driver"] == driver].copy()
                    row_df["Year"] = year
                    row_df["Grand Prix"] = row["EventName"]
                    all_races.append(row_df)
        except Exception:
            continue

    if not all_races:
        return f"<h2>No race data for {driver}</h2><a href='/'>⬅ Back</a>"

    df = pd.concat(all_races)
    df = df[["Year", "Grand Prix", "Quali", "Race", "+Pos", "Q/R/+O", "Total Points"]]
    df = df.sort_values(by=["Year", "Grand Prix"], ascending=[False, False])
    return render_template("season.html", table=df.to_html(classes="table table-bordered text-center", index=False))

@app.route("/update_latest_race", methods=["POST"])
def update_latest_race():
    from datetime import datetime
    current_year = datetime.now().year
    schedule = fastf1.get_event_schedule(current_year)
    past_races = schedule[schedule['EventDate'] < pd.Timestamp.now()]

    if past_races.empty:
        return "<h2>⚠️ No races have occurred yet this season.</h2><a href='/'>⬅ Back</a>"

    latest_race = past_races.iloc[-1]
    race_name = latest_race["EventName"]

    print(f"🔄 Updating with latest race: {race_name}")
    df = calculate_points(current_year, race_name)

    if df.empty:
        return f"<h2>⚠️ Failed to calculate points for {race_name}.</h2><a href='/'>⬅ Back</a>"

    # Trigger update of affected drivers only
    for driver in df["Driver"].unique():
        try:
            generate_driver_rating(driver, force=True)
            print(f"✅ Updated rating for {driver}")
        except Exception as e:
            print(f"❌ Failed to update {driver}: {e}")

    return f"<h2>✅ Latest race ({race_name}) processed and ratings updated.</h2><a href='/'>⬅ Back</a>"



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)