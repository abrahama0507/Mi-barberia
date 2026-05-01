import re
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

# 🛡️ CONFIGURACIÓN DE SEGURIDAD
RESERVAS_POR_DIA = 3  # Máximo reservas por día desde una IP
RESERVAS_POR_TELEFONO = 2  # Máximo reservas por teléfono
BLOQUEO_IP_MINUTOS = 30  # Tiempo de bloqueo tras spam
RESERVAS_RECIENTES_HORAS = 24  # Horas para considerar reserva reciente


def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")

    if db_url:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        return psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    else:
        import sqlite3
        conn = sqlite3.connect("barberia.db")
        conn.row_factory = sqlite3.Row
        return conn


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
        estado TEXT DEFAULT 'Pendiente',
        ip_cliente TEXT,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Agregar columna ip_cliente si no existe
    try:
        cursor.execute("ALTER TABLE reservas ADD COLUMN IF NOT EXISTS ip_cliente TEXT")
        cursor.execute("ALTER TABLE reservas ADD COLUMN IF NOT EXISTS fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    except:
        pass  # Ya existe
    
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
    # 🛡️ OBTENER IP DEL CLIENTE
    ip_cliente = request.remote_addr
    if request.headers.get('X-Forwarded-For'):
        ip_cliente = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    
    # 📋 OBTENER DATOS DEL FORMULARIO
    nombre = request.form.get("nombre", "").strip()
    telefono = request.form.get("telefono", "").strip()
    correo = request.form.get("correo", "").strip()
    corte = request.form.get("corte", "").strip()
    fecha = request.form.get("fecha", "").strip()
    horario = request.form.get("horario", "").strip()
    
    # 🛡️ VALIDACIÓN DE CAMPOS VACÍOS Y SANITIZACIÓN
    errores = []
    
    # Validar nombre (solo letras, espacios y tildes)
    if not nombre or len(nombre) < 2:
        errores.append("El nombre es obligatorio")
    elif not re.match(r'^[a-zA-ZáéíóúÁÉÍÓÚñÑ\s]+$', nombre):
        errores.append("El nombre solo puede contener letras")
    
    # Validar teléfono (formato básico chileno)
    if not telefono or len(telefono) < 8:
        errores.append("El teléfono es obligatorio")
    elif not re.match(r'^\+?[0-9\s\-]+$', telefono):
        errores.append("Teléfono inválido")
    
    # Validar correo
    if not correo or "@" not in correo:
        errores.append("El correo es obligatorio")
    elif not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', correo):
        errores.append("Correo electrónico inválido")
    
    # Validar servicio
    servicios_validos = ["Degradado", "Corte Clásico", "Barba"]
    if corte not in servicios_validos:
        errores.append("Selecciona un servicio válido")
    
    # Validar fecha
    if not fecha:
        errores.append("La fecha es obligatoria")
    
    # Validar horario
    horarios_validos = ["09:00", "10:30", "12:00", "13:30", "15:00", "16:30", "18:00"]
    if horario not in horarios_validos:
        errores.append("Selecciona un horario válido")
    
    # Si hay errores de validación, mostrarlos
    if errores:
        for error in errores:
            flash(f"⚠️ {error}")
        return redirect("/")
    
    # 🔒 CONEXIÓN A BASE DE DATOS
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 🛡️ ANTI-SPAM: VERIFICAR RESERVAS RECIENTES DESDE LA MISMA IP
    cursor.execute("""
        SELECT COUNT(*) as total 
        FROM reservas 
        WHERE (ip_cliente = %s OR telefono = %s)
        AND fecha >= NOW() - INTERVAL '%s hours'
    """, (ip_cliente, telefono, RESERVAS_RECIENTES_HORAS))
    
    resultado_ip = cursor.fetchone()
    reservas_recientes = resultado_ip["total"] if resultado_ip else 0
    
    if reservas_recientes >= RESERVAS_POR_DIA:
        cursor.close()
        conn.close()
        flash("⛔ Has realizado demasiadas reservas recently. Intenta más tarde.")
        return redirect("/")
    
    # 🛡️ VERIFICAR LÍMITE POR TELÉFONO
    cursor.execute("""
        SELECT COUNT(*) as total 
        FROM reservas 
        WHERE telefono = %s
        AND fecha >= NOW() - INTERVAL '%s hours'
    """, (telefono, RESERVAS_RECIENTES_HORAS))
    
    resultado_tel = cursor.fetchone()
    reservas_telefono = resultado_tel["total"] if resultado_tel else 0
    
    if reservas_telefono >= RESERVAS_POR_TELEFONO:
        cursor.close()
        conn.close()
        flash("⛔ Este teléfono ya tiene demasiadas reservas. Intenta más tarde.")
        return redirect("/")
    
    # 🔒 VERIFICAR QUE EL HORARIO NO ESTÉ YA OCUPADO
    cursor.execute("""
        SELECT COUNT(*) as total 
        FROM reservas 
        WHERE fecha = %s 
        AND horario = %s 
        AND estado IN ('Pendiente', 'Aceptado')
    """, (fecha, horario))
    
    resultado_horario = cursor.fetchone()
    horario_ocupado = resultado_horario["total"] if resultado_horario else 0
    
    if horario_ocupado > 0:
        cursor.close()
        conn.close()
        flash("⛔ Este horario ya está ocupado. Por favor selecciona otro.")
        return redirect("/")
    
    # 💾 INSERTAR LA RESERVA CON IP
    cursor.execute("""
        INSERT INTO reservas (nombre, telefono, correo, corte, fecha, horario, ip_cliente)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (nombre, telefono, correo, corte, fecha, horario, ip_cliente))
    
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