from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import pymongo
import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------
# MONGODB SETUP
# ---------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI")

try:
    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client.get_database('vault_db')
    users_col = db.get_collection('users')
    ledger_col = db.get_collection('ledger')
    goals_col = db.get_collection('goals')
    client.server_info()
    print("✅ MongoDB Atlas Connected Successfully")
except Exception as e:
    print(f"⚠️ MongoDB Connection Failed: {e}")

@app.route('/')
def index():
    return render_template('index.html')

# ---------------------------------------------------------
# AUTH ENDPOINTS
# ---------------------------------------------------------
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Username and Password required'}), 400

    user = users_col.find_one({"username": username})
    
    if user:
        if user['password'] == password:
            return jsonify({'status': 'success', 'message': 'Login successful'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Invalid Password'}), 401
    else:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'status': 'error', 'message': 'All fields required'}), 400

    if users_col.find_one({"username": username}):
        return jsonify({'status': 'error', 'message': 'Username already exists'}), 409

    users_col.insert_one({"username": username, "password": password})
    return jsonify({'status': 'success', 'message': 'Account created! Please login.'}), 201

# ---------------------------------------------------------
# TRANSACTION ENDPOINTS
# ---------------------------------------------------------
@app.route('/transaction', methods=['POST'])
def upload():
    data = request.get_json()
    name = data.get('name')
    amount = float(data.get('amount', 0))
    txn_type = data.get('type')
    note = data.get('note', 'No reason')

    if not name or not amount:
        return jsonify({'status': 'error', 'message': 'Data missing'}), 400

    record = {
        "username": name,
        "amount": amount,
        "type": txn_type,
        "note": note,
        "timestamp": time.time()
    }
    ledger_col.insert_one(record)
    return jsonify({'status': 'success', 'message': 'Transaction saved'}), 200

@app.route('/get_balance', methods=['GET'])
def get_balance():
    username = request.args.get('name')
    if not username:
        return jsonify({'status': 'error', 'message': 'Username required'}), 400

    pipeline = [
        {"$match": {"username": username}},
        {"$group": {
            "_id": None,
            "total": {
                "$sum": {
                    "$cond": [{"$eq": ["$type", "Credit"]}, "$amount", {"$multiply": ["$amount", -1]}]
                }
            }
        }}
    ]
    result = list(ledger_col.aggregate(pipeline))
    balance = result[0]['total'] if result else 0.0
    return jsonify({'status': 'success', 'balance': balance}), 200

# ---------------------------------------------------------
# ANALYTICS ENDPOINTS
# ---------------------------------------------------------
@app.route('/analytics', methods=['GET'])
def get_analytics():
    username = request.args.get('name')
    if not username:
        return jsonify({'status': 'error', 'message': 'Username required'}), 400

    now = datetime.now()
    start_of_day = datetime(now.year, now.month, now.day).timestamp()
    start_of_month = datetime(now.year, now.month, 1).timestamp()
    start_of_year = datetime(now.year, 1, 1).timestamp()

    def get_stats(since):
        pipe = [
            {"$match": {"username": username, "timestamp": {"$gte": since}}},
            {"$group": {
                "_id": "$type",
                "total": {"$sum": "$amount"}
            }}
        ]
        res = list(ledger_col.aggregate(pipe))
        gains = 0
        spends = 0
        for r in res:
            if r['_id'] == 'Credit': gains = r['total']
            if r['_id'] == 'Debit': spends = r['total']
        return gains, spends

    d_g, d_s = get_stats(start_of_day)
    m_g, m_s = get_stats(start_of_month)
    y_g, y_s = get_stats(start_of_year)

    return jsonify({
        'status': 'success',
        'daily': {'gains': d_g, 'spends': d_s},
        'monthly': {'gains': m_g, 'spends': m_s},
        'yearly': {'gains': y_g, 'spends': y_s}
    }), 200

@app.route('/get_ledger', methods=['GET'])
def get_ledger():
    username = request.args.get('name')
    cursor = ledger_col.find({"username": username}).sort("timestamp", -1)
    data = []
    for doc in cursor:
        doc['_id'] = str(doc['_id'])
        data.append(doc)
    return jsonify(data), 200

# ---------------------------------------------------------
# DIARY ENDPOINTS
# ---------------------------------------------------------
@app.route('/save_goal', methods=['POST'])
def save_goal():
    data = request.get_json()
    username = data.get('username')
    target = float(data.get('target', 0))
    strategies = data.get('strategies')

    record = {
        "username": username,
        "target": target,
        "strategies": strategies,
        "timestamp": time.time()
    }
    goals_col.insert_one(record)
    return jsonify({'status': 'success'}), 200

@app.route('/get_goals', methods=['GET'])
def get_goals():
    username = request.args.get('name')
    cursor = goals_col.find({"username": username}).sort("timestamp", -1)
    data = []
    for doc in cursor:
        doc['_id'] = str(doc['_id'])
        data.append(doc)
    return jsonify(data), 200




if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
