# TFU UT5 – Refugio de animales

## 1. Arquitectura implementada

La solución utiliza **Event-Driven Architecture (EDA)** para distribuir el procesamiento de las solicitudes de adopción.

```text
Adoptante
   |
   | HTTP / REST / JSON
   v
Nginx ---> API FastAPI (3 réplicas) ---> PostgreSQL
                    |                       |
                    |                       +-- Solicitud
                    |                       +-- OutboxEvent
                    |
             event-publisher <--------------+
                    |
                    | XADD
                    v
             Redis Streams
              /          \
             /            \
 grupo_notificaciones   grupo_auditoria
          |                    |
    Notificaciones          Auditoría
          |
          | SOAP / XML
          v
     Servicio SOAP
          |
          v
      PostgreSQL
```

Responsabilidades:

- **API REST (FastAPI):** autentica al usuario, valida las reglas de negocio y registra la solicitud. En la misma transacción registra un evento en `outbox_events`.
- **Transactional Outbox / `event-publisher`:** busca eventos pendientes en PostgreSQL, los publica en Redis Streams y establece `published_at`.
- **Redis Streams:** distribuye el evento `SolicitudRegistrada` a grupos de consumidores independientes.
- **Notificaciones:** consume el evento, consulta el detalle mediante SOAP, registra el resultado de la notificación y marca el evento como procesado. La notificación es una demostración por logs; no envía un correo real.
- **Auditoría:** consume el mismo evento desde su propio grupo y lo registra en `registros_auditoria`.
- **Servicio SOAP:** expone `ConsultarSolicitud(solicitud_id)` y devuelve un tipo complejo XML publicado en el WSDL.
- **PostgreSQL:** almacena usuarios, animales, hogares, solicitudes, Outbox, eventos procesados y auditoría.

Los grupos `grupo_notificaciones` y `grupo_auditoria` son independientes: ambos reciben cada evento. No comparten el mismo grupo de consumidores.

## 2. Preparar y levantar el proyecto

Abrir PowerShell en la carpeta donde está este `README.md`.

Copiar el archivo de configuración de ejemplo:

```powershell
Copy-Item .env.example .env
```

Construir las imágenes y levantar los servicios, escalando la API a tres instancias:

```powershell
docker compose up --build --scale api=3 -d
```

Abrí la documentación interactiva de la API:

- Swagger: <http://localhost:8000/docs>

Para observar los procesos distribuidos en tiempo real, abrir otra terminal y ejecutar:

```powershell
docker compose logs -f event-publisher notificaciones auditoria soap
```

## 3. Preparar usuarios de prueba

El registro público crea usuarios con rol `ADOPTANTE`. Para las pruebas se necesita un usuario administrativo y uno o más adoptantes.

### 4.1 Registrar el usuario administrador

En Swagger, ejecutar `POST /auth/registro` con:

```json
{
  "email": "admin@example.com",
  "password": "Admin123"
}
```

Para la demostración local, asignar el rol administrador directamente en PostgreSQL:

```powershell
docker compose exec db psql -U tfu5 -d tfu5 -c "UPDATE usuarios SET rol = 'ADMIN' WHERE email = 'admin@example.com';"
```

**Volver a iniciar sesión después de cambiar el rol**

### 4.2 Registrar el adoptante

Ejecutar `POST /auth/registro`:

```json
{
  "email": "adoptante@example.com",
  "password": "Adoptante123"
}
```

### 4.3 Obtener los tokens

Ejecutar `POST /auth/login` para cada usuario.

Copiar `access_token` de cada respuesta.

En Swagger, pulsar **Authorize** y pegar el token correspondiente.

## 5. Crear los datos necesarios

### 5.1 Crear un animal

Autorizar con el token ADMIN y ejecutar `POST /animales`:

```json
{
  "nombre": "Kona",
  "especie": "perro"
}
```

Guardar el `id` que devuelve la API. 

### 5.2 Registrar el hogar del adoptante

Autorizar con el token del adoptante y ejecutar `POST /hogares`:

