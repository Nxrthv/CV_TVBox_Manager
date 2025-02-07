from quart import Quart, render_template, request, redirect, url_for, flash, jsonify
import psycopg2, time, subprocess, aiohttp, asyncio, os, logging, requests
from Conexion import conectar_db

app = Quart(__name__)
app.secret_key = os.urandom(24)

# Ruta principal
@app.route('/')
async def index():
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute('''
            WITH UltimasVerificaciones AS (
                SELECT 
                    url_id, 
                    exito, 
                    fecha_verificacion,
                    ROW_NUMBER() OVER (PARTITION BY url_id ORDER BY fecha_verificacion DESC) AS rn
                FROM 
                    verificaciones
            )

            SELECT 
                u.id, 
                u.url, 
                u.nombre, 
                COALESCE(v.fecha_verificacion, NULL) AS fecha_verificacion,
                COALESCE(v.exito, FALSE) AS exito,
                u.ip_tvbox
            FROM 
                urls u
            LEFT JOIN 
                UltimasVerificaciones v ON u.id = v.url_id AND v.rn = 1
            ORDER BY
                u.nombre ASC;
        ''')
        urls = cursor.fetchall()
    except Exception as e:
        print(f"Error al acceder a la base de datos: {e}")
        return "Error al acceder a la base de datos", 500
    finally:
        cursor.close()
        conn.close()
    
    return await render_template('Index.html', urls=urls)

# Agregar URL
@app.route('/agregar', methods=['POST'])
async def agregar_url():
    
    form_data = await request.form
    nombre = form_data.get('nombre', '').upper()
    url = form_data.get('url', '')
    ip_tvbox = form_data.get('ip', '')

    # Validar campos
    if not nombre or not url or not ip_tvbox:
        flash('⚠️ Por favor, completa todos los campos.', 'error')
        return redirect(url_for('index'))
    
    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO urls (nombre, url, ip_tvbox) VALUES (%s, %s, %s)',
            (nombre, url, ip_tvbox)
        )
        conn.commit()
        await flash('✅ URL agregada correctamente.', 'success')

    except psycopg2.IntegrityError:
        conn.rollback()
        await flash('⚠️ La URL ya está registrada.', 'error')

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('index'))

# Eliminar URL
@app.route('/eliminar/<int:id>', methods=['POST'])
async def eliminar_url(id):
    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM verificaciones WHERE url_id = %s', (id,))
        
        cursor.execute('DELETE FROM urls WHERE id = %s', (id,))
        
        if cursor.rowcount == 0:
            await flash('⚠️ No se encontró la URL para eliminar.', 'error')
        else:
            conn.commit()
            await flash('URL eliminada correctamente.', 'success')
    except psycopg2.Error as e:
        conn.rollback()
        await flash(f'⚠️ Ocurrió un error al eliminar la URL: {str(e)}', 'error')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('index'))

#Verificar Errores
@app.route('/verificar_errores', methods=['POST'])
async def verificar_errores():
    return None

#Verificar todas las URLs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def verificar_stream(url):
    try:
        # Hacer la solicitud con stream=True para evitar que se cuelgue
        with requests.get(url, stream=True, timeout=5) as response:
            if response.status_code == 200:
                # Leer solo un pequeño fragmento para verificar que el stream está activo
                chunk = next(response.iter_content(1024), None)
                if chunk:
                    # Verificar si es un stream M3U8
                    if url.endswith('.m3u8') and not response.text.startswith('#EXTM3U'):
                        return response.status_code, time.time(), True  # No es un M3U8 válido
                    return response.status_code, time.time(), True  # Stream activo
                else:
                    return response.status_code, time.time(), False  # Stream no activo
            else:
                return response.status_code, time.time(), False  # Stream no activo
    except requests.Timeout:
        logging.error(f"⚠️ Timeout al intentar acceder a {url}")
        return None, None, False  # Timeout
    except requests.RequestException as e:
        logging.error(f'❌ Error al verificar el stream {url}: {e}')
        return None, None, False

@app.route('/verificar', methods=['POST'])
async def verificar_todas():
    conn = None
    cursor = None
    try:
        conn = conectar_db()
        if conn is None:
            flash('Error al conectar a la base de datos.', 'error')
            return redirect(url_for('index'))

        cursor = conn.cursor()
        cursor.execute('SELECT id, url FROM urls')
        urls = cursor.fetchall()

        resultados = []
        for url_id, url in urls:
            logging.info(f'Verificando URL: {url}')
            codigo, tiempo, exito = verificar_stream(url)
            resultados.append((url_id, codigo, tiempo, exito))

        print(f"Resultados de verificación: {resultados}")

        for url_id, codigo, tiempo, exito in resultados:
            print(f"Preparando inserción: url_id={url_id}, codigo={codigo}, tiempo={tiempo}, exito={exito}")
            try:
                if codigo is not None:
                    cursor.execute(''' 
                        INSERT INTO verificaciones (url_id, fecha_verificacion, codigo_respuesta, tiempo_respuesta, exito) 
                        VALUES (%s, NOW(), %s, %s::interval, %s)
                    ''', (url_id, codigo, f'{tiempo} seconds', exito))
                else:
                    cursor.execute(''' 
                        INSERT INTO verificaciones (url_id, fecha_verificacion, codigo_respuesta, tiempo_respuesta, exito) 
                        VALUES (%s, NOW(), %s, %s::interval, %s)
                    ''', (url_id, -1, '0 seconds', False))
            except Exception as e:
                print(f"❌ Error al insertar en la tabla verificaciones: {e}")

        conn.commit()
        flash('✅ Todas las URLs han sido verificadas.', 'success')

    except Exception as e:
        print(f"❌ Error crítico en la verificación: {e}")
        flash('Error crítico en la verificación de URLs.', 'error')

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        print("🔴 Conexión a la base de datos cerrada.")

    return redirect(url_for('index'))

#Actualizar IP
@app.route('/actualizar_ip', methods=['POST'])
async def actualizar_ip():
    form_data = await request.form
    url_id = form_data.get('url_id')
    ip = form_data.get('ip')

    if not ip:
        await flash("⚠️ No ingresaste una IP.", "error")
        return redirect(url_for('index'))

    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'UPDATE urls SET ip_tvbox = %s WHERE id = %s', (ip, url_id)
        )
        if cursor.rowcount == 0:
            await flash("⚠️ No se encontró la URL para actualizar.", "error")
        else:
            conn.commit()
            await flash("✅ IP guardada correctamente.", "success")

    except Exception as e:
        conn.rollback()
        await flash(f"⚠️ Error al guardar la IP: {e}", "error")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('index'))

#Abrir VLC
def abrir_vlc(url): 
    subprocess.Popen(["C:\\Program Files\\VideoLAN\\VLC\\vlc.exe", url])

@app.route('/abrir_vlc')
async def abrir_vlc_route():
    url = request.args.get('url')
    if url:
        abrir_vlc(url)
        return None
    else:
        return "No se proporcionó una URL", 400 
    
#Coneccion ADB
@app.route('/conectar_adb', methods=['POST'])
def conectar_adb():
    data = request.get_json()
    ip = data.get('ip')

    try:
        adb_command = f"adb connect {ip}"
        adb_result = subprocess.run(adb_command, shell=True, capture_output=True, text=True)

        if "connected" in adb_result.stdout:
            scrcpy_command = f"scrcpy -s {ip}"
            subprocess.Popen(scrcpy_command, shell=True)
            return jsonify({"message": f"Conectado a {ip} y lanzando scrcpy."}), 200
        else:
            return jsonify({"message": f"No se pudo conectar a {ip}."}), 400
    except Exception as e:
        return jsonify({"message": f"Error al conectar o lanzar scrcpy: {str(e)}"}), 500
    
#Desconectar ADB
@app.route('/desconectar_adb', methods=['POST'])
def desconectar_adb():
    data = request.get_json()
    ip = data.get('ip')

    if not ip:
        return jsonify({"message": "⚠️ No se proporcionó una IP."}), 400

    resultado = subprocess.run(["adb", "disconnect"], capture_output=True, text=True)

    if "disconnected" in resultado.stdout:
        return jsonify({"message": f"🔴 Desconectado de {ip}."})
    else:
        return jsonify({"message": f"⚠️ Error al desconectar: {resultado.stderr}"}), 500
    
#Consultar estado de Coneccion
@app.route('/estado_adb', methods=['GET'])
def estado_adb():
    resultado = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    dispositivos = resultado.stdout.splitlines()[1:]

    ips_conectadas = [
        linea.split("\t")[0] for linea in dispositivos if "device" in linea
    ]

    return jsonify(ips_conectadas)

#Interfaz de Errores
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from flask import make_response

#Registrar Errores
@app.route('/errores')
async def listar_errores():
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT e.id, u.nombre, e.fecha_error, e.tipo_error
        FROM errores e
        JOIN urls u ON e.url_id = u.id
        WHERE e.id IN (
            SELECT MAX(id)
            FROM errores
            GROUP BY url_id
        )
        ORDER BY e.fecha_error DESC;
    ''')
    errores = cursor.fetchall()

    conn.close()
    return await render_template('Errores.html', errores=errores)

#Informe de errores
@app.route('/informe/errores_pdf')
def generar_informe_pdf():
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT e.id, u.nombre, e.fecha_error, e.tipo_error
        FROM errores e
        JOIN urls u ON e.url_id = u.id
        WHERE e.id IN (
            SELECT MAX(id)
            FROM errores
            GROUP BY url_id
        )
        ORDER BY e.fecha_error DESC;
    ''')
    errores = cursor.fetchall()

    conn.close()

    # Crear un archivo PDF
    response = make_response()
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=reporte_errores.pdf'

    p = canvas.Canvas(response.stream, pagesize=letter)
    p.drawString(100, 750, "Reporte de Errores")
    y = 730
    for id_error, nombre, fecha_error, tipo_error in errores:
        p.drawString(100, y, f"Canal: {nombre}")
        p.drawString(100, y - 15, f"Fecha: {fecha_error.strftime('%Y-%m-%d %H:%M:%S')}")
        p.drawString(100, y - 30, f"Error: {tipo_error}")
        y -= 50
    p.showPage()
    p.save()

    return response

import pandas as pd
from flask import send_file

@app.route('/informe/errores_excel')
def generar_informe_excel():
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT e.id, u.nombre, e.fecha_error, e.tipo_error
        FROM errores e
        JOIN urls u ON e.url_id = u.id
        WHERE e.id IN (
            SELECT MAX(id)
            FROM errores
            GROUP BY url_id
        )
        ORDER BY e.fecha_error DESC;
    ''')
    errores = cursor.fetchall()

    conn.close()

    # Crear un DataFrame de pandas
    df = pd.DataFrame(errores, columns=['ID', 'Canal', 'Fecha del Error', 'Tipo de Error'])

    # Guardar en un archivo Excel
    df.to_excel('reporte_errores.xlsx', index=False)

    return send_file('reporte_errores.xlsx', as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)