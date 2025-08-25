

# ----------------- Database Connection -----------------
import os
import psycopg2
from flask import Flask

import os
import psycopg2
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key_here")


def connect_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )


# ----------------- LOGIN -----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name, password FROM users WHERE LOWER(email)=%s", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session.permanent = True
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('dashboard'))

        return render_template('login.html', error="Invalid credentials")

    return render_template('login.html')

# ----------------- SIGNUP -----------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name     = request.form['name']
        gender   = request.form['gender']
        location = request.form['location']
        dob      = request.form['dob']
        email    = request.form['email']
        mobile   = request.form['mobile']
        pwd      = request.form['password']

        hashed = generate_password_hash(pwd)

        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (name, gender, location, dob, email, mobile, password)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (name, gender, location, dob, email, mobile, hashed))
        conn.commit()
        conn.close()

        return redirect(url_for('login'))
    return render_template('signup.html')

# ----------------- FORGOT PASSWORD -----------------
@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'POST':
        email = request.form['email']
        pwd   = request.form['password']
        hashed = generate_password_hash(pwd)

        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password=%s WHERE email=%s", (hashed, email))
        conn.commit()
        conn.close()

        return redirect(url_for('login'))
    return render_template('forgot.html')

# ----------------- DASHBOARD -----------------
@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    first_letter = username[0].upper()
    return render_template('dashboard.html', username=username, first_letter=first_letter)

# ----------------- LOGOUT -----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ----------------- BOOK TICKET (Search Form) -----------------
@app.route('/book_ticket', methods=['GET', 'POST'])
def book_ticket():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        src = request.form['source']
        dst = request.form['destination']
        dt  = request.form['date']
        return redirect(url_for('search_flights', source=src, destination=dst, date=dt))
    return render_template('book_ticket.html')

# ----------------- SEARCH FLIGHTS -----------------
@app.route('/search_flights', methods=['GET'])
def search_flights():
    source      = request.args.get('source')
    destination = request.args.get('destination')
    date        = request.args.get('date')  # keep for display only

    conn   = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, flight_number, departure_time, arrival_time, available_seats, price
        FROM flights
        WHERE source = %s
          AND destination = %s
    """, (source, destination))
    flights = cursor.fetchall()
    conn.close()

    return render_template('search_flights.html',
                           flights=flights,
                           source=source,
                           destination=destination,
                           selected_date=date)


# ----------------- BOOK TICKET PAGE -----------------
@app.route('/book_ticket/<int:flight_id>', methods=['GET', 'POST'])
def booking(flight_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = connect_db()
    cursor = conn.cursor()

    # Fetch flight details including price
    cursor.execute("SELECT flight_number, source, destination, price FROM flights WHERE id=%s", (flight_id,))
    flight = cursor.fetchone()

    if not flight:
        return "Flight not found", 404

    flight_number, source, destination, price = flight  # Unpack the price as well

    if request.method == 'POST':
        date = request.form['date']
        passenger_count = int(request.form['passenger_count'])
        passengers = []

        for i in range(1, passenger_count + 1):
            name = request.form.get(f'name{i}')
            age = request.form.get(f'age{i}')
            nationality = request.form.get(f'nationality{i}')
            gender = request.form.get(f'gender{i}')

            if name and age and nationality and gender:
                cursor.execute(""" 
                    INSERT INTO bookings (user_id, flight_id, passenger_name, age, nationality, gender, date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (session['user_id'], flight_id, name, age, nationality, gender, date))

                passengers.append({
                    'name': name,
                    'age': age,
                    'nationality': nationality,
                    'gender': gender
                })

        cursor.execute("UPDATE flights SET available_seats = available_seats - %s WHERE id = %s",
                       (passenger_count, flight_id))
        conn.commit()
        conn.close()

        session['booking_details'] = {
            'flight_number': flight_number,
            'id': flight_id,
            'source': source,
            'destination': destination,
            'selected_date': date,
            'passengers': passengers,
            'price': price,
            'total_amount': passenger_count * price
        }

        return redirect(url_for('payment'))

    # Handle GET request – set default date (today or blank)
    date = request.args.get('date', '')

    return render_template("booking.html", 
                           flight_id=flight_id, 
                           flight_number=flight_number, 
                           date=date, 
                           source=source, 
                           destination=destination)


