import requests

url = "http://headends.ottvideostream.cloud:8933/CORAZON/mpegts"

def verificar_stream(url):
    try:
        with requests.get(url, stream=True, timeout=5) as response:
            if response.status_code == 200:
                # Leer solo un pequeño fragmento para verificar que el stream está activo
                chunk = next(response.iter_content(1024), None)
                if chunk:
                    return True  # Stream activo
                else:
                    return False  # Stream no activo
            else:
                return False  # Stream no activo
    except requests.Timeout:
        print(f"⚠️ Timeout al intentar acceder a {url}")
        return False  # Timeout
    except requests.RequestException as e:
        print(f"❌ Error al acceder a {url}: {e}")
        return False  # Otro error

# Probar la función
if verificar_stream(url):
    print("El stream está activo.")
else:
    print("El stream no está activo.")