```json
{
  "responsable": "Adoptante",
  "direccion": "Av. Italia 1234"
}
```

## 6. Caso de uso principal: registrar una solicitud y distribuir el evento

### 6.1 Registrar la solicitud

Con el token del adoptante, ejecutar `POST /adopciones`:

```json
{
  "animal_id": 1,
  "tipo": "definitiva"
}
```

Guardar el `solicitud_id` devuelto. La solicitud y el evento Outbox se guardan en una misma transacción PostgreSQL. La API no espera a que Notificaciones ni Auditoría terminen.

### 6.2 Observar la publicación del evento

En los logs de `event-publisher` debería aparecer el procesamiento de los eventos pendientes (el publicador puede no imprimir una línea por cada evento cuando no hay errores). Consultar el stream:

```powershell
docker compose exec redis redis-cli -n 2 XRANGE solicitudes - +
```

El stream se llama `solicitudes` y se almacena en la base lógica Redis 2.

### 6.3 Comprobar los grupos independientes

```powershell
docker compose exec redis redis-cli -n 2 XINFO GROUPS solicitudes
```

Deberían aparecer los grupos:

- `grupo_notificaciones`
- `grupo_auditoria`

Esto demuestra que cada consumidor mantiene su propio seguimiento de lectura y recibe los eventos de manera independiente.

### 6.4 Comprobar los consumidores

```powershell
docker compose logs --since=5m notificaciones auditoria event-publisher
```

En los logs de Notificaciones debería aparecer una línea similar a:

```text
NOTIFICACION DEMO: solicitud=1 email=adoptante@example.com animal=Kona estado=pendiente
```

Auditoría persiste el evento en PostgreSQL. Comprobar con:

```powershell
docker compose exec db psql -U tfu4 -d tfu4 -c "SELECT id, event_id, event_type, solicitud_id, registrado_en FROM registros_auditoria ORDER BY id DESC LIMIT 10;"
```

### 6.5 Comprobar idempotencia

```powershell
docker compose exec db psql -U tfu4 -d tfu4 -c "SELECT event_id, consumer, processed_at FROM eventos_procesados ORDER BY id DESC LIMIT 20;"
```

Para un mismo `event_id` deberían existir registros independientes para `notificaciones` y `auditoria`. La restricción única `(event_id, consumer)` evita registrar dos veces el mismo evento para el mismo consumidor.

Los consumidores ejecutan `XACK` después de confirmar la transacción en PostgreSQL. Los mensajes pendientes abandonados pueden recuperarse con `XAUTOCLAIM` luego de 60 segundos de inactividad.

### 6.6 Consultar el estado de notificación

Con el token del mismo adoptante que creó la solicitud, ejecutar:

```http
GET /adopciones/{solicitud_id}/estado-notificacion
```

Por ejemplo:

```http
GET /adopciones/1/estado-notificacion
```

Una vez procesada correctamente, la respuesta será similar a:

```json
{
  "solicitud_id": 1,
  "estado_notificacion": "enviada",
  "error": null
}
```

Los estados posibles son `pendiente`, `enviada` y `fallida`. El adoptante solamente puede consultar sus propias solicitudes.

## 7. Demostrar la migración REST a SOAP/XML

En la versión anterior existía la consulta de detalle `GET /adopciones/{solicitud_id}`. En esta entrega esa consulta se migra al servicio SOAP mediante la operación `ConsultarSolicitud(solicitud_id)`. 


### 7.1 Verificar que el WSDL esté disponible

Ejecutar desde PowerShell:

```powershell
docker compose exec notificaciones python -c "import requests; r=requests.get('http://soap:8001/?wsdl'); print('HTTP:', r.status_code); print(r.text[:2500])"
```

Se espera HTTP `200` y un documento WSDL que describe `ConsultarSolicitud` y el tipo complejo de respuesta.

### 7.2 Invocar SOAP desde el consumidor Zeep

Reemplazar `1` por el ID real de la solicitud:

```powershell
docker compose exec notificaciones python -c "from zeep import Client; c=Client('http://soap:8001/?wsdl'); r=c.service.ConsultarSolicitud(1); print({k:getattr(r,k) for k in ['solicitud_id','encontrada','interesado_email','animal_id','animal_nombre','tipo','estado','error']})"
```

Zeep lee el WSDL, construye el mensaje SOAP/XML y transforma la respuesta XML en un objeto Python. El consumidor de Notificaciones utiliza esta misma operación para obtener los datos de la solicitud.

## 8. Demostrar Transactional Outbox ante una caída de Redis

Esta prueba permite observar que la solicitud y el evento quedan guardados en PostgreSQL aunque Redis no esté disponible temporalmente.

1. Detener Redis:

```powershell
docker compose stop redis
```

2. Registrar una solicitud válida con un adoptante que no tenga otra solicitud pendiente y un animal disponible. La API debería seguir pudiendo registrar la solicitud porque el acceso a caché tolera errores de Redis y la solicitud más el evento Outbox se guardan en PostgreSQL.

3. Consultar los últimos eventos Outbox:

```powershell
docker compose exec db psql -U tfu5 -d tfu5 -c "SELECT id, event_id, event_type, published_at FROM outbox_events ORDER BY id DESC LIMIT 10;"
```

El evento nuevo debería tener `published_at` en `NULL` mientras Redis está detenido.

4. Volver a iniciar Redis:

```powershell
docker compose start redis
```

5. Esperar unos segundos y repetir la consulta SQL. El publicador debería enviar el evento y completar `published_at`.

6. Verificar que los consumidores lo hayan procesado con las consultas de `registros_auditoria` y `eventos_procesados` de la sección 6.

Esta prueba demuestra tolerancia a la indisponibilidad temporal de Redis durante la publicación. No significa que el sistema tolere cualquier caída: PostgreSQL sigue siendo necesario para registrar la solicitud.

## 9. Demostrar Circuit Breaker ante una caída de SOAP 

El Circuit Breaker protege la llamada de Notificaciones al servicio SOAP. La configuración de ejemplo abre el circuito después de 3 fallos y permite probar nuevamente luego de 30 segundos.

Para alcanzar el umbral de 3 fallos, preparar tres solicitudes válidas de tres adoptantes diferentes y tres animales disponibles. Cada adoptante debe tener su hogar registrado y no debe tener otra solicitud pendiente.

1. Detener SOAP:

```powershell
docker compose stop soap
```

2. Registrar las tres solicitudes y observar los logs:

```powershell
docker compose logs -f notificaciones
```

3. Después de los fallos, el Circuit Breaker pasa a estado abierto y las llamadas se rechazan temporalmente. Los mensajes no se confirman con `XACK`, por lo que quedan pendientes en Redis. El estado de notificación puede quedar como `fallida` mientras se espera el reintento.

4. Iniciar SOAP nuevamente:

```powershell
docker compose start soap
```

5. Esperar al menos 60 segundos desde el último intento fallido para que `XAUTOCLAIM` pueda recuperar los mensajes pendientes. El tiempo de reapertura del Circuit Breaker es 30 segundos y el umbral de recuperación de mensajes pendientes es 60 segundos.

6. Volver a revisar los logs y el endpoint de estado de notificación. Si el procesamiento termina correctamente, el estado debe pasar a `enviada`.

## 10. Probar que Auditoría es independiente

Se puede detener Auditoría sin detener la API ni Notificaciones:

```powershell
docker compose stop auditoria
```

Registrar una solicitud válida. Notificaciones puede seguir procesándola mientras Auditoría permanece detenida. Luego iniciar Auditoría:

```powershell
docker compose start auditoria
```

El consumidor puede recuperar los mensajes pendientes de su grupo. Verificar que el evento aparezca en `registros_auditoria` y en `eventos_procesados` para el consumidor `auditoria`.

Esta prueba evidencia que el consumidor de auditoría no forma parte del camino síncrono de la API ni depende del proceso de Notificaciones.

