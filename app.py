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
from model import db, User, UserRaceResult


from core_utils import (
    get_all_cached_drivers,
    get_last_processed_race,
    get_cached_race,
    is_race_cached,
    fetch_and_cache_race
)
from points_utils import (
    generate_all_driver_ratings,
    process_latest_race_and_apply_boosts,
    process_single_race_and_apply_boosts,
    generate_driver_rating
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


@app.route("/admin/calculate_single", methods=["POST"])
@login_required
def admin_calculate_single():
    if current_user.username not in {"admin", "siaaah"}:
        return "⛔ Access Denied", 403

    year = int(request.form.get("year"))
    gp_name = request.form.get("gp_name")

    try:
        success, message = process_single_race_and_apply_boosts(year, gp_name)
        return f"<h3>{message}</h3><a href='/admin/management'>⬅ Back</a>"
        if df.empty:
            return f"<h3>❌ No data calculated for {year} - {gp_name}</h3><a href='/admin/management'>⬅ Back</a>"
        else:
            return f"<h3>✅ Race processed: {year} - {gp_name}</h3><a href='/admin/management'>⬅ Back</a>"
    except Exception as e:
        return f"<h3>❌ Failed to calculate race: {e}</h3><a href='/admin/management'>⬅ Back</a>"


@app.route("/admin/reset_user/<int:user_id>", methods=["POST"])
@login_required
def reset_user(user_id):
    if current_user.username not in {"admin", "siaaah"}:
        return "⛔ Access Denied", 403

    user = db.session.get(User, user_id)
    if not user:
        return "❌ User not found", 404

    user.balance = 15_000_000
    user.drivers = ""
    user.boosts = ""
    user.boost_type = ""
    user.boost_driver = ""
    user.boost_expiry = None
    db.session.commit()

    return redirect("/admin/users")


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

from model import RosteredDrivers

@app.route("/generate_driver_rating", methods=["GET", "POST"])
def generate_driver_rating_route():
    from model import RosteredDrivers

    driver_image_map = {
        "ALB": "Alex.webp", "SAI": "Carlos.webp", "LEC": "Charles.webp",
        "OCO": "Ocon.webp", "ALO": "Fernando.webp", "BOR": "Gabe.webp",
        "RUS": "FuckFace.webp", "HAD": "Isack.webp", "DOO": "Jack.webp",
        "ANT": "Kimi.webp", "STR": "Lance.webp", "NOR": "Lando.webp",
        "HAM": "Lewis.webp", "PIA": "Oscar.webp", "GAS": "Pierre.webp",
        "SAR": "Logan.webp", "VER": "Max.webp", "ZHO": "Guanyu.webp",
        "TSU": "Yuki.webp", "BOT": "Valtteri.webp", "HUL": "Nico.webp"
    }

    driver = request.form.get("driver") if request.method == "POST" else request.args.get("driver")
    if not driver:
        return "<h2>⚠️ Please enter a valid driver abbreviation.</h2><a href='/'>⬅ Back</a>"

    driver = driver.upper().strip()
    img_filename = driver_image_map.get(driver, "placeholder.webp")
    driver_img_url = url_for("static", filename=f"driver_images/{img_filename}")
    weekday = datetime.utcnow().weekday()

    try:
        df, weighted_avg, fantasy_value, previous_weighted_avg = generate_driver_rating(driver)

        if df.empty:
            return f"<h2>❌ No data available for {driver}</h2><a href='/'>⬅ Back</a>", 404

        # Stat rows
        season_avg_row = df[df["Scope"] == "Seasonal Average"].drop(columns=["Q/R/+O", "Year", "Grand Prix"])
        last_3_row = df[df["Scope"] == "Last 3 Races Avg"].drop(columns=["Q/R/+O", "Year", "Grand Prix"])
        prev_3_row = df[df["Scope"] == "Prev 3 Races Avg"].drop(columns=["Q/R/+O", "Year", "Grand Prix"])
        last_race_row = df[df["Scope"].isna()].iloc[0:1].drop(columns=["Q/R/+O", "Year", "Grand Prix"])

        fantasy_value_display = f"${round(fantasy_value):,}" if fantasy_value else "N/A"
        previous_value = (
            round((season_avg_row["Total Points"].values[0] * 0.9 + previous_weighted_avg * 0.1) * 250000)
            if previous_weighted_avg else None
        )
        previous_value_display = f"${previous_value:,}" if previous_value else "N/A"

        value_color = "green" if fantasy_value and previous_value and fantasy_value > previous_value else "red"
        percent_display = (
            f"({((fantasy_value - previous_value) / previous_value) * 100:+.1f}%)"
            if fantasy_value and previous_value else ""
        )

        # Get user-specific data
        user_stats = None
        if current_user.is_authenticated:
            user_roster = RosteredDrivers.query.filter_by(user_id=current_user.id, driver=driver).first()
            if user_roster:
                user_stats = {
                    "value_at_buy": round(user_roster.value_at_buy),
                    "boost_points": round(user_roster.boost_points),
                    "value_diff": round((fantasy_value or 0) - user_roster.value_at_buy),
                    "races_owned": user_roster.races_owned
                }

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
            weekday=weekday,
            user_stats=user_stats
        )

    except Exception as e:
        return f"<h2>❌ Failed to generate rating: {e}</h2><a href='/'>⬅ Back</a>", 500


