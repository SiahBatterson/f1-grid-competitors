import time
from flask import Flask
from model import db, Pet

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pet.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


def decay_once():
    with app.app_context():
        pets = Pet.query.all()
        for p in pets:
            p.food = max(p.food - 1, 0)
            p.water = max(p.water - 1, 0)
            p.fun = max(p.fun - 1, 0)
            p.xp += 1
            if p.xp >= 25:
                p.level += p.xp // 25
                p.xp %= 25
        db.session.commit()


def run_decay_loop():
    while True:
        decay_once()
        time.sleep(60)


if __name__ == '__main__':
    run_decay_loop()
