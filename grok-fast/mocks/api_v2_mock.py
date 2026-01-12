"""
Mock API for /api/v2 appointments
Simulates immediate, pending, delayed responses
"""

from flask import Flask, request, jsonify
import time
import random

app = Flask(__name__)

@app.route('/api/v2/appointments', methods=['POST'])
def mock_book():
    data = request.get_json()
    response_type = data.get('response_type', 'immediate')  # immediate, pending, delayed

    if response_type == 'immediate':
        return jsonify({
            'appointment_id': 'mock-apt-123',
            'status': 'booked',
            'datetime': data.get('datetime')
        }), 201
    elif response_type == 'pending':
        return jsonify({
            'appointment_id': 'mock-apt-pending',
            'status': 'pending',
            'message': 'Processing...'
        }), 202
    elif response_type == 'delayed':
        time.sleep(random.uniform(1, 3))  # Simulate delay
        return jsonify({
            'appointment_id': 'mock-apt-delayed',
            'status': 'booked',
            'datetime': data.get('datetime')
        }), 201
    else:
        return jsonify({'error': 'Unknown response type'}), 400

if __name__ == '__main__':
    app.run(port=5001, debug=True)