@app.route("/admin/management")
@login_required
def admin_management():
    if current_user.username not in {"admin", "siaaah"}:
        return "⛔ Access Denied", 403

    cached_races = [f for f in os.listdir(CACHE_DIR) if f.endswith(".csv") and " - " in f]
    return render_template("admin_management.html", cached_races=sorted(cached_races))


@app.route("/boost/<category>", methods=["POST"])
@login_required
def activate_global_boost(category):
    category = category.lower()
    if category not in {"qualifying", "race", "pass"}:
        return "❌ Invalid boost category", 400

    BOOST_COST = 1_000_000

    if current_user.balance < BOOST_COST:
        return "❌ Not enough balance to activate this boost.", 400

    current_user.balance -= BOOST_COST
    current_user.boosts = category  # or store in boost_driver:category format if needed
    db.session.commit()

    return redirect("/profile")

@app.cli.command("clear_boosts")
def clear_boosts():
    users = User.query.all()
    for user in users:
        user.boosts = ""
    db.session.commit()
    print("✅ All boosts cleared")

@app.route("/admin/update_users", methods=["POST"])
@login_required
def update_users():
    if current_user.username not in {"admin", "siaaah"}:
        return "⛔ Access Denied", 403

    users = User.query.all()
    for user in users:
        balance_key = f"balance_{user.id}"
        drivers_key = f"drivers_{user.id}"

        if balance_key in request.form:
            try:
                user.balance = float(request.form[balance_key])
            except ValueError:
                pass  # Skip invalid inputs

        if drivers_key in request.form:
            user.drivers = request.form[drivers_key].strip()

    db.session.commit()
    return redirect("/admin/users")


from model import RosteredDrivers

@app.route("/add_driver/<driver>", methods=["POST"])
@login_required
def add_driver(driver):
    driver = driver.upper()
    team = current_user.drivers.split(",") if current_user.drivers else []
    MAX_TEAM_SIZE = 5

    if driver in team:
        return "❌ Already on your team.", 400

    if len(team) >= MAX_TEAM_SIZE:
        return "❌ Team full.", 400

    price = get_driver_price(driver)
    if current_user.balance < price:
        return f"❌ Not enough balance. {driver} costs ${price:,}", 400

    _, hype, value, _ = generate_driver_rating(driver)
    rostered = RosteredDrivers(
        user_id=current_user.id,
        driver=driver,
        hype_at_buy=hype,
        value_at_buy=value,
        current_value=value
    )
    db.session.add(rostered)

    team.append(driver)
    current_user.drivers = ",".join(team)
    current_user.balance -= price
    db.session.commit()
    return redirect("/")


    # Update user record
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

    if driver not in team:
        return "❌ Driver not on your team.", 400

    # Refund value based on current value
    record = RosteredDrivers.query.filter_by(user_id=current_user.id, driver=driver).first()
    refund = record.current_value if record else get_driver_price(driver)

    # Remove from rostered drivers
    if record:
        db.session.delete(record)

    # Update team
    team.remove(driver)
    current_user.drivers = ",".join(team)
    current_user.balance += refund

    db.session.commit()
    return redirect("/profile")


