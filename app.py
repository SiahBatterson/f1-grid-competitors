from flask import Flask, render_template, request, Response
import pandas as pd
import os
import fastf1
import time

from utils import (
    calculate_points,
    generate_driver_rating,
    generate_all_driver_ratings,
    get_all_cached_drivers
)

fastf1.Cache.enable_cache("/mnt/f1_cache")
app = Flask(__name__)

CACHE_DIR = "/mnt/f1_cache"

@app.route("/")
def home():
    drivers = get_all_cached_drivers()
    driver_name_map = {
        "VER": "Max Verstappen", "HAM": "Lewis Hamilton", "LEC": "Charles Leclerc",
        "SAI": "Carlos Sainz", "PER": "Sergio Perez", "ALO": "Fernando Alonso",
        "NOR": "Lando Norris", "PIA": "Oscar Piastri", "RUS": "George Russell",
        "TSU": "Yuki Tsunoda", "ZHO": "Zhou Guanyu", "ALB": "Alex Albon",
        "SAR": "Logan Sargeant", "HUL": "Nico Hulkenberg", "MAG": "Kevin Magnussen",
        "RIC": "Daniel Ricciardo", "BOT": "Valtteri Bottas", "GAS": "Pierre Gasly",
        "OCO": "Esteban Ocon"
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
            df, hype, value = generate_driver_rating(d)
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
    return render_template("home.html", drivers=drivers, driver_name_map=driver_name_map, top_drivers=top_drivers)


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


def generate_driver_rating(driver_abbr, force=False):
    output_path = os.path.join(CACHE_DIR, f"Driver Rating - {driver_abbr}.csv")
    if os.path.exists(output_path) and not force:
        print(f"📂 Using cached driver rating for {driver_abbr}")
        df = pd.read_csv(output_path)
        return df, None, None, None

    print(f"🧲 Generating fresh driver rating for {driver_abbr}")
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
        return pd.DataFrame([{"Error": f"❌ No valid data for {driver_abbr}"}]), None, None, None

    full_df = pd.concat(all_driver_races, ignore_index=True)
    full_df = full_df.sort_values(by=["Year", "Grand Prix"], ascending=[False, False])

    last_3 = full_df.head(3)
    prev_3 = full_df.iloc[1:4]  # Shifted window

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

    full_out = pd.concat([seasonal_avg, last_3, last_3_avg], ignore_index=True)
    full_out.to_csv(output_path, index=False)

    avg = seasonal_avg["Total Points"].values[0]
    fantasy_value = round(((avg * 0.9) + (weighted_total * 0.1)) * 250000, 2)

    return full_out, weighted_total, fantasy_value, previous_weighted



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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)