from datetime import datetime
import random
from flask import render_template, request, redirect, url_for, session
import uuid
import mysql.connector


@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    booking = session.get('booking_details')
    if not booking:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        transaction_id = "TXN" + str(random.randint(100000, 999999))
        payment_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE bookings
        SET transaction_id = %s
        WHERE user_id = %s AND flight_id = %s AND transaction_id IS NULL
        """, (transaction_id, session['user_id'], booking['id']))
        conn.commit()
        conn.close()

        booking['transaction_id'] = transaction_id
        booking['payment_time'] = payment_time
        session['booking_details'] = booking

        return redirect(url_for('payment_success'))  # ✅ Redirect added

    return render_template("payment.html", total_amount=booking['total_amount'])

# ----------------- PAYMENT SUCCESS -----------------
@app.route('/payment_success')
def payment_success():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    booking = session.get('booking_details')
    if not booking:
        return redirect(url_for('dashboard'))

    return render_template('payment_success.html', 
                           transaction_id=booking['transaction_id'],
                           payment_time=booking['payment_time'],
                           total_amount=booking['total_amount'],
                           passengers=booking['passengers'],
                           flight_number=booking['flight_number'],
                           source=booking['source'],
                           destination=booking['destination'],
                           selected_date=booking['selected_date'])
 
@app.route('/my_bookings')
def my_bookings():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = connect_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT b.transaction_id, b.date AS selected_date, f.flight_number, f.source, f.destination, f.price,
               b.passenger_name AS name, b.age, b.gender, b.nationality
        FROM bookings b
        JOIN flights f ON b.flight_id = f.id
        WHERE b.user_id = %s AND b.transaction_id IS NOT NULL
        ORDER BY b.transaction_id DESC, b.id
    """, (session['user_id'],))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return render_template('my_bookings.html', bookings=[])

    grouped_bookings = {}
    for row in rows:
        txn = row['transaction_id']
        if txn not in grouped_bookings:
            grouped_bookings[txn] = {
                'transaction_id': txn,
                'selected_date': row['selected_date'],
                'flight_number': row['flight_number'],
                'source': row['source'],
                'destination': row['destination'],
                'total_amount': 0,
                'passengers': []
            }
        grouped_bookings[txn]['passengers'].append({
            'name': row['name'],
            'age': row['age'],
            'gender': row['gender'],
            'nationality': row['nationality']
        })
        grouped_bookings[txn]['total_amount'] += row['price']

    return render_template('my_bookings.html', bookings=list(grouped_bookings.values()))

# ----------------- CANCEL BOOKING -----------------
@app.route('/cancel_booking/<transaction_id>', methods=['GET', 'POST'])
def cancel_booking(transaction_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = connect_db()
    cursor = conn.cursor(dictionary=True)

    # Step 1: Get all bookings for this transaction_id and user
    cursor.execute("""
        SELECT b.id, b.flight_id
        FROM bookings b
        WHERE b.transaction_id = %s AND b.user_id = %s
    """, (transaction_id, session['user_id']))

    bookings = cursor.fetchall()

    if not bookings:
        conn.close()
        return redirect(url_for('dashboard'))  # Redirect to dashboard if no booking found

    if request.method == 'POST':
        # Step 2: Cancel the bookings
        for booking in bookings:
            cursor.execute("""
                UPDATE flights
                SET available_seats = available_seats + 1
                WHERE id = %s
            """, (booking['flight_id'],))

        # Step 2.2: Now, delete the booking entries
        cursor.execute("""
            DELETE FROM bookings
            WHERE transaction_id = %s AND user_id = %s
        """, (transaction_id, session['user_id']))

        conn.commit()
        conn.close()

        # After cancellation, show a success message and provide an option to go to the dashboard
        cancel_message = "Booking successfully cancelled and refund initiated!"
        return render_template('cancel_booking.html', transaction_id=transaction_id, cancel_message=cancel_message)

    conn.close()
    return render_template('cancel_booking.html', transaction_id=transaction_id)
@app.route('/general')
def general_info():
    return render_template('general.html')


#-------------------------------MANAGE PROFILE------------------------------------








@app.route('/manage_profile', methods=['GET', 'POST'])
def manage_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form['name']
        gender = request.form['gender']
        location = request.form['location']
        dob = request.form['dob']
        mobile = request.form['mobile']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password:
            if password == confirm_password:
                hashed_password = generate_password_hash(password)
                update_query = """
                    UPDATE users 
                    SET name=%s, gender=%s, location=%s, dob=%s, mobile=%s, password=%s 
                    WHERE user_id=%s
                """
                values = (name, gender, location, dob, mobile, hashed_password, user_id)
            else:
                conn.close()
                flash('Passwords do not match!', 'error')
                return redirect(url_for('manage_profile'))
        else:
            update_query = """
                UPDATE users 
                SET name=%s, gender=%s, location=%s, dob=%s, mobile=%s 
                WHERE user_id=%s
            """
            values = (name, gender, location, dob, mobile, user_id)

        cursor.execute(update_query, values)
        conn.commit()
        conn.close()

        session['username'] = name
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('dashboard'))

    # GET method - fetch existing user data
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()

    return render_template('manage_profile.html', user=user)   # ✅ added this
#-----------------------------------customer support-----------------------------------

@app.route('/customer_support', methods=['GET', 'POST'])
def customer_support():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = connect_db()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        message = request.form['message'].strip()
        timestamp = datetime.datetime.now()

        if message:
            # Insert user message into database
            insert_query = """  
                INSERT INTO support_chat (user_id, message, timestamp)  
                VALUES (%s, %s, %s) 
            """
            cursor.execute(insert_query, (user_id, message, timestamp))
            conn.commit()

            # Simulated bot response (basic automated reply)
            bot_response = "Thank you for your message! Our support team will assist you shortly."
            cursor.execute(insert_query, (0, bot_response, timestamp))  # 0 represents bot messages
            conn.commit()

    # Fetch chat history
    cursor.execute("SELECT * FROM support_chat WHERE user_id = %s OR user_id = 0 ORDER BY timestamp", (user_id,))
    chat_history = cursor.fetchall()

    conn.close()

    return render_template('customer_support.html', chat_history=chat_history)


#--------------------------------upload delay----------------------------------------
@app.route("/upload_delay", methods=["GET", "POST"])
def upload_delay():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="flight_db"
    )
    cursor = conn.cursor()

    if request.method == "POST":
        flight_number = request.form["flight_number"]
        delay_minutes = int(request.form["delay_minutes"])  
        reason = request.form["reason"]

        try:
            sql = "INSERT INTO flight_delays (flight_number, delay_minutes, reason) VALUES (%s, %s, %s)"
            cursor.execute(sql, (flight_number, delay_minutes, reason))
            conn.commit()
        except Exception as e:
            print(f"Database commit error: {e}")  

        cursor.close()
        conn.close()

        return redirect(url_for("upload_delay"))  

    # Fetch delay data
    cursor.execute("SELECT * FROM flight_delays ORDER BY id DESC")
    delays = cursor.fetchall()
    
    cursor.close()
    conn.close()

    return render_template("upload_delay.html", delays=delays)

if __name__ == "__main__":
    app.run(debug=True)


# ----------------- RUN APP -----------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
