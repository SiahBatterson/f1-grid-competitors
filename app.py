from flask import Flask, render_template, request, Response, url_for
import pandas as pd
import os
import fastf1
import time
from datetime import datetime
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, Response, url_for, redirect
from flask_login import LoginManager
from model import db, User


from utils import (
    calculate_points,
    generate_driver_rating,
    generate_all_driver_ratings,
    get_all_cached_drivers,
    get_last_processed_race
)


fastf1.Cache.enable_cache("/mnt/f1_cache")
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////mnt/f1_cache/users.db'
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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
        "LAW": "Liam Lawson",
        "DOO": "Jack Doohan"
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
        driver_image_map = {
        "ALB": "Alex.webp",
        "SAI": "Carlos.webp",
        "LEC": "Charles.webp",
        "OCO": "Ocon.webp",
        "ALO": "Fernando.webp",
        "BOR": "Gabe.webp",
        "RUS": "FuckFace.webp",
        "HAD": "Isack.webp",
        "DOO": "Jack.webp",
        "ANT": "Kimi.webp",
        "STR": "Lance.webp",
        "NOR": "Lando.webp",
        "HAM": "Lewis.webp",
        "PIA": "Oscar.webp",
        "GAS": "Pierre.webp",
        "SAR": "Logan.webp",
        "VER": "Max.webp",
        "ZHO": "Guanyu.webp",
        "TSU": "Yuki.webp",
        "BOT": "Valtteri.webp",
        "HUL": "Nico.webp"
    }
        driver = (
        request.form.get("driver") if request.method == "POST"
        else request.args.get("driver")
    )

        img_filename = driver_image_map.get(driver, "placeholder.webp")
        driver_img_url = url_for("static", filename=f"driver_images/{img_filename}")
        if not driver:
            return "<h2>⚠️ Please enter a valid driver abbreviation.</h2><a href='/'>⬅ Back</a>"

        try:
            df, weighted_avg, fantasy_value, previous_weighted_avg = generate_driver_rating(driver)

            season_avg_row = df[df["Scope"] == "Seasonal Average"].drop(columns=["Q/R/+O", "Year", "Grand Prix"])
            last_3_row = df[df["Scope"] == "Last 3 Races Avg"].drop(columns=["Q/R/+O", "Year", "Grand Prix"])
            prev_3_row = df[df["Scope"] == "Prev 3 Races Avg"].drop(columns=["Q/R/+O", "Year", "Grand Prix"])
            last_race_row = df[df["Scope"].isna()].iloc[0:1].drop(columns=["Q/R/+O", "Year", "Grand Prix"])

            # Format for display
            fantasy_value_display = f"${round(fantasy_value):,}" if fantasy_value else "N/A"
            previous_value = round((season_avg_row["Total Points"].values[0] * 0.9 + previous_weighted_avg * 0.1) * 250000) if previous_weighted_avg else None
            previous_value_display = f"${previous_value:,}" if previous_value else "N/A"

            # Color and % change
            if fantasy_value and previous_value:
                value_color = "green" if fantasy_value > previous_value else "red"
                percent_change = ((fantasy_value - previous_value) / previous_value) * 100
                percent_display = f"({percent_change:+.1f}%)"
            else:
                value_color = "black"
                percent_display = ""
                weekday = datetime.utcnow().weekday()
            return render_template(
                "driver_rating.html",
                driver=driver,
                driver_img_url=driver_img_url,
                fantasy_value=fantasy_value_display,
                previous_value=previous_value_display,
                value_color=value_color,
                percent_display=percent_display,
                season_avg=season_avg_row.to_dict(orient="records")[0],
                last_3=last_3_row.to_dict(orient="records")[0],
                prev_3=prev_3_row.to_dict(orient="records")[0],
                last_race=last_race_row.to_dict(orient="records")[0],
                weekday=weekday
            )
        except Exception as e:
            return f"<h2>❌ Failed to generate rating: {e}</h2><a href='/'>⬅ Back</a>", 500

    return "<h2>Use the form to POST a driver abbreviation.</h2>"


@app.route("/add_driver/<driver>", methods=["POST"])
@login_required
def add_driver(driver):
    driver = driver.upper()
    team = current_user.drivers.split(",") if current_user.drivers else []
    price = get_driver_price(driver)
    MAX_TEAM_SIZE = 5

    if driver in team:
        return "❌ Already on your team.", 400

    if len(team) >= MAX_TEAM_SIZE:
        return "❌ Team full.", 400

    if current_user.balance < price:
        return f"❌ Not enough balance. {driver} costs ${price:,}", 400

    team.append(driver)
    current_user.drivers = ",".join(team)
    current_user.balance -= price
    db.session.commit()
    return redirect("/")