def get_user_driver_data(user_id):
    rostered = RosteredDrivers.query.filter_by(user_id=user_id).all()
    user_driver_data = {}
    for record in rostered:
        user_driver_data[record.driver] = {
            "hype_at_buy": record.hype_at_buy,
            "value_at_buy": record.value_at_buy,
            "current_value": record.current_value,
            "boost_points": record.boost_points,
            "races_owned": record.races_owned
        }
    return user_driver_data



@app.route("/preload", methods=["POST"])
def preload():
    year = int(request.form.get("year", 2023))
    print(f"🔁 Manually triggered preload for {year}")

    try:
        schedule = fastf1.get_event_schedule(year)

        # Limit to races before Miami 2025 (exclusive)
        if year == 2025:
            schedule = schedule[schedule["EventName"] != "Miami Grand Prix"]
        else:
            schedule = schedule[schedule['EventDate'] < pd.Timestamp.now()]
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


@app.route("/admin/delete_race", methods=["POST"])
@login_required
def delete_race_file():
    if current_user.username not in {"admin", "siaaah"}:
        return "⛔ Access Denied", 403

    race_file = request.form.get("race_file")
    path = os.path.join(CACHE_DIR, race_file)

    if not os.path.exists(path):
        return f"⚠️ File not found: {race_file}<br><a href='/admin/management'>⬅ Back</a>"

    try:
        # Extract race info
        year = int(race_file.split(" - ")[0])
        gp_name = race_file.split(" - ")[1].replace(".csv", "")

        # Step 1: Delete main race file
        os.remove(path)

        # Step 2: Delete LastProcessedRace file if matching
        last_race_path = os.path.join(CACHE_DIR, f"{year} - LastProcessedRace.txt")
        if os.path.exists(last_race_path):
            with open(last_race_path, "r") as f:
                if f"{year} - {gp_name}" in f.read():
                    os.remove(last_race_path)

        # Step 3: Remove from all Driver Rating files
        for file in os.listdir(CACHE_DIR):
            if file.startswith("Driver Rating - ") and file.endswith(".csv"):
                file_path = os.path.join(CACHE_DIR, file)
                df = pd.read_csv(file_path)
                df = df[~((df["Year"] == year) & (df["Grand Prix"] == gp_name))]
                df.to_csv(file_path, index=False)

        # Step 4: Rebuild Weighted Driver Averages
        weighted_path = os.path.join(CACHE_DIR, "Weighted Driver Averages.csv")
        if os.path.exists(weighted_path):
            os.remove(weighted_path)

        from utils import generate_all_driver_ratings
        generate_all_driver_ratings()

        # Step 5: Remove from averages file
        avg_path = os.path.join(CACHE_DIR, f"averages_{year}.csv")
        if os.path.exists(avg_path):
            df = pd.read_csv(avg_path)
            df = df[df["Grand Prix"] != gp_name]
            df.to_csv(avg_path, index=False)

        # Step 6: Remove FastF1 session cache
        try:
            import shutil
            event = fastf1.get_event(year, gp_name)
            session_path = os.path.join(CACHE_DIR, "f1data", str(year), event.Location)
            if os.path.exists(session_path):
                shutil.rmtree(session_path)
        except Exception as e:
            print(f"⚠️ Failed to delete FastF1 session cache: {e}")

        return f"✅ Deleted all traces of {race_file}<br><a href='/admin/management'>⬅ Back</a>"
    except Exception as e:
        return f"❌ Error deleting {race_file}: {e}<br><a href='/admin/management'>⬅ Back</a>"



