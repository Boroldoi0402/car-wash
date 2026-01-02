from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import date, timedelta


app = Flask(__name__)
app.secret_key = "secretkey123"

# =========================
# Admin config
# =========================
ADMIN_PHONE = "89730419"     # ← өөрийн админы утас
ADMIN_PASSWORD = "Puntsag0402" # ← өөрийн нууц үг


# =========================
# Database connection
# =========================
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


# =========================
# Home page
# =========================
@app.route("/")
def index():
    if "user" in session:
        return render_template("index.html")
    return redirect("/login")


# =========================
# Login (phone number only)
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form["phone"]

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE
            )
        """)

        cur.execute("SELECT id FROM users WHERE phone=?", (phone,))
        user = cur.fetchone()

        if not user:
            cur.execute("INSERT INTO users (phone) VALUES (?)", (phone,))
            conn.commit()

        conn.close()
        session["user"] = phone
        return redirect("/")

    return render_template("login.html")

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    error = None

    if request.method == "POST":
        phone = request.form.get("phone")
        password = request.form.get("password")

        if phone == ADMIN_PHONE and password == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
        else:
            error = "❌ Утас эсвэл нууц үг буруу"

    return render_template("admin_login.html", error=error)



# =========================
# Booking page
# =========================
@app.route("/booking", methods=["GET", "POST"])
def booking():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    # --- tables ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            date TEXT,
            plate TEXT,
            services TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            max_cars INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS blocked_days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE
        )
    """)

    DEFAULT_MAX = 8   # 🟢 ерөнхий лимит

    # =====================
    # POST – захиалга хийх
    # =====================
    if request.method == "POST":
        date_selected = request.form.get("date")
        plate = request.form.get("plate", "").upper().strip()
        services_list = request.form.getlist("services")
        services_str = ",".join(services_list)


        if not date_selected or not plate:
            conn.close()
            return "❌ Өдөр болон улсын дугаарыг бүрэн оруулна уу"

        # 🔒 хаалттай өдөр шалгах
        cur.execute("SELECT 1 FROM blocked_days WHERE date=?", (date_selected,))
        if cur.fetchone():
            conn.close()
            return "❌ Энэ өдөр захиалга авахгүй (хаалттай)"

        # 🚫 ижил өдөр + ижил дугаар
        cur.execute(
            "SELECT 1 FROM bookings WHERE date=? AND plate=?",
            (date_selected, plate)
        )
        if cur.fetchone():
            conn.close()
            return "❌ Энэ улсын дугаар аль хэдийн захиалагдсан байна"

        # 🔢 тухайн өдрийн лимит авах
        cur.execute(
            "SELECT max_cars FROM daily_limits WHERE date=?",
            (date_selected,)
        )
        row = cur.fetchone()
        max_limit = row["max_cars"] if row else DEFAULT_MAX

        # 🚗 тухайн өдөр хэдэн машин байгаа вэ
        cur.execute("SELECT COUNT(*) FROM bookings WHERE date=?", (date_selected,))
        count = cur.fetchone()[0]

        if count >= max_limit:
            conn.close()
            return f"❌ Энэ өдөр {max_limit} машин авах лимиттэй"

        # ✅ insert
        cur.execute(
            "INSERT INTO bookings (user, date, plate, services) VALUES (?, ?, ?, ?)",
            (session["user"], date_selected, plate, services_str)
        )


        conn.commit()
        conn.close()
        return redirect("/booking")

    # =====================
    # GET – ойрын 3 хоног
    # =====================
    today = date.today()
    days = []

    for i in range(3):
        d = (today + timedelta(days=i)).isoformat()

        # тухайн өдрийн лимит
        cur.execute("SELECT max_cars FROM daily_limits WHERE date=?", (d,))
        row = cur.fetchone()
        max_limit = row["max_cars"] if row else DEFAULT_MAX

        # хэдэн машин байна
        cur.execute("SELECT COUNT(*) FROM bookings WHERE date=?", (d,))
        count = cur.fetchone()[0]

        # хаалттай эсэх
        cur.execute("SELECT 1 FROM blocked_days WHERE date=?", (d,))
        blocked = cur.fetchone() is not None

        days.append({
            "date": d,
            "full": count >= max_limit,
            "blocked": blocked,
            "limit": max_limit,
            "count": count
        })

    conn.close()
    return render_template("booking.html", days=days)


# =========================
# Admin page
# =========================
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if "admin" not in session:
        return redirect("/admin-login")

    conn = get_db()
    cur = conn.cursor()

    # --------- DELETE BOOKING ----------
    if request.method == "POST" and "delete_id" in request.form:
        cur.execute(
            "DELETE FROM bookings WHERE id=?",
            (request.form["delete_id"],)
        )
        conn.commit()

    # --------- BLOCK DAY ----------
    if request.method == "POST" and "block_date" in request.form:
        cur.execute(
            "INSERT OR IGNORE INTO blocked_days (date) VALUES (?)",
            (request.form["block_date"],)
        )
        conn.commit()

    # --------- UNBLOCK DAY ----------
    if request.method == "POST" and "unblock_date" in request.form:
        cur.execute(
            "DELETE FROM blocked_days WHERE date=?",
            (request.form["unblock_date"],)
        )
        conn.commit()

    # --------- ADMIN ADD BOOKING ----------
    if request.method == "POST" and "admin_add" in request.form:
        cur.execute(
            "INSERT INTO bookings (user, date, plate) VALUES (?, ?, ?)",
            ("ADMIN", request.form["date"], request.form["plate"].upper())
        )
        conn.commit()

    # --------- FILTER BY DATE ----------
    selected_date = request.args.get("date")

    if selected_date:
        cur.execute("""
            SELECT id, date, plate, user
            FROM bookings
            WHERE date=?
            ORDER BY date
        """, (selected_date,))
    else:
        cur.execute("""
            SELECT id, date, plate, user
            FROM bookings
            ORDER BY date
        """)

    # --------- SET DAILY LIMIT ----------
    if request.method == "POST" and "limit_date" in request.form:
        cur.execute("""
            INSERT INTO daily_limits (date, max_cars)
            VALUES (?, ?)
            ON CONFLICT(date)
            DO UPDATE SET max_cars=excluded.max_cars
        """, (request.form["limit_date"], request.form["max_cars"]))
    conn.commit()


    bookings = cur.fetchall()
    conn.close()

    return render_template(
        "admin.html",
        bookings=bookings,
        selected_date=selected_date
    )



# =========================
# Logout
# =========================
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

@app.route("/admin-logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin-login")



# =========================
# Run server
# =========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
    
