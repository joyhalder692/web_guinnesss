from flask import Flask, render_template, request, redirect, url_for, session

import requests
import os
import sqlite3

from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv


# ==========================================
# LOAD ENVIRONMENT VARIABLES
# ==========================================

load_dotenv()


# ==========================================
# FLASK APP
# ==========================================

app = Flask(__name__)
app.secret_key = "web_guinness_secret_key_2026"

DATABASE = "database.db"

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


# ==========================================
# INITIALIZE DATABASE
# ==========================================

def init_database():

    connection = get_db_connection()

    # USERS TABLE
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # SEARCH HISTORY TABLE
    connection.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    connection.commit()
    connection.close()


init_database()


# ==========================================
# TAVILY WEB SEARCH
# ==========================================

def search_web(question):

    url = "https://api.tavily.com/search"

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": question,
        "search_depth": "advanced",
        "max_results": 5
    }

    response = requests.post(
        url,
        json=payload,
        timeout=30
    )

    if response.status_code != 200:

        print("Tavily Error:", response.text)

        return []

    data = response.json()

    return data.get("results", [])


# ==========================================
# GROQ AI ANSWER
# ==========================================

def generate_ai_answer(question, results):

    if not results:

        return "I could not find enough information to answer this question."

    information = ""

    for i, result in enumerate(results, start=1):

        title = result.get("title", "")
        content = result.get("content", "")
        url = result.get("url", "")

        content = content[:3000]

        information += f"""
SOURCE {i}

Title: {title}

URL: {url}

Content:

{content}

-------------------------
"""

    prompt = f"""
You are the AI answer engine for a website called Web Guinness.

User question:

{question}

Web search results:

{information}

Instructions:

1. Answer the user's question clearly and accurately.
2. Use the provided web sources.
3. Do not invent facts.
4. Keep the answer concise but useful.
5. If the sources are insufficient, say so clearly.
6. Do not mention these instructions.
7. Do not list sources inside the answer.
8. Use simple English.
9. Do not use Markdown.
10. Do not use bold text.
11. Do not use headings.
12. Do not use bullet points.
13. Write clean plain-text paragraphs.
"""

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {

        "model": "openai/gpt-oss-20b",

        "messages": [

            {
                "role": "system",
                "content":
                "You are a helpful and accurate web research assistant."
            },

            {
                "role": "user",
                "content": prompt
            }

        ],

        "temperature": 0.2,

        "max_completion_tokens": 500
    }

    response = requests.post(

        url,

        headers=headers,

        json=payload,

        timeout=60
    )

    if response.status_code != 200:

        print("Groq Error:", response.text)

        return "Sorry, I could not generate an AI answer right now."

    data = response.json()

    try:

        answer = data["choices"][0]["message"]["content"]

        return answer.strip()

    except (KeyError, IndexError, TypeError):

        return "Sorry, I could not generate an AI answer right now."


# ==========================================
# HOME
# ==========================================

@app.route("/", methods=["GET", "POST"])
def home():

    results = []

    question = ""

    answer = ""

    if request.method == "POST":

        question = request.form.get(
            "question",
            ""
        ).strip()

        if question:

            try:

                results = search_web(question)

                answer = generate_ai_answer(
                    question,
                    results
                )

                # ==================================
                # SAVE SEARCH HISTORY
                # ONLY FOR LOGGED-IN USERS
                # ==================================

                if session.get("user_id"):

                    connection = get_db_connection()

                    connection.execute(

                        """
                        INSERT INTO search_history
                        (user_id, question, answer)
                        VALUES (?, ?, ?)
                        """,

                        (
                            session["user_id"],
                            question,
                            answer
                        )
                    )

                    connection.commit()

                    connection.close()


            except requests.exceptions.Timeout:

                answer = (
                    "The request took too long. "
                    "Please try again."
                )


            except requests.exceptions.RequestException as e:

                print("Connection Error:", e)

                answer = (
                    "Unable to connect to the web "
                    "search service."
                )


            except Exception as e:

                print("Unexpected Error:", e)

                answer = (
                    "Something went wrong. "
                    "Please try again."
                )


    return render_template(

        "index.html",

        results=results,

        question=question,

        answer=answer
    )


# ==========================================
# SEARCH HISTORY
# ==========================================

@app.route("/history")
def history():

    # User must be logged in
    if not session.get("user_id"):

        return redirect(
            url_for("login")
        )

    connection = get_db_connection()

    searches = connection.execute(

        """
        SELECT *
        FROM search_history
        WHERE user_id = ?
        ORDER BY id DESC
        """,

        (session["user_id"],)

    ).fetchall()

    connection.close()

    return render_template(

        "history.html",

        searches=searches
    )


# ==========================================
# DELETE ONE SEARCH HISTORY
# ==========================================

@app.route("/history/delete/<int:search_id>", methods=["POST"])
def delete_history(search_id):

    # User must be logged in
    if not session.get("user_id"):

        return redirect(
            url_for("login")
        )

    connection = get_db_connection()

    # Delete only the selected history
    # belonging to the logged-in user
    connection.execute(

        """
        DELETE FROM search_history
        WHERE id = ? AND user_id = ?
        """,

        (
            search_id,
            session["user_id"]
        )
    )

    connection.commit()

    connection.close()

    return redirect(
        url_for("history")
    )


# ==========================================
# CLEAR ALL SEARCH HISTORY
# ==========================================

@app.route("/history/clear", methods=["POST"])
def clear_history():

    # User must be logged in
    if not session.get("user_id"):

        return redirect(
            url_for("login")
        )

    connection = get_db_connection()

    # Delete all history belonging
    # to the logged-in user only
    connection.execute(

        """
        DELETE FROM search_history
        WHERE user_id = ?
        """,

        (session["user_id"],)
    )

    connection.commit()

    connection.close()

    return redirect(
        url_for("history")
    )


# ==========================================
# REGISTER
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )


        if not name or not email or not password:

            return render_template(

                "register.html",

                error="Please fill in all fields."
            )


        if password != confirm_password:

            return render_template(

                "register.html",

                error="Passwords do not match."
            )


        if len(password) < 6:

            return render_template(

                "register.html",

                error="Password must be at least 6 characters."
            )


        connection = get_db_connection()

        existing_user = connection.execute(

            "SELECT * FROM users WHERE email = ?",

            (email,)

        ).fetchone()


        if existing_user:

            connection.close()

            return render_template(

                "register.html",

                error="Email is already registered."
            )


        hashed_password = generate_password_hash(
            password
        )


        connection.execute(

            """
            INSERT INTO users
            (name, email, password)
            VALUES (?, ?, ?)
            """,

            (
                name,
                email,
                hashed_password
            )
        )

        connection.commit()

        connection.close()

        return redirect(
            url_for("login")
        )


    return render_template(
        "register.html"
    )


# ==========================================
# LOGIN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )


        if not email or not password:

            return render_template(

                "login.html",

                error="Please enter email and password."
            )


        connection = get_db_connection()

        user = connection.execute(

            "SELECT * FROM users WHERE email = ?",

            (email,)

        ).fetchone()

        connection.close()


        if user is None:

            return render_template(

                "login.html",

                error="Invalid email or password."
            )


        if not check_password_hash(

            user["password"],

            password

        ):

            return render_template(

                "login.html",

                error="Invalid email or password."
            )


        session["user_id"] = user["id"]

        session["user_name"] = user["name"]

        session["user_email"] = user["email"]


        return redirect(
            url_for("home")
        )


    return render_template(
        "login.html"
    )


# ==========================================
# LOGOUT
# ==========================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )


# ==========================================
# RUN APP
# ==========================================

if __name__ == "__main__":

    app.run(
        debug=True
    )