from flask import Flask, render_template_string, redirect, url_for, request
import pandas as pd
import fastf1
from fastf1.core import Laps

import os

# Ensure cache directory exists
os.makedirs('f1_cache', exist_ok=True)

fastf1.Cache.enable_cache('f1_cache')

app = Flask(__name__)

def calculate_points(year, gp_name):
    try:
        event = fastf1.get_event(year, gp_name)
        quali = event.get_session('Qualifying')
        race = event.get_session('Race')

        quali.load()
        race.load()

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
        df['points_from_race'] = (21 - df['position_race']) * 1
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

        df['Q/R/+O'] = df.apply(lambda row: f"{row['points_from_quali']}/{row['points_from_race']}/{row['points_from_gain']}", axis=1)
        return df[['Driver', 'Quali', 'Race', '+Pos', 'Q/R/+O', 'Total Points']]

    except Exception as e:
        print(f"Error processing {year} {gp_name}: {e}")
        return pd.DataFrame()

@app.route("/")
def home():
    return render_template_string("""
    <html>
    <head>
        <title>F1 Fantasy App</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="container mt-5">
        <h1 class="mb-4">F1 Fantasy Leaderboard</h1>
        <a href="{{ url_for('season') }}" class="btn btn-primary btn-lg">🏁 View All Race Scores</a>
        <a href="{{ url_for('averages') }}" class="btn btn-secondary btn-lg ms-3">📊 View Driver Averages</a>
    </body>
    </html>
    """)

@app.route("/season")
def season():
    year = 2023
    schedule = fastf1.get_event_schedule(year)
    all_results = []
    for _, row in schedule.iterrows():
        df = calculate_points(year, row['EventName'])
        if not df.empty:
            df["Race ID"] = row['EventName']
            all_results.append(df)

    if not all_results:
        return "<h2>No valid race data for this season.</h2>"

    season_df = pd.concat(all_results)
    html_table = season_df.to_html(classes="table table-bordered table-striped text-center", index=False)
    return render_template_string("""
    <html>
    <head>
        <title>Season Scores</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="container mt-5">
        <h1 class="mb-4">🏎️ All Race Scores</h1>
        <a href="/" class="btn btn-outline-dark mb-3">⬅️ Back</a>
        <div class="table-responsive">
            {{ table|safe }}
        </div>
    </body>
    </html>
    """, table=html_table)

@app.route("/averages")
def averages():
    year = int(request.args.get("year", 2023))
    schedule = fastf1.get_event_schedule(year)
    all_results = []

    for _, row in schedule.iterrows():
        df = calculate_points(year, row['EventName'])
        if not df.empty:
            all_results.append(df)

    valid_race_count = len(all_results)

    if not all_results:
        return "<h2>No data to average.</h2>"

    season_df = pd.concat(all_results)
    appearance_counts = season_df["Driver"].value_counts()
    qualified_drivers = appearance_counts[appearance_counts >= 5].index
    filtered_df = season_df[season_df["Driver"].isin(qualified_drivers)]

    avg_df = (
        filtered_df.groupby("Driver")
        .agg({
            "Quali": "mean",
            "Race": "mean",
            "+Pos": "mean",
            "Total Points": "mean"
        })
        .round(2)
        .reset_index()
        .sort_values("Total Points", ascending=False)
    )

    html_table = avg_df.to_html(classes="table table-bordered table-striped text-center", index=False)

    return render_template_string("""
    <html>
    <head>
        <title>Average Fantasy Scores</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="container mt-5">
        <h1 class="mb-4">📊 Driver Averages — {{ year }} Season</h1>
        <p class="text-muted">Based on {{ race_count }} valid race sessions</p>
        <form method="get" action="/averages" class="mb-4">
            <label for="year" class="form-label">Select Season:</label>
            <select name="year" id="year" class="form-select w-auto d-inline" onchange="this.form.submit()">
                {% for y in [2025, 2024, 2023, 2022, 2021] %}
                    <option value="{{ y }}" {% if y == year %}selected{% endif %}>{{ y }}</option>
                {% endfor %}
            </select>
        </form>
        <a href="/" class="btn btn-outline-dark mb-3">⬅️ Back</a>
        <div class="table-responsive">
            {{ table|safe }}
        </div>
    </body>
    </html>
    """, table=html_table, year=year, race_count=valid_race_count)

if __name__ == "__main__":
    app.run(debug=True)