@app.route("/season")
def season():
    year = 2023
    schedule = fastf1.get_event_schedule(year)
    schedule = schedule[schedule['EventDate'] < pd.Timestamp.now()]  # Only past races
    all_results = []
    for _, row in schedule.iterrows():
        df = calculate_points(year, row["EventName"])
        if not df.empty:
            df["Race ID"] = row["EventName"]
            all_results.append(df)

    if not all_results:
        return "<h2>No valid race data for this season.</h2>"

    season_df = pd.concat(all_results)
    races = season_df.to_dict(orient="records")
    return render_template("season.html", races=races)



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
            schedule = schedule[schedule['EventDate'] < pd.Timestamp.now()]  # Only past races
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
    boosts = current_user.boosts.split(";") if current_user.boosts else []
    active_boost = boosts[0].split(":")[1] if boosts and ":" in boosts[0] else ""

    from model import RosteredDrivers, UserRaceResult
    last_boost = UserRaceResult.query.filter_by(user_id=current_user.id).order_by(UserRaceResult.id.desc()).first()
    boost_bonus_points = round(last_boost.total_points - last_boost.base_points) if last_boost and last_boost.boosted else 0

    for code in drivers:
        try:
            df, hype, value, previous = generate_driver_rating(code)
            if not df.empty:
                driver_rec = RosteredDrivers.query.filter_by(user_id=current_user.id, driver=code).first()
                value_at_buy = driver_rec.value_at_buy if driver_rec else value
                boost_pts = driver_rec.boost_points if driver_rec else 0
                races_owned = driver_rec.races_owned if driver_rec else 0

                delta = round(value - value_at_buy) if value and value_at_buy else 0
                delta_class = "text-success" if delta >= 0 else "text-danger"

                img_filename = driver_info.get(code, {}).get("image", "placeholder.webp")
                full_name = driver_info.get(code, {}).get("name", code)
                driver_img_url = url_for("static", filename=f"driver_images/{img_filename}")
                total_driver_value += value or 0

                driver_cards.append({
                    "code": code,
                    "name": full_name,
                    "image": driver_img_url,
                    "hype": hype,
                    "value": value,
                    "value_at_buy": value_at_buy,
                    "boost_points": boost_pts,
                    "races_owned": races_owned,
                    "delta": delta,
                    "delta_class": delta_class
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
        active_boost=active_boost,
        boost_bonus_points=boost_bonus_points,
        driver_cards=driver_cards,
        balance=balance,
        net_worth_delta=net_worth_delta,
        net_worth=net_worth,
        networth_class=networth_class
    )

@app.route("/admin/users")
@login_required
def admin_users():
    if current_user.username not in {"admin", "siaaah"}:
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
@login_required
def driver_season_view(driver):
    from model import UserRaceResult

    all_races = []
    boost_lookup = {}

    for year in [2025, 2024, 2023, 2022, 2021]:
        try:
            schedule = fastf1.get_event_schedule(year)
            schedule = schedule[schedule['EventDate'] < pd.Timestamp.now()]  # ⛔ Filter future races

            for _, row in schedule.iterrows():
                gp_name = row["EventName"]
                df = calculate_single_race(year, gp_name)  # ✅ avoid overwriting last race file
                if not df.empty and driver in df["Driver"].values:
                    row_df = df[df["Driver"] == driver].copy()
                    row_df["Year"] = year
                    row_df["Grand Prix"] = gp_name

                    # Check if this user has a boosted record
                    result = UserRaceResult.query.filter_by(
                        user_id=current_user.id,
                        driver=driver,
                        year=year,
                        race=gp_name,
                        boosted=True
                    ).first()

                    if result:
                        row_df["Boost Note"] = f"Boosted for +{int(result.total_points - result.base_points)} points"
                    else:
                        row_df["Boost Note"] = ""

                    all_races.append(row_df)
        except Exception as e:
            print(f"⚠️ Failed for {year} {driver}: {e}")
            continue

    if not all_races:
        return "<h2>⚠️ No data available.</h2><a href='/'>⬅ Back</a>"

    df = pd.concat(all_races)
    df = df[["Year", "Grand Prix", "Quali", "Race", "+Pos", "Q/R/+O", "Total Points", "Boost Note"]]
    df = df.sort_values(by=["Year", "Grand Prix"], ascending=[False, False])
    return render_template("season.html", races=df.to_dict(orient="records"))


@app.route("/boost/<category>/<driver>", methods=["POST"])
@login_required
def activate_boost(category, driver):
    category = category.lower()
    if category not in {"qualifying", "race", "pass"}:
        return "❌ Invalid category", 400

    current_boosts = current_user.boosts.split(";") if current_user.boosts else []
    new_boost = f"{driver.upper()}:{category}"
    
    # Replace existing boost for same driver
    current_boosts = [b for b in current_boosts if not b.startswith(driver.upper())]
    current_boosts.append(new_boost)

    current_user.boosts = ";".join(current_boosts)
    db.session.commit()
    return redirect("/profile")


@app.route("/update_latest_race", methods=["POST"])
def update_latest_race():
    success, message = process_latest_race_and_apply_boosts()
    return f"<h2>{message}</h2><a href='/'>⬅ Back</a>"


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