# INCORPORACIÓN DE RABBITMQ EN ARQUITECTURA DISTRIBUIDA CON TRAEFIK

Partiendo de la arquitectura un proyecto anterior (clientes que envían solicitudes a un servicio de analíticas, y un panel que visualiza los resultados), se desea mejorar la escalabilidad y robustez del sistema incorporando RabbitMQ como sistema de comunicación entre servicios.

## 1. Revisión conceptual:

### 1.1 ¿Qué es RabbitMQ y cuál es su función en una arquitectura distribuida?

RabbitMQ es un broker de mensajes; un broker de mensajes (o message broker) es un intermediario que gestiona la transmisión de mensajes entre servicios o aplicaciones. Su propósito principal es desacoplar el emisor del receptor, permitiendo que cada uno funcione de forma independiente y asincrónica.

En una arquitectura distribuida, donde distintos servicios corren en contenedores separados, RabbitMQ permite que un servicio envíe un mensaje (evento) y que otro lo reciba más tarde, aunque no estén disponibles al mismo tiempo.

Con RabbitMQ el transporte de datos se hace por medio de mensajes (JSON, texto plano, binario, etc.) y no a través de solicitudes HTTP (REST, GraphQL, etc.) como lo hace Traefik. Además, RabbitMQ cuenta con persistencia de datos, en contraste con Traefik que solo enruta y no guarda datos.

Los escenarios comunes de RabbitMQ son la analítica, las colas de trabajo, los eventos y las notificaciones. Las aplicaciones típicas de Traefik son el balanceo de carga, la redirección, la seguridad y la autenticación.

Los protocolos usados por RabbitMQ son: AMQP, MQTT, STOMP

### 1.2 ¿Qué ventajas ofrece frente a llamadas HTTP directas entre servicios?

- **Desacoplamiento:** El productor y consumidor no tienen que conocerse, en cambio con llamadas HTTP, las llamadas directas requieren conocer el endpoint.
- **Tolerancia a fallos:** Los mensajes se pueden encolar si el consumidor cae o no está disponible, en cuanto a las llamadas HTTP, si el servicio destino está caído, el sistema no puede procesar las solicitudes y lanza un error.
- **Escalabilidad:** Se pueden tener múltiples consumidores fácilmente, mientras que con las llamadas HTTP, escalar requiere balanceadores adicionales.
- **Entrega asíncrona:** El productor no espera respuesta inmediata, pero con las llamadas HTTP, se bloquea hasta recibir respuesta o error.
- **Flexibilidad:** Se pueden enrutar mensajes a distintas colas, mientras que las llamadas HTTP son punto a punto.

### 1.3 ¿Qué son las colas, exchanges, publishers y consumers?

- **Publisher (Sender):** Es el emisor del mensaje. Publica información en un exchange de RabbitMQ para que otros servicios puedan procesarla. Ejemplo: servicio-cliente-uno.
- **Consumer (Receiver):** Es quien recibe y procesa el mensaje. Escucha una cola específica y procesa los mensajes que llegan. Ejemplo: servicio-analíticas.
- **Queue (Cola):** Es donde se almacenan temporalmente los mensajes hasta que un consumer los lea.
- **Exchange:** Es quien recibe los mensajes del publisher y decide a qué cola(s) enviarlos, según ciertas reglas (binding).

Ejemplo visual simple:

```
Publisher → [Exchange] → [Queue] → Consumer
```

## 2. Análisis del sistema actual:

### 2.1 ¿Quién produce eventos?

Los servicio-cliente-X (cliente-uno, cliente-dos, etc.) producen los eventos:

- Estos servicios realizan solicitudes HTTP periódicas a servicio-analíticas.
- Envían un header personalizado `X-Client-Name` con su nombre.

### 2.2 ¿Quién consume estos eventos?

El servicio-analiticas consume los eventos:

- Recibe las solicitudes HTTP entrantes.
- Lee el header `X-Client-Name` y actualiza un contador por cliente.

### 2.3 ¿Dónde existen acoplamientos directos que podrían desacoplarse?

- **Acoplamiento directo: cliente y analíticas:** Los clientes dependen de que servicio-analíticas esté disponible en tiempo real. Si el servicio-analíticas está caído, los mensajes se pierden o fallan, es decir, no hay resiliencia ni redundancia. Además, los clientes también deben conocer la URL exacta del backend.
- **Acoplamiento temporal:** El productor (cliente) y el consumidor (analíticas) deben estar activos al mismo tiempo. No hay forma de almacenar mensajes si analíticas está momentáneamente fuera de servicio.
- **Falta de escalabilidad y desacoplamiento:** No se puede escalar el servicio-analiticas fácilmente si muchos clientes lo llaman al mismo tiempo y, no se pueden reenviar o redirigir mensajes fácilmente a otros servicios (por ejemplo, un logger).

## 3. Propuesta de rediseño:

### 3.1 Objetivo del rediseño

Desacoplar la comunicación directa entre los clientes (servicio-cliente-X) y el backend (servicio-analiticas) para lograr un sistema más escalable, tolerante a fallos y flexible, utilizando RabbitMQ como intermediario de mensajes y Traefik como reverce-proxy.

### 3.2 Cambios clave en la arquitectura

- Los servicio-cliente-X ya no llaman directamente al servicio-analíticas, en su lugar, publican mensajes a un exchange y una cola en RabbitMQ.
- El servicio-analíticas ahora actúa como consumer, leyendo mensajes desde una cola y procesándolos.
- El panel-visual continúa consultando el estado actual del servicio de analíticas (sin conectarse a RabbitMQ directamente).

### 3.3 Flujo de mensaje propuesto

```
servicio-cliente → [Exchange: eventos_clientes] → [Queue: cola_analiticas] → servicio-analiticas
                                                                                         |
                                                                      (Almacena mensajes si el servicio está caído)
```

### 3.4 Elementos del diseño

- **Publisher:** `cliente_x` publica eventos en el Exchange `eventos_clientes`.
- **Exchange:** `eventos_clientes`, tipo direct o fanout, enruta a `cola_analiticas`.
- **Queue:** `cola_analiticas` almacena eventos generados por los clientes.
- **Consumer:** `analiticas`, consume los mensajes y actualiza contadores.
- **Panel-visual:** Consulta a `analiticas` mediante HTTP, sin conectarse a RabbitMQ.
- **RabbitMQ (Broker):** `rabbitmq-service` actúa como intermediario de mensajes.
- **Reverse Proxy (Traefik):** `reverse-proxy` enruta el tráfico, administra puertos y panel.
- **Middleware (Traefik):** `panel-visual` usa `strip-panel` para eliminar prefijo `/panel`.

### 3.5 Formato del mensaje

```json
{
  "cliente": "cliente_uno",
  "evento": "click",
  "timestamp": "2025-04-13T12:00:00Z"
}
```

### 3.6 Lógica del consumidor (servicio-analíticas)

1. Se conecta a RabbitMQ (`cola_analiticas`)
2. Por cada mensaje recibido:
   - Extrae nombre del cliente
   - Incrementa contador por cliente
3. Expone `/reporte` para mostrar estadísticas acumuladas

## 4. Estructura del proyecto

```
├── docker-compose.yml
├── .env
├── sender/
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
├── servicio-analiticas/
│   ├── analiticas.py
│   ├── requirements.txt
│   └── Dockerfile
├── panel-visual/
│   ├── panel.py
│   ├── requirements.txt
│   └── Dockerfile
```

## 4. Inicio de implementación:

### 4.1. Tecnologías utilizadas:
- **Docker**: Contenedores para gestionar los servicios.
- **Python & Flask**: Implementación de servicios backend.
- **RabbitMQ**: Sistema de mensajería para desacoplar los servicios.
- **Traefik**: Balanceo de carga y enrutamiento de tráfico HTTP.

### 4.2. Instrucciones:

1. **Clonar el repositorio**:
   ```bash
   git clone https://github.com/DianeyM/Incorporaci-n-de-RabbitMQ-en-Arquitectura-Distribuida-con-Traefik.git
   ```

2. **Iniciar servicios**:
   ```bash
   docker-compose up --build -d
   ```

3. **Acceder a los servicios desde el host local (ejemplo Máquina Virtual o Sistema Base)**:
   - Traefik se puede acceder a través de `http://localhost:8080` para gestionar el enrutamiento.
   - RabbitMQ está disponible en `http://localhost:15672`.

### 4.3 Pruebas de Verificación: Comprobar que todo está bien:

#### 4.3.1 Verificar el estado de los contenedores:
```bash
docker ps
```

#### 4.3.2 Acceder al dashboard de Traefik:
```bash
curl -s http://localhost:8081/api/http/routers | jq
curl http://localhost:8081/dashboard/
```

#### 4.3.3 Acceder al dashboard de RabbitMQ:

##### 4.3.3.1 Ingresar como usuario gest al panel de control:
```bash
curl -u guest:guest http://localhost:15672/api/overview | jq
docker exec -it rabbitmq6 rabbitmqctl list_users
```

##### 4.3.3.2 Para acceder desde el exterior (por ejemplo máquina física sobre la cual está la MV) se debe crear un nuevo usuario con permisos adecuados:
```bash
docker exec -it rabbitmq6 rabbitmqctl add_user dianey 'dianey94*'
docker exec -it rabbitmq6 rabbitmqctl set_permissions -p / dianey ".*" ".*" ".*"
docker exec -it rabbitmq6 rabbitmqctl set_user_tags dianey administrator
docker exec -it rabbitmq6 rabbitmqctl list_users
```

##### 4.3.3.3 Acceder desde el navegador desde el exterior:
```bash
http://IPMáquinaVirtual:15672
```
Usar la credenciales del paso anterior

### 4.3.4 Verificar el acceso a los servicios a través de Traefik:
Accede a la ruta `/panel` desde el host y desde el exterior, respectivamente:
```bash
curl http://localhost/panel
```
Desde el navegador exterior:
```bash
http://IPMáquinaVirtual/panel
```

### 4.3.5 Verificar que el servicio cliente (cliente_x) está publicando mensajes a RabbitMQ:
Enviar un mensaje desde cliente_x:
```bash
curl -X POST http://localhost:5046/send -H "Content-Type: application/json" -d '{"message": "mensaje de prueba"}'
```

Ver logs del cliente:
```bash
docker-compose logs -f cliente_x
```

### 4.3.6 Verificar que el servicio analíticas está exponiendo `/reporte` correctamente:
```bash
curl http://localhost:5064/reporte
```
Desde el exterior: 

```bash
curl http://IPMáquinaVirtual:5064/reporte
```



