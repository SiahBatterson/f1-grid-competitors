# model.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    password = db.Column(db.String(200))
    balance = db.Column(db.Float, default=15000000)
    drivers = db.Column(db.String, default="")  # comma-separated
    boosts = db.Column(db.String, default="")   # Format: "VER:qualifying;HAM:race"


class UserRaceResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    driver = db.Column(db.String)
    year = db.Column(db.Integer)
    race = db.Column(db.String)
    base_points = db.Column(db.Float)
    category = db.Column(db.String)  # "qualifying", "race", "pass"
    boosted = db.Column(db.Boolean, default=False)
    total_points = db.Column(db.Float)

class RosteredDrivers(db.Model):
    __tablename__ = 'rostered_drivers'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    driver = db.Column(db.String, nullable=False)
    hype_at_buy = db.Column(db.Float, nullable=False)
    value_at_buy = db.Column(db.Float, nullable=False)
    races_owned = db.Column(db.Integer, default=0)
    boost_points = db.Column(db.Float, default=0)
    current_value = db.Column(db.Float, default=0)