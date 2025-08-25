import mysql.connector

import psycopg2
import os
# ----------------- Database Connection -----------------
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


# Check Database Connection
def test_database_connection():
    try:
        conn = connect_db()
        cursor = conn.cursor()
        
        # Run a simple query to check the connection
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        
        if result:
            print("Database connection successful!")
        else:
            print("Database connection failed!")
        
        conn.close()
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    
# Test the connection
test_database_connection()
