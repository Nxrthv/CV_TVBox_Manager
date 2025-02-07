from quart import Quart, render_template, request, redirect, url_for, flash, render_template_string, jsonify
import psycopg2, time , subprocess, aiohttp, asyncio, os
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
            SELECT 
                u.id, 
                u.url, 
                u.intervalo_verificacion, 
                u.nombre, 
                COALESCE(v.fecha_verificacion) AS fecha_verificacion,
                COALESCE(v.exito, FALSE) AS exito,
                u.ip_tvbox
            FROM 
                urls u
            LEFT JOIN 
                (SELECT url_id, exito, fecha_verificacion  -- Asegúrate de incluir fecha_verificacion aquí
                FROM verificaciones v1
                WHERE fecha_verificacion = (
                    SELECT MAX(fecha_verificacion) 
                    FROM verificaciones v2 
                    WHERE v1.url_id = v2.url_id
                )) v
            ON 
                u.id = v.url_id
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
    
    return await render_template('index.html', urls=urls)

#Verificar todas las URLs
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

        print(f"🔍 Verificando {len(urls)} URLs...")

        resultados = await verificar_todas_urls(urls)
        print(f"Resultados de verificación: {resultados}")

        for url_id, codigo, tiempo, exito in resultados:
            try:
                if codigo is not None:
                    cursor.execute(''' 
                        INSERT INTO verificaciones (url_id, fecha_verificacion, codigo_respuesta, tiempo_respuesta, exito) 
                        VALUES (%s, NOW(), %s, %s, %s)
                    ''', (url_id, codigo, tiempo, exito))
                else:
                    cursor.execute('''
                        INSERT INTO errores (url_id, fecha_error, tipo_error)
                        VALUES (%s, NOW(), %s)
                    ''', (url_id, "Error al verificar la URL"))
            except Exception as insert_error:
                print(f"❌ Error al insertar en la tabla de verificaciones: {insert_error}")
                conn.rollback()  # Deshacer cualquier cambio si hay un error

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

async def verificar_url(url, url_id):
    headers = {
        "User -Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
    }
    try:
        async with aiohttp.ClientSession() as session:
            inicio = time.time()
            async with session.get(url, headers=headers, timeout=5) as respuesta:
                tiempo_respuesta = time.time() - inicio
                codigo = respuesta.status
                exito = (codigo == 200)
                print(f"✅ URL verificada: {url} - Código {codigo}, Tiempo {tiempo_respuesta:.2f}s")
                return (url_id, codigo, tiempo_respuesta, exito)
    except asyncio.TimeoutError:
        print(f"⏳ Timeout al verificar la URL: {url}")
        return (url_id, None, None, False)
    except Exception as e:
        print(f"❌ Error al verificar la URL {url}: {e}")
        return (url_id, None, None, False)
    
async def verificar_todas_urls(urls):
    tasks = []
    for url_id, url in urls:
        tasks.append(verificar_url(url, url_id))
    return await asyncio.gather(*tasks)

#Registrar Errores
def registrar_error(url_id, tipo_error):
    conn = conectar_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO errores (url_id, fecha_error, tipo_error)
            VALUES (%s, NOW(), %s)
        ''', (url_id, tipo_error))
        conn.commit()
        print(f"⚠️ Error registrado en BD: {tipo_error}")
    except Exception as db_error:
        print(f"❌ Error al registrar en la tabla errores: {db_error}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

# Agregar URL
@app.route('/agregar', methods=['POST'])
def agregar_url():
    if request.method == 'POST':
        nombre = request.form['nombre'].upper()
        url = request.form['url']
        ip_tvbox = request.form['ip']  # Capturar la IP ingresada
        intervalo = request.form['intervalo']

        if not nombre or not url or not intervalo or not ip_tvbox:
            flash('⚠️ Por favor, completa todos los campos.', 'error')
            return redirect(url_for('index'))
        
        conn = conectar_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO urls (nombre, url, intervalo_verificacion, ip_tvbox) VALUES (%s, %s, %s, %s)',
                (nombre, url, intervalo, ip_tvbox)
            )
            conn.commit()
            flash('✅ URL agregada correctamente.', 'success')

        except psycopg2.IntegrityError:
            conn.rollback()
            flash('⚠️ La URL ya está registrada.', 'error')

        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('index'))

#Actualizar IP
@app.route('/actualizar_ip', methods=['POST'])
def actualizar_ip():
    url_id = request.form['url_id']
    ip = request.form['ip']

    if not ip:
        flash("⚠️ No ingresaste una IP.", "error")
        return redirect(url_for('index'))

    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'UPDATE urls SET ip_tvbox = %s WHERE id = %s', (ip, url_id)
        )
        conn.commit()
        flash("✅ IP guardada correctamente.", "success")

    except Exception as e:
        conn.rollback()
        flash(f"⚠️ Error al guardar la IP: {e}", "error")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('index'))

#Descargar m3u
# @app.route('/descargar_m3u')
# def descargar_m3u():
#     url = request.args.get('url')
#     contenido = f"#EXTM3U\n#EXTINF:-1,Stream\n{url}"
#     return response(contenido, mimetype="audio/x-mpegurl", headers={"Content-Disposition": "attachment; filename=stream.m3u"})

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

# Eliminar URL
@app.route('/eliminar/<int:id>', methods=['POST'])
def eliminar_url(id):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM urls WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    flash('URL eliminada correctamente.', 'success')
    return redirect(url_for('index'))

# Verifica solo URLs con error o sin registro
@app.route('/verificar_errores', methods=['POST'])
async def verificar_errores():
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT u.id, u.url
        FROM urls u
        LEFT JOIN verificaciones v ON u.id = v.url_id
        WHERE v.url_id IS NULL OR v.exito = FALSE
    ''')
    urls_con_error = cursor.fetchall()

    urls_dict = {url_id: url for url_id, url in urls_con_error}

    # Ejecutar verificación en paralelo
    resultados = verificar_url(urls_dict.values())

    data = []
    for url_id, url in urls_dict.items():
        codigo, tiempo, exito = resultados.get(url, (None, None, False))
        data.append((url_id, codigo, tiempo, exito))

    if data:
        cursor.executemany('''
            INSERT INTO verificaciones (url_id, fecha_verificacion, codigo_respuesta, tiempo_respuesta, exito)
            VALUES (%s, NOW(), %s, %s, %s)
        ''', data)
        conn.commit()

    conn.close()
    flash('URLs con error verificadas correctamente.', 'success')
    return redirect(url_for('index'))

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

# def registrar_error(url_id, tipo_error):
#     conn = conectar_db()
#     cursor = conn.cursor()

#     cursor.execute('''
#         INSERT INTO errores (url_id, tipo_error)
#         VALUES (%s, %s)
#     ''', (url_id, tipo_error))

#     conn.commit()
#     conn.close()

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