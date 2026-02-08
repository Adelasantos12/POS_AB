# Estrategia Offline - Adelé Boutique POS

Este documento describe la arquitectura y el funcionamiento del modo offline del sistema de punto de venta.

## Arquitectura: Offline-First Light

El sistema utiliza una estrategia de "cola de operaciones local" para permitir que la tienda siga operando incluso cuando la conexión a internet es inestable o inexistente.

### 1. Detección de Estado
El frontend monitorea constantemente el estado de la conexión mediante los eventos `online` y `offline` del navegador. Un indicador visual en la parte superior del POS muestra el estado actual (**ONLINE** / **OFFLINE**).

### 2. Cola Local (LocalStorage)
Cuando el sistema está en modo **OFFLINE**, las operaciones críticas (ventas y movimientos) no se envían al servidor inmediatamente. En su lugar:
1. Se genera un `offline_id` único para la operación.
2. Se empaqueta el `payload` con los datos de la venta.
3. Se guarda en una cola dentro del `localStorage` del navegador.
4. Se notifica al usuario que la venta se guardó localmente.

### 3. Sincronización
Cuando la conexión se restablece (evento `online` o clic manual en sincronizar):
1. El frontend envía la cola completa al endpoint `/api/sync/`.
2. El servidor procesa cada operación de forma atómica.
3. Se utiliza el `offline_id` para garantizar la **idempotencia** (evitar duplicados si una operación se envió pero la respuesta no llegó).
4. El frontend limpia de la cola local solo aquellas operaciones que el servidor confirmó como procesadas exitosamente o ya sincronizadas.

## Protocolo de Sincronización

### Endpoint: `POST /api/sync/`

**Request:**
```json
{
  "operaciones": [
    {
      "tipo_op": "venta",
      "offline_id": "123456789-abc",
      "payload": {
        "items": [{"id": 1, "cantidad": 2}],
        "total": 500,
        "metodo": "EFECTIVO",
        "fecha": "2026-02-08T12:00:00Z"
      }
    }
  ]
}
```

**Response:**
```json
{
  "status": "ok",
  "resultados": [
    {
      "offline_id": "123456789-abc",
      "status": "ok",
      "id": 45
    }
  ]
}
```

## Manejo de Conflictos
- **Stock Negativo:** El sistema permite stock teórico negativo para no detener la venta en tienda. Los ajustes se realizan posteriormente en el módulo de inventario.
- **Errores de Validación:** Si una operación falla permanentemente, se mantiene en la cola y se marca con el error recibido para revisión del administrador.
