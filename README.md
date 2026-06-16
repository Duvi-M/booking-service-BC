# Booking Service

Backend service pequeño, async y listo para entregar como test técnico de Python Backend.
Permite crear, consultar, listar y cancelar reservas de citas. Cuando se crea una reserva, el
API la guarda como `pending` y dispara una tarea Celery que simula una integración externa:
si la integración sale bien, la reserva pasa a `confirmed` y se registra una notificación mock
en logs JSON; si falla, pasa a `failed`.

## Arquitectura general

- **FastAPI** expone la REST API y valida requests con Pydantic v2.
- **SQLAlchemy 2.0 async** implementa el acceso a datos sin bloquear el event loop.
- **PostgreSQL** es la base de datos de runtime.
- **Alembic** versiona el schema y crea la tabla `bookings`.
- **Redis** funciona como broker/result backend de Celery.
- **Celery** ejecuta el procesamiento asíncrono de confirmación de reservas.
- **pytest + SQLite async** permiten correr tests sin Docker, Postgres ni Redis reales.
- **Docker Compose** levanta API, worker, PostgreSQL y Redis con una sola orden.

## Por qué estas decisiones

**FastAPI** encaja bien para un servicio REST pequeño: validación clara, OpenAPI automático,
soporte async nativo y bajo coste de mantenimiento.

**Celery + Redis** separa el request HTTP del trabajo externo. El API responde rápido y la
confirmación queda delegada al worker. Redis es suficiente como broker para este alcance y
mantiene el compose simple.

**PostgreSQL + SQLAlchemy + Alembic** da una base robusta para producción: transacciones,
tipos sólidos, migraciones reproducibles y una capa ORM async sin SQL raw.

## Idempotencia del worker

La task `bookings.confirm_booking` consulta la reserva antes de hacer cualquier cambio:

- Si el `booking_id` no existe, loggea el caso y termina sin romper.
- Si el estado ya no es `pending`, no llama a la integración externa y no modifica nada.
- Si se ejecuta dos veces sobre la misma reserva, la segunda ejecución observa `confirmed`,
  `failed` o `cancelled` y sale sin duplicar notificaciones ni pisar estado.

## Retry con backoff

La task usa `autoretry_for=(Exception,)`, `retry_backoff=True`, jitter y `max_retries=3`.
Los fallos esperados de la integración simulada no levantan excepción: actualizan la reserva a
`failed`. El retry queda reservado para errores inesperados de infraestructura o ejecución.

## Logging

El servicio usa structured logging JSON con `structlog`. La notificación mock se emite con:

```json
{
  "event": "notification_sent",
  "booking_id": "...",
  "service_type": "...",
  "status": "confirmed"
}
```

## Correr con Docker

```bash
docker compose up --build
```

El API queda disponible en `http://localhost:8000`. El compose espera healthchecks de
PostgreSQL y Redis antes de iniciar API/worker. El API ejecuta `alembic upgrade head` al
arrancar.

## Migraciones

```bash
make migrate
```

Crear una nueva revisión:

```bash
make revision message="add new field"
```

## Tests

Los tests corren sin Docker:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

```bash
pytest
```

Durante tests se usa SQLite async y se mockea el envío de la task Celery para evitar Redis.

## Makefile

```bash
make dev
make test
make lint
make migrate
make revision message="..."
```

## Endpoints

### Crear reserva

```bash
curl -X POST http://localhost:8000/bookings \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Ada Lovelace",
    "datetime": "2026-06-20T10:00:00+00:00",
    "service_type": "consultation"
  }'
```

Respuesta: `201 Created`, reserva con `status=pending`.

### Consultar reserva

```bash
curl http://localhost:8000/bookings/{booking_id}
```

Si no existe, devuelve `404`.

### Listar reservas

```bash
curl "http://localhost:8000/bookings?limit=20&offset=0"
```

Filtrar por estado:

```bash
curl "http://localhost:8000/bookings?status=confirmed&limit=10&offset=0"
```

### Cancelar reserva

```bash
curl -X DELETE http://localhost:8000/bookings/{booking_id}
```

Solo se puede cancelar si está `pending`. Para `confirmed` o `failed`, devuelve `400`.
No hay borrado físico: el estado pasa a `cancelled`.

## Estados

- `pending`
- `confirmed`
- `failed`
- `cancelled`

## Rate limiting

`POST /bookings` incluye un rate limiting simple en memoria por IP. Es deliberadamente pequeño
y suficiente para el test. En producción se movería a Redis para compartir estado entre réplicas.

## Limitaciones conocidas

- La integración externa está simulada con probabilidad configurable de fallo.
- El rate limiting en memoria no es distribuido.
- No hay autenticación/autorización porque no forma parte del alcance.
- No se guarda una tabla de notificaciones; el mock queda registrado en logs estructurados.
