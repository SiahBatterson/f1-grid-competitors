from flask import Flask, request, jsonify
from model import db, Pet

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pet.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

@app.before_first_request
def create_tables():
    db.create_all()

@app.route('/api/pet/<int:pet_id>', methods=['GET', 'PUT'])
def handle_pet(pet_id):
    pet = Pet.query.get(pet_id)

    if request.method == 'GET':
        if pet:
            return jsonify(pet.to_dict())
        return jsonify({'error': 'Pet not found'}), 404

    data = request.get_json() or {}
    if not pet:
        pet = Pet(id=pet_id)
        db.session.add(pet)

    pet.food = data.get('food', pet.food)
    pet.water = data.get('water', pet.water)
    pet.fun = data.get('fun', pet.fun)
    pet.xp = data.get('xp', pet.xp)
    pet.level = data.get('level', pet.level)
    db.session.commit()
    return jsonify(pet.to_dict())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
