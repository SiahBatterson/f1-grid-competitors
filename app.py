from flask import Flask, render_template, request
import pandas as pd
import os
from utils import calculate_points
import fastf1

fastf1.Cache.enable_cache("/mnt/f1_cache")
app = Flask(__name__)

@app.route("/")
def home():
    return render_template("home.html")

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
    cache_path = f"/mnt/f1_cache/averages_{year}.csv"

    # ✅ Try to load from disk first
    if os.path.exists(cache_path):
        avg_df = pd.read_csv(cache_path)
        print(f"✅ Loaded cached averages for {year}")
    else:
        print(f"🧮 Calculating averages for {year}")
        schedule = fastf1.get_event_schedule(year)
        all_results = [calculate_points(year, row["EventName"]) for _, row in schedule.iterrows() if not calculate_points(year, row["EventName"]).empty]

        if not all_results:
            return "<h2>No data to average.</h2>"

        df = pd.concat(all_results)
        drivers = df["Driver"].value_counts()
        df = df[df["Driver"].isin(drivers[drivers >= 5].index)]
        avg_df = df.groupby("Driver")[["Quali", "Race", "+Pos", "Total Points"]].mean().round(2).reset_index()
        avg_df = avg_df.sort_values("Total Points", ascending=False)

        # ✅ Save to disk for next time
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
