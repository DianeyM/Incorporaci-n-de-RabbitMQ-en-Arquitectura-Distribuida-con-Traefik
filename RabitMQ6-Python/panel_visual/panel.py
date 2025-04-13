from flask import Flask, render_template_string
import requests
import threading
import time

# Creamos la app Flask
app = Flask(__name__)

# Lista global donde se almacenarán los mensajes recuperados de servicio-analiticas
mensajes = []

# Esta función hace la petición GET a servicio-analiticas y maneja los reintentos
def fetch_reporte():
    MAX_RETRIES = 5
    RETRY_INTERVAL = 10  # Espera de 10 segundos entre intentos

    for retries in range(MAX_RETRIES):
        try:
            # Hacemos una petición GET al servicio-analiticas
            response = requests.get('http://analiticas:5000/reporte', timeout=5)

            if response.status_code == 200:
                # Si la respuesta es exitosa, devolvemos los datos
                data = response.json()
                if 'mensajes' in data and data['mensajes']:
                    return data['mensajes']
                else:
                    print(f"[Panel] No hay mensajes, esperando más...")
            else:
                print(f"[Panel] Error en respuesta /reporte: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"[Panel] Error al consultar /reporte: {e}")
        
        # Espera antes de intentar nuevamente
        print(f"[Panel] Reintentando... ({retries + 1}/{MAX_RETRIES})")
        time.sleep(RETRY_INTERVAL)

    raise Exception("No se pudo obtener el reporte de servicio-analiticas después de varios intentos.")

# Esta función se ejecutará en segundo plano y cada 5 segundos consultará el endpoint /reporte
def actualizar_mensajes():
    while True:
        try:
            # Hacemos la petición a servicio-analiticas
            nuevos_mensajes = fetch_reporte()
            
            # Si tenemos nuevos mensajes, actualizamos la lista global
            if nuevos_mensajes:
                mensajes.clear()  # Limpiamos la lista antes de actualizar
                mensajes.extend(nuevos_mensajes)  # Añadimos los nuevos mensajes
                print('[Panel] Mensajes actuales:', mensajes)
        except Exception as e:
            print(f"[Panel] No se pudo actualizar los mensajes: {e}")

        # Esperamos 5 segundos antes de intentar nuevamente
        time.sleep(5)

# Ruta principal del panel: muestra los mensajes en una lista HTML
@app.route('/')
def panel():
    html = """
    <html>
      <head><title>Panel Visual</title></head>
      <body>
        <h1>Mensajes del sistema</h1>
        <ul>
          {% for m in mensajes %}
            <li>{{ m }}</li>
          {% endfor %}
        </ul>
      </body>
    </html>
    """
    # Renderiza el HTML pasando la lista de mensajes como contexto
    return render_template_string(html, mensajes=mensajes)

# Si se ejecuta este script directamente:
if __name__ == '__main__':
    # Creamos un hilo que ejecuta actualizar_mensajes() en segundo plano
    hilo = threading.Thread(target=actualizar_mensajes, daemon=True)
    hilo.start()

    # Arrancamos el servidor Flask accesible en toda la red del contenedor
    app.run(host='0.0.0.0', port=5000)