@app.route("/remove_driver/<driver>", methods=["POST"])
@login_required
def remove_driver(driver):
    driver = driver.upper()
    team = current_user.drivers.split(",")
    price = get_driver_price(driver)

    if driver in team:
        team.remove(driver)
        current_user.drivers = ",".join(team)
        current_user.balance += price
        db.session.commit()
    return redirect("/")





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

@app.route("/profile")
@login_required
def profile():
    drivers = current_user.drivers.split(",") if current_user.drivers else []
    driver_cards = []

    driver_info = {
        "VER": {"name": "Max Verstappen", "image": "Max.webp"},
        "TSU": {"name": "Yuki Tsunoda", "image": "Yuki.webp"},
        "LEC": {"name": "Charles Leclerc", "image": "Charles.webp"},
        "HAM": {"name": "Lewis Hamilton", "image": "Lewis.webp"},
        "RUS": {"name": "George Russell", "image": "FuckFace.webp"},
        "ANT": {"name": "Andrea Kimi Antonelli", "image": "Kimi.webp"},
        "NOR": {"name": "Lando Norris", "image": "Lando.webp"},
        "PIA": {"name": "Oscar Piastri", "image": "Oscar.webp"},
        "ALO": {"name": "Fernando Alonso", "image": "Fernando.webp"},
        "STR": {"name": "Lance Stroll", "image": "Lance.webp"},
        "GAS": {"name": "Pierre Gasly", "image": "Pierre.webp"},
        "COL": {"name": "Franco Colapinto", "image": "placeholder.webp"},
        "OCO": {"name": "Esteban Ocon", "image": "Ocon.webp"},
        "BEA": {"name": "Oliver Bearman", "image": "placeholder.webp"},
        "ALB": {"name": "Alex Albon", "image": "Alex.webp"},
        "SAI": {"name": "Carlos Sainz", "image": "Carlos.webp"},
        "HUL": {"name": "Nico Hülkenberg", "image": "Nico.webp"},
        "BOR": {"name": "Gabriel Bortoleto", "image": "Gabe.webp"},
        "HAD": {"name": "Isack Hadjar", "image": "Isack.webp"},
        "LAW": {"name": "Liam Lawson", "image": "placeholder.webp"},
        "DOO": {"name": "Jack Doohan", "image": "Jack.webp"},
        "SAR": {"name": "Logan Sargeant", "image": "Logan.webp"},
        "BOT": {"name": "Valtteri Bottas", "image": "Valtteri.webp"},
        "ZHO": {"name": "Guanyu Zhou", "image": "Guanyu.webp"}
    }

    total_driver_value = 0
    for code in drivers:
        try:
            df, hype, value, previous = generate_driver_rating(code)
            img_filename = driver_info.get(code, {}).get("image", "placeholder.webp")
            full_name = driver_info.get(code, {}).get("name", code)
            driver_img_url = url_for("static", filename=f"driver_images/{img_filename}")
            total_driver_value += value or 0

            value_class = ""
            if value is not None and previous is not None:
                value_class = "text-success" if value > previous else "text-danger"

            driver_cards.append({
                "code": code,
                "name": full_name,
                "image": driver_img_url,
                "hype": hype,
                "value": value,
                "value_class": value_class
            })
        except Exception as e:
            print(f"❌ Failed to load driver {code}: {e}")
            continue

    balance = current_user.balance
    net_worth = balance + total_driver_value
    networth_class = "text-success" if net_worth >= 15000000 else "text-danger"
    net_worth_delta = net_worth - 15000000

    return render_template(
        "profile.html",
        user=current_user,
        driver_cards=driver_cards,
        balance=balance,
        net_worth_delta=net_worth_delta,
        net_worth=net_worth,
        networth_class=networth_class
    )




@app.route("/admin/users")
@login_required
def admin_users():
    if current_user.username == "siaaah":
        all_users = User.query.all()
        return render_template("admin_users.html", users=all_users)
    if current_user.username != "admin" or "siaaah":  # or use a proper role system later
        return "⛔ Access Denied", 403

    all_users = User.query.all()
    return render_template("admin_users.html", users=all_users)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"], method='pbkdf2:sha256')


        if User.query.filter_by(username=username).first():
            return "❌ Username already exists"
        
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        return redirect("/login")

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()
        if user and check_password_hash(user.password, request.form["password"]):
            login_user(user)
            return redirect("/")
        return "❌ Invalid login"
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect("/")

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

# Functions Not Routes

def get_driver_price(driver_code):
    try:
        _, _, fantasy_value, _ = generate_driver_rating(driver_code)
        return round(fantasy_value or 0)
    except Exception as e:
        print(f"⚠️ Could not get price for {driver_code}: {e}")
        return 0

import os

db_path = "/mnt/f1_cache/users.db"
if not os.path.exists(db_path):
    print("📦 Creating users.db and tables...")
    with app.app_context():
        db.create_all()
    print("✅ User table created.")
else:
    print("ℹ️ users.db already exists.")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)