from flask import Flask, request, jsonify
import time
import threading

app = Flask(__name__)

# Behavior controls for tests
STATE = {
    'fail_next': 0,
    'delay': 0.0,
    'bookings': []
}

@app.route('/api/v2/calendar', methods=['POST'])
def book():
    data = request.get_json() or {}
    if STATE['delay'] > 0:
        time.sleep(STATE['delay'])
    if STATE['fail_next'] > 0:
        STATE['fail_next'] -= 1
        return ("", 500)
    # create booking
    calendar_id = f"cal_{len(STATE['bookings'])+1}"
    STATE['bookings'].append({'calendar_id': calendar_id, 'data': data})
    return jsonify({'calendar_id': calendar_id})

@app.route('/__admin/state', methods=['POST'])
def set_state():
    d = request.get_json() or {}
    STATE.update(d)
    return ("", 204)

@app.route('/__admin/state', methods=['GET'])
def get_state():
    return jsonify(STATE)

if __name__ == '__main__':
    app.run(port=5001)
