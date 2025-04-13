#Servicio analíticas
from flask import Flask, jsonify
import pika  # Importa la librería pika, que es utilizada para conectarse a RabbitMQ
import os    # Para acceder a las variables de entorno
import sys   # Para poder manejar la salida del programa
import threading
from retry import retry  # Librería para aplicar reintentos automáticos

# Lista donde se guardarán los mensajes recibidos
mensajes = []

# Crear una instancia de la aplicación Flask (Para exponer /reporte)
app = Flask(__name__)

@app.route('/reporte')
def reporte():
    return jsonify({"mensajes": mensajes})

# Función con reintentos automáticos para conectarse a RabbitMQ
@retry(tries=5, delay=2)  # Reintenta hasta 5 veces, esperando 2 segundos entre cada intento
def connect_to_rabbitmq():
    # Recupera el nombre del host de RabbitMQ desde la variable de entorno RABBIT_HOST, o usa 'localhost' por defecto si no se encuentra la variable
    rabbit_host = os.getenv("RABBIT_HOST", "localhost")

    # Establece una conexión con RabbitMQ, utilizando el host proporcionado en la variable de entorno
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbit_host))
    return connection

# Esta función se llama cada vez que se recibe un mensaje de la cola
def callback(ch, method, properties, body):
    mensaje = body.decode()
    # Imprime el contenido del mensaje recibido. 'body' es en bytes, por lo que se decodifica a string.
    print(f" [x] Received {mensaje}")
    #Añade el mensaje al listado de mensajes
    mensajes.append(mensaje)

# Función principal que establece la conexión y empieza a consumir mensajes
def start_consumer():
    try:
        # 1. Conectarse a RabbitMQ con reintentos mediante la función creado en esta clase connect_to_rabbitmq()
        connection = connect_to_rabbitmq()
        
        # 2. Crea un canal de comunicación sobre la conexión establecida
        channel = connection.channel()

        # 3. Declara la cola 'hello'. Si la cola ya existe, no hace nada. Esto asegura que la cola está disponible para consumir mensajes
        channel.queue_declare(queue='hello')

        # 4. Comienza a consumir mensajes de la cola 'hello'. Cada vez que llegue un mensaje, se ejecutará la función 'callback', función creado en esta clase
        #    - 'auto_ack=True' significa que el mensaje será reconocido automáticamente al ser recibido.
        channel.basic_consume(
            queue='hello',
            auto_ack=True,
            on_message_callback=callback
        )

        # 5. Imprime un mensaje indicando que el consumidor está esperando mensajes
        print(' [*] Waiting for messages in servicio analiticas. To exit press CTRL+C')

        # 6. Empieza el ciclo de espera y consumo de mensajes
        #    Esto es un ciclo infinito que espera y procesa mensajes.
        channel.start_consuming() 

    except pika.exceptions.AMQPConnectionError as connection_error:
        # 7. Maneja el caso en el que no se pueda establecer una conexión con RabbitMQ
        #    Si no se puede conectar, imprime el error y sale del programa
        print(f" [!] Error al conectar con RabbitMQ: {connection_error}")
        sys.exit(1)  # Sale del programa con un código de error 1

    except KeyboardInterrupt:
        # 8. Captura una interrupción del teclado (Ctrl+C) para salir del programa de manera controlada
        print(' [!] Interrumpido por el usuario')
        try:
            sys.exit(0)  # Intenta salir limpiamente
        except SystemExit:
            os._exit(0)  # En caso de que sys.exit no funcione, forzamos la salida

# Este bloque asegura que la función main() solo se ejecute cuando este archivo se ejecute directamente, no cuando se importe como módulo
if __name__ == '__main__':
    # Creamos un hilo (thread) que ejecutará la función start_consumer
    # Esto permite que el consumidor de RabbitMQ corra en paralelo con la aplicación Flask (que procesa mensajes entrantes.)
    #Flask, por defecto, bloquea el hilo principal cuando se ejecuta app.run(...). Entonces, si ejecutaras el consumidor antes o después 
    # de app.run(...), uno bloquearía al otro y la app no funcionaría como SERVICIO DOBLE.
    # daemon=True indica que este hilo es "secundario" o "de fondo", si la app principal (Flask) se cierra, este hilo se cerrará automáticamente.
    consumer_thread = threading.Thread(target=start_consumer, daemon=True)
    
    # Iniciamos el hilo del consumidor,este hilo escuchará la cola de mensajes y guardará los datos recibidos
    consumer_thread.start()
    
    # Iniciamos la aplicación Flask en el hilo principal
    # Esto levanta un servidor web que expone el endpoint /reporte en el puerto 5000
    app.run(host='0.0.0.0', port=5000)
