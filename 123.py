from flask import Flask, render_template, request, jsonify
import cv2
import numpy as np
import base64
import sqlite3
import os

try:
    import easyocr
except ImportError:
    raise ImportError("Install it using: pip install easyocr")

app = Flask(__name__)
reader = easyocr.Reader(['en'], gpu=False)

DATABASE = 'plates.db'

# Initialize DB
def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Main vehicle table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS number_plate_records (
            plate_number TEXT PRIMARY KEY,
            owner_name TEXT NOT NULL,
            model TEXT NOT NULL,
            balance REAL NOT NULL
        )
    ''')

    # Deduction history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deduction_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number TEXT,
            deduction_amount REAL,
            deduction_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            remaining_balance REAL,
            FOREIGN KEY (plate_number) REFERENCES number_plate_records(plate_number)
        )
    ''')

    # Insert some sample data
    sample_data = [
        ('HR99G1000', 'John Doe', 'Hyundai i20', 300),
        ('DL09CD5678', 'Priya Sharma', 'Honda City', 150),
        ('KA05EF9012', 'Ravi Kumar', 'Maruti Swift', 70)
    ]
    for record in sample_data:
        cursor.execute("INSERT OR IGNORE INTO number_plate_records VALUES (?, ?, ?, ?)", record)

    conn.commit()
    conn.close()

# Route: Homepage
@app.route('/')
def index():
    return render_template('index.html')

# Route: OCR Decode and DB Update
@app.route('/decode', methods=['POST'])
def decode():
    data = request.json['image']
    encoded_data = data.split(',')[1]
    img_bytes = base64.b64decode(encoded_data)
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Resize if needed
    MAX_DIM = 640
    h, w = img.shape[:2]
    if max(h, w) > MAX_DIM:
        scale = MAX_DIM / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))

    # OCR to read plate
    results = reader.readtext(img)
    plate_text = ''
    for (bbox, text, prob) in results:
        if prob > 0.5:
            plate_text += text.strip().replace(" ", "")  # Remove whitespace

    plate_text = plate_text.upper()

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM number_plate_records WHERE plate_number = ?", (plate_text,))
    record = cursor.fetchone()

    if record:
        plate, owner, model, balance = record
        deduction = 50.0

        if balance >= deduction:
            new_balance = balance - deduction
            cursor.execute("UPDATE number_plate_records SET balance = ? WHERE plate_number = ?", (new_balance, plate))
            cursor.execute("INSERT INTO deduction_history (plate_number, deduction_amount, remaining_balance) VALUES (?, ?, ?)",
                           (plate, deduction, new_balance))
            conn.commit()
            conn.close()
            return jsonify({
                'plate': plate,
                'owner': owner,
                'model': model,
                'balance': new_balance,
                'message': f"₹{deduction} deducted. Remaining ₹{new_balance}"
            })
        else:
            conn.close()
            return jsonify({
                'plate': plate,
                'owner': owner,
                'model': model,
                'balance': balance,
                'message': "Insufficient balance!"
            })
    else:
        conn.close()
        return jsonify({'plate': plate_text, 'message': 'Plate not found in records.'})

# Main runner

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()

    import webbrowser
    import threading

    def open_browser():
        webbrowser.open_new('http://127.0.0.1:5000')

    threading.Timer(1.0, open_browser).start()
    app.run(debug=True)

