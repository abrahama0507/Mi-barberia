from flask import Flask, render_template, request, redirect, session, flash, jsonify
from flask_wtf.csrf import CSRFProtect
import os
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave_super_secreta_123')

csrf = CSRFProtect(app)

ADMIN_USER = os.environ.get('ADMIN_USER', 'AbrahamNE')
ADMIN_PASS = os.environ.get('ADMIN_PASS', '0511_Abraham')


# 🔥 CONEXIÓN CORRECTA A RENDER
def get_db_connection():
    return psycopg2.connect(os.environ.get("DATABASE_URL"), cursor_factory=RealDictCursor)


def crear_tablas():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reservas (
        id SERIAL PRIMARY KEY,
        nombre TEXT NOT NULL,
        telefono TEXT NOT NULL,
        correo TEXT NOT NULL,
        corte TEXT NOT NULL,
        fecha TEXT NOT NULL,
        horario TEXT NOT NULL,
        estado TEXT DEFAULT 'Pendiente'
    )
    """)
    
    conn.commit()
    cursor.close()
    conn.close()

crear_tablas()


# 🏠 CLIENTE
@app.route("/")
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM reservas")
    reservas = cursor.fetchall()
    
    conn.close()
    
    horas_ocupadas = [
        {"fecha": r["fecha"], "hora": r["horario"]}
        for r in reservas if r["estado"] in ["Pendiente", "Aceptado"]
    ]
    
    fecha_min = datetime.now().strftime('%Y-%m-%d')
    fecha_max = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    
    return render_template("index.html",
                           horas_ocupadas=horas_ocupadas,
                           fecha_min=fecha_min,
                           fecha_max=fecha_max)


# 💾 RESERVAR
@app.route("/reservar", methods=["POST"])
def reservar():
    nombre = request.form["nombre"]
    telefono = request.form["telefono"]
    correo = request.form["correo"]
    corte = request.form["corte"]
    fecha = request.form["fecha"]
    horario = request.form["horario"]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO reservas (nombre, telefono, correo, corte, fecha, horario)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (nombre, telefono, correo, corte, fecha, horario))
    
    conn.commit()
    cursor.close()
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


# 🧑‍💼 ADMIN
@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/login")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM reservas ORDER BY fecha, horario")
    reservas = cursor.fetchall()
    
    conn.close()
    
    return render_template("admin.html", reservas=reservas)


# ✅ ACEPTAR
@app.route("/gestionar/<int:id>/aceptar")
def aceptar(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE reservas SET estado='Aceptado' WHERE id=%s", (id,))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect("/admin")


# ❌ CANCELAR
@app.route("/gestionar/<int:id>/cancelar")
def cancelar(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE reservas SET estado='Cancelado' WHERE id=%s", (id,))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect("/admin")


# 🗑️ ELIMINAR
@app.route("/gestionar/<int:id>/eliminar")
def eliminar(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM reservas WHERE id=%s", (id,))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect("/admin")


# 📅 CALENDARIO
@app.route("/calendario")
def calendario():
    if not session.get("admin"):
        return redirect("/login")

    conn = get_db_connection()
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


# 📡 API
@app.route("/api/citas")
def api_citas():
    if not session.get('admin'):
        return jsonify([])

    conn = get_db_connection()
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


# 🚀 RUN
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port) 