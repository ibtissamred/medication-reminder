
from flask import Flask, request, redirect, render_template_string
import sqlite3
from datetime import date, datetime

app = Flask(__name__)
DB_NAME = "medications.db"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def setup_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            dosage TEXT NOT NULL,
            frequency INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dose_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medication_id INTEGER NOT NULL,
            dose_date TEXT NOT NULL,
            dose_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            FOREIGN KEY (medication_id) REFERENCES medications(id)
        )
    """)
    conn.commit()
    conn.close()


def prepare_today():
    today = date.today().isoformat()
    conn = get_db()
    medications = conn.execute("""
        SELECT * FROM medications
        WHERE start_date <= ? AND end_date >= ?
    """, (today, today)).fetchall()

    for med in medications:
        for hour in range(24 // med["frequency"]):
            time = f"{hour * (24 // med['frequency']):02d}:00"
            exists = conn.execute("""
                SELECT id FROM dose_records
                WHERE medication_id = ? AND dose_date = ? AND dose_time = ?
            """, (med["id"], today, time)).fetchone()

            if not exists:
                conn.execute("""
                    INSERT INTO dose_records
                    (medication_id, dose_date, dose_time, status)
                    VALUES (?, ?, ?, 'Pending')
                """, (med["id"], today, time))

    conn.commit()
    conn.close()


@app.route("/")
def home():
    prepare_today()
    today = date.today().isoformat()
    conn = get_db()

    doses = conn.execute("""
        SELECT dose_records.*, medications.name, medications.dosage
        FROM dose_records
        JOIN medications ON medications.id = dose_records.medication_id
        WHERE dose_date = ?
        ORDER BY dose_time
    """, (today,)).fetchall()

    total = len(doses)
    taken = sum(1 for dose in doses if dose["status"] == "Taken")
    pending = sum(1 for dose in doses if dose["status"] == "Pending")

    medications = conn.execute("""
        SELECT * FROM medications ORDER BY name
    """).fetchall()
    conn.close()

    return render_template_string("""
    <!doctype html>
    <html>
    <head>
      <title>Medication Reminder</title>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <style>
        body {font-family: Arial; background:#f4f6fb; color:#263248;
              max-width:900px; margin:30px auto; padding:0 16px;}
        h1 {color:#5842a6;}
        .cards {display:flex; gap:12px; flex-wrap:wrap;}
        .card, .panel {background:white; padding:18px; border-radius:12px;
                       margin-bottom:16px; box-shadow:0 2px 8px #0001;}
        .card {flex:1; min-width:110px;}
        .number {font-size:26px; font-weight:bold;}
        input, select, button {padding:10px; margin:5px 0;
                              border:1px solid #ddd; border-radius:6px;}
        button {background:#5842a6; color:white; cursor:pointer; border:0;}
        a {color:#5842a6;}
        .dose {display:flex; justify-content:space-between; gap:12px;
               align-items:center; border-bottom:1px solid #eee; padding:12px 0;}
        .status {font-weight:bold;}
        form {display:inline;}
      </style>
    </head>
    <body>
      <h1>💊 Medication Reminder</h1>
      <p>Manage your medication schedule and keep track of recorded doses.</p>

      <div class="cards">
        <div class="card">Today's doses<div class="number">{{ total }}</div></div>
        <div class="card">Taken<div class="number">{{ taken }}</div></div>
        <div class="card">Pending<div class="number">{{ pending }}</div></div>
      </div>

      <div class="panel">
        <h2>Today's Schedule</h2>
        {% if doses %}
          {% for dose in doses %}
          <div class="dose">
            <div>
              <strong>{{ dose.name }}</strong> — {{ dose.dosage }}<br>
              <small>{{ dose.dose_time }}</small>
              <div class="status">{{ dose.status }}</div>
            </div>
            <div>
              {% if dose.status == 'Pending' %}
              <form method="post" action="/status/{{ dose.id }}/Taken">
                <button type="submit">Mark Taken</button>
              </form>
              <form method="post" action="/status/{{ dose.id }}/Missed">
                <button type="submit">Mark Missed</button>
              </form>
              {% endif %}
            </div>
          </div>
          {% endfor %}
        {% else %}
          <p>No doses scheduled today. Add a medication below to begin.</p>
        {% endif %}
      </div>

      <div class="panel">
        <h2>Add Medication</h2>
        <form method="post" action="/add">
          <label>Medication name<br>
            <input name="name" required maxlength="100" placeholder="Example: Vitamin D">
          </label><br>
          <label>Dosage instructions<br>
            <input name="dosage" required maxlength="100" placeholder="As prescribed">
          </label><br>
          <label>Doses per day<br>
            <select name="frequency">
              <option value="1">Once daily</option>
              <option value="2">Twice daily</option>
              <option value="3">Three times daily</option>
              <option value="4">Four times daily</option>
            </select>
          </label><br>
          <label>Start date<br>
            <input type="date" name="start_date" required value="{{ today }}">
          </label><br>
          <label>End date<br>
            <input type="date" name="end_date" required value="{{ today }}">
          </label><br>
          <button type="submit">Add Medication</button>
        </form>
        <p><small>Use only the schedule specified by a healthcare professional.
        The example times are generated automatically and are not medical advice.</small></p>
      </div>

      <div class="panel">
        <h2>Medication List</h2>
        {% for med in medications %}
          <p><strong>{{ med.name }}</strong> — {{ med.dosage }}
          ({{ med.frequency }} dose(s)/day)
          <form method="post" action="/delete/{{ med.id }}">
            <button type="submit">Delete</button>
          </form></p>
        {% else %}
          <p>No medications added yet.</p>
        {% endfor %}
      </div>

      <p><a href="/history">View Dose History →</a></p>
    </body>
    </html>
    """, doses=doses, total=total, taken=taken, pending=pending,
       medications=medications, today=today)


@app.route("/add", methods=["POST"])
def add_medication():
    name = request.form["name"].strip()
    dosage = request.form["dosage"].strip()
    frequency = int(request.form["frequency"])
    start_date = request.form["start_date"]
    end_date = request.form["end_date"]

    if (not name or not dosage or frequency not in (1, 2, 3, 4)
            or end_date < start_date):
        return "Please check the medication details and dates.", 400

    conn = get_db()
    conn.execute("""
        INSERT INTO medications (name, dosage, frequency, start_date, end_date)
        VALUES (?, ?, ?, ?, ?)
    """, (name, dosage, frequency, start_date, end_date))
    conn.commit()
    conn.close()
    return redirect("/")


@app.route("/status/<int:dose_id>/<status>", methods=["POST"])
def update_status(dose_id, status):
    if status not in ("Taken", "Missed"):
        return "Invalid status", 400

    conn = get_db()
    conn.execute("""
        UPDATE dose_records SET status = ?
        WHERE id = ? AND dose_date = ? AND status = 'Pending'
    """, (status, dose_id, date.today().isoformat()))
    conn.commit()
    conn.close()
    return redirect("/")


@app.route("/delete/<int:med_id>", methods=["POST"])
def delete_medication(med_id):
    conn = get_db()
    conn.execute("DELETE FROM dose_records WHERE medication_id = ?", (med_id,))
    conn.execute("DELETE FROM medications WHERE id = ?", (med_id,))
    conn.commit()
    conn.close()
    return redirect("/")


@app.route("/history")
def history():
    conn = get_db()
    records = conn.execute("""
        SELECT dose_records.*, medications.name, medications.dosage
        FROM dose_records
        JOIN medications ON medications.id = dose_records.medication_id
        ORDER BY dose_date DESC, dose_time DESC
        LIMIT 100
    """).fetchall()
    conn.close()

    return render_template_string("""
    <!doctype html>
    <html>
    <head>
      <title>Dose History</title>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <style>
        body {font-family:Arial; max-width:900px; margin:30px auto;
              padding:0 16px; background:#f4f6fb; color:#263248;}
        .panel {background:white; padding:18px; border-radius:12px;}
        table {width:100%; border-collapse:collapse;}
        th, td {padding:10px; text-align:left; border-bottom:1px solid #ddd;}
        a {color:#5842a6;}
      </style>
    </head>
    <body>
      <h1>Medication Dose History</h1>
      <div class="panel">
        <table>
          <tr><th>Date</th><th>Time</th><th>Medication</th><th>Status</th></tr>
          {% for r in records %}
          <tr>
            <td>{{ r.dose_date }}</td><td>{{ r.dose_time }}</td>
            <td>{{ r.name }} — {{ r.dosage }}</td><td>{{ r.status }}</td>
          </tr>
          {% else %}
          <tr><td colspan="4">No dose records yet.</td></tr>
          {% endfor %}
        </table>
      </div>
      <p><a href="/">← Back to Dashboard</a></p>
    </body>
    </html>
    """, records=records)


setup_db()

if __name__ == "__main__":
    app.run(debug=True)
