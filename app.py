from flask import Flask, render_template, request, redirect, session, flash, jsonify
from flask_wtf.csrf import CSRFProtect
import os
from datetime import datetime, timedelta
import sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave_super_secreta_123')

csrf = CSRFProtect(app)

ADMIN_USER = os.environ.get('ADMIN_USER', 'AbrahamNE')
ADMIN_PASS = os.environ.get('ADMIN_PASS', '0511_Abraham')


# 🔥 CREAR BASE DE DATOS
def crear_db():
    conn = sqlite3.connect("barberia.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reservas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        telefono TEXT,
        correo TEXT,
        corte TEXT,
        fecha TEXT,
        horario TEXT,
        estado TEXT DEFAULT 'Pendiente'
    )
    """)

    conn.commit()
    conn.close()

crear_db()


# 🏠 CLIENTE
@app.route("/")
def index():
    conn = sqlite3.connect("barberia.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM reservas")
    reservas = cursor.fetchall()

    conn.close()

    horas_ocupadas = [
        {"fecha": r["fecha"], "hora": r["horario"]}
        for r in reservas if r["estado"] != "Cancelado"
    ]

    fecha_min = datetime.now().strftime('%Y-%m-%d')
    fecha_max = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

    return render_template("index.html",
                           horas_ocupadas=horas_ocupadas,
                           fecha_min=fecha_min,
                           fecha_max=fecha_max)


# 💾 GUARDAR RESERVA
@app.route("/reservar", methods=["POST"])
def reservar():
    nombre = request.form["nombre"]
    telefono = request.form["telefono"]
    correo = request.form["correo"]
    corte = request.form["corte"]
    fecha = request.form["fecha"]
    horario = request.form["horario"]

    conn = sqlite3.connect("barberia.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO reservas (nombre, telefono, correo, corte, fecha, horario)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (nombre, telefono, correo, corte, fecha, horario))

    conn.commit()
    conn.close()

    flash("Reserva guardada con éxito 🔥")
    return redirect("/")


# 🔐 LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form["usuario"]
        password = request.form["clave"]

        if user == ADMIN_USER and password == ADMIN_PASS:
            session["admin"] = True
            return redirect("/admin")
        else:
            flash("❌ Usuario incorrecto")

    return render_template("login.html")


# 🔓 LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# 🧑‍💼 PANEL ADMIN
@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/login")

    conn = sqlite3.connect("barberia.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM reservas ORDER BY fecha, horario")
    reservas = cursor.fetchall()

    conn.close()

    return render_template("admin.html", reservas=reservas)


# ✅ ACEPTAR
@app.route("/gestionar/<int:id>/aceptar")
def aceptar(id):
    conn = sqlite3.connect("barberia.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE reservas SET estado='Aceptado' WHERE id=?", (id,))

    conn.commit()
    conn.close()

    return redirect("/admin")


# ❌ CANCELAR
@app.route("/gestionar/<int:id>/cancelar")
def cancelar(id):
    conn = sqlite3.connect("barberia.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE reservas SET estado='Cancelado' WHERE id=?", (id,))

    conn.commit()
    conn.close()

    return redirect("/admin")


# 🗑️ ELIMINAR
@app.route("/gestionar/<int:id>/eliminar")
def eliminar(id):
    conn = sqlite3.connect("barberia.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM reservas WHERE id=?", (id,))

    conn.commit()
    conn.close()

    return redirect("/admin")


# 📅 CALENDARIO
@app.route("/calendario")
def calendario():
    if not session.get("admin"):
        return redirect("/login")

    conn = sqlite3.connect("barberia.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM reservas")
    reservas = cursor.fetchall()

    conn.close()

    eventos = []

    for r in reservas:
        eventos.append({
            "title": r["nombre"],
            "start": f"{r['fecha']}T{r['horario']}",
            "extendedProps": {
                "servicio": r["corte"]
            }
        })

    return render_template("calendario.html", eventos=eventos)


# 📡 API CITAS
@app.route("/api/citas")
def api_citas():
    if not session.get('admin'):
        return jsonify([])

    conn = sqlite3.connect("barberia.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM reservas")
    reservas = cursor.fetchall()

    conn.close()

    eventos = []
    for r in reservas:
        if r["estado"] != "Cancelado":
            eventos.append({
                'id': r["id"],
                'title': f"{r['nombre']} - {r['corte']}",
                'start': f"{r['fecha']}T{r['horario']}",
                'color': '#d4af37' if r["estado"] == 'Aceptado' else '#ffc107',
                'extendedProps': {
                    'servicio': r["corte"],
                    'telefono': r["telefono"],
                    'estado': r["estado"]
                }
            })

    return jsonify(eventos)


# 🚀 INICIAR
if __name__ == "__main__":
    app.run(debug=True)