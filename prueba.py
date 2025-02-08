# import subprocess
# import json

# def subir_volumen(ip_tvbox, puerto):
#     # Comando para subir el volumen
#     comando = f"adb -s {ip_tvbox}:{puerto} shell input keyevent 24"

#     try:
#         subprocess.run(comando, shell=True, check=True)
#         mensaje = "Se subió el volumen correctamente"
#     except subprocess.CalledProcessError as e:
#         mensaje = f"Error al subir el volumen: {e}"

#     return json.dumps({"mensaje": mensaje})

# ip_tvbox = "192.168.90.66"
# puerto = "5555"

# resultado = subir_volumen(ip_tvbox, puerto)
# print(resultado)

# def bajar_volumen(ip_tvbox, puerto):
#     # Comando para bajar el volumen
#     comando = f"adb -s {ip_tvbox}:{puerto} shell input keyevent 25"

#     try:
#         subprocess.run(comando, shell=True, check=True)
#         mensaje = "Se bajo el volumen correctamente"
#     except subprocess.CalledProcessError as e:
#         mensaje = f"Error al bajar el volumen: {e}"

#     return json.dumps({"mensaje": mensaje})

# ip_tvbox = "192.168.90.66"
# puerto = "5555"

# resultado = subir_volumen(ip_tvbox, puerto)
# print(resultado)

import subprocess
import json

def cambiar_url_bsplayer(ip_tvbox, puerto, nueva_url):
    # Comando para cambiar la URL en BS Player Pro
    comando = f'adb -s {ip_tvbox}:{puerto} shell am start -n com.bsplayer.pro/.MainActivity -e url "{nueva_url}"'

    try:
        # Ejecutar el comando
        subprocess.run(comando, shell=True, check=True)
        mensaje = "URL cambiada correctamente en BS Player Pro"
    except subprocess.CalledProcessError as e:
        mensaje = f"Error al cambiar la URL: {e}"

    # Devolver el mensaje en formato JSON
    return json.dumps({"mensaje": mensaje})

# Ejemplo de uso
ip_tvbox = "192.168.90.55"      
puerto = "5555"
nueva_url = "http://181.119.107.201:5054/play/a0dt/index.m3u8"  # Reemplaza con la nueva URL

resultado = cambiar_url_bsplayer(ip_tvbox, puerto, nueva_url)
print(resultado)