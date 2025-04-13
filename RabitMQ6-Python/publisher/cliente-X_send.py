# Importamos las librerías necesarias para crear la API y conectarnos a RabbitMQ
from flask import Flask, request, jsonify  # Flask para la API y jsonify para la respuesta JSON
import pika  # Librería para conectarse a RabbitMQ
import os  # Librería para acceder a variables de entorno
from retry import retry  # Librería para aplicar reintentos automáticos
from werkzeug.exceptions import BadRequest

# Crear una instancia de la aplicación Flask
app = Flask(__name__)

# Función con reintentos automáticos para conectarse a RabbitMQ y enviar un mensaje
@retry(tries=5, delay=2)  # Reintenta hasta 5 veces, esperando 2 segundos entre cada intento
def send_to_rabbitmq(message):
    # 1. Recupera el nombre del host de RabbitMQ desde la variable de entorno RABBIT_HOST,o usa 'localhost' por defecto si no se encuentra la variable
    rabbit_host = os.getenv("RABBIT_HOST", "localhost")

    # 2. Establece una conexión con RabbitMQ, utilizando el host proporcionado en la variable de entorno
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbit_host))

    # 3. Crea un canal de comunicación con RabbitMQ
    channel = connection.channel()

    # 4. Asegura que la cola 'hello' exista (la crea si no existe)
    channel.queue_declare(queue='hello')

    # 5. Publica el mensaje en la cola 'hello'
    channel.basic_publish(
        exchange='',           # Usamos el exchange por defecto
        routing_key='hello',   # La cola destino del mensaje
        body=message           # El contenido del mensaje
    )

    # 6. Cierra la conexión con RabbitMQ
    connection.close()

# Definir la ruta '/send' para el endpoint que recibe los mensajes y los envía a RabbitMQ
@app.route('/send', methods=['POST'])
def send_message():
    try:
        # Intentar obtener el JSON del cuerpo de la solicitud
        data = request.get_json(force=True)
    except BadRequest:
        return jsonify({"status": "Error", "details": "Cuerpo inválido. Se esperaba JSON con el mensaje a enviar."}), 400

    # Verificar que haya contenido en el cuerpo y que incluya el campo "message"
    if not data or "message" not in data:
        return jsonify({"status": "Error", "details": "Se requiere el campo 'message'"}), 400

    # Obtener el mensaje, y eliminar espacios al inicio y al final
    message = data["message"].strip()

    if not message:
        return jsonify({"status": "Error", "details": "El mensaje no puede estar vacío"}), 400

    try:
        # Advertencia si no se define RABBIT_HOST
        if os.getenv("RABBIT_HOST") is None:
            print("[Advertencia] No se encontró la variable de entorno RABBIT_HOST. Usando 'localhost'.")

        # Enviar mensaje a RabbitMQ con reintentos automáticos (Método al inicio de la clase).
        send_to_rabbitmq(message)

        # Devolver una respuesta JSON indicando que el mensaje fue enviado con éxito
        return jsonify({"status": "Message sent", "message": message}), 200

    except Exception as e:
        # Si ocurre algún error, devolver un mensaje de error en formato JSON
        return jsonify({"status": "Error", "details": str(e)}), 500

# Ejecutar la aplicación Flask en todas las interfaces de red (0.0.0.0) y en el puerto 5000 (Puerto interno)
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)