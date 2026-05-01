# Compliance LFPDPPP 2025 — Inventario y procedimientos

> **Documento ejecutivo de cumplimiento.** Para uso interno y para
> defenderse ante la **Secretaría Anticorrupción y Buen Gobierno**
> en caso de auditoría o reclamación.

**Versión:** 1 — generado 2026-05-01.
**Marco normativo:** Ley Federal de Protección de Datos Personales en
Posesión de los Particulares (LFPDPPP) reformada en marzo 2025.

---

## 1. Inventario de datos personales tratados

| Tabla | Columna | Origen | Base legal | Finalidad | Retención (meses) |
|---|---|---|---|---|---|
| `vendedores` | `nombre`, `email`, `telefono` | Empleado | Relación laboral con Intergranel | Identificación operativa | 60 |
| `usuarios` | `nombre`, `email` | Empleado | Relación laboral | Identificación de usuarios del sistema | 60 |
| `cadenas` | `contacto_central_*` | Manual | Interés legítimo B2B | Contacto comercial central | 36 |
| `establecimientos` | `nombre`, `razon_social`, `rfc` | DENUE INEGI / Manual | Fuente de acceso público + interés legítimo B2B | Identificación de prospecto comercial | 60 |
| `establecimientos` | `telefono`, `whatsapp`, `email` | DENUE / Google Places / Manual | Fuente de acceso público + consentimiento | Contacto comercial inicial | 36 |
| `establecimientos` | `contacto_*` | Manual (vendedor en visita) | Consentimiento del prospecto | Trato personalizado | 36 |
| `enriquecimiento_google` | `google_phone` | Google Places API | Fuente pública (API oficial) | Contacto comercial verificado | 12 |
| `interacciones` | `contacto_persona` | Manual | Consentimiento implícito por interacción | Trazabilidad comercial | 36 |
| `sat_lista_69b` | `rfc`, `razon_social` | DOF (publicación oficial SAT) | Información pública oficial | Cruce de riesgo fiscal | 24 |

**Total: 21 columnas de PII catalogadas.** Ver tabla `_columnas_pii` en DB
para lista actualizada.

## 2. Bases legales aplicadas

Conforme al Art. 16 de la LFPDPPP, todo tratamiento se justifica con una de
estas bases:

| Base legal | Aplicación en CRM-Granos-MX |
|---|---|
| **Fuente de acceso público** | DENUE INEGI, SAT 69-B, Censo, ENIGH, SIAP, CONEVAL, Google Places API |
| **Interés legítimo comercial B2B** | Contacto inicial a establecimientos comerciales con datos públicos |
| **Consentimiento** | Captura manual por vendedor en visita, formularios web (cuando exista) |
| **Relación laboral** | Datos de empleados (vendedores, usuarios) |

## 3. Finalidades declaradas

### 3.1 Finalidades primarias (sin consentimiento adicional)
1. Identificación de prospectos comerciales del sector granos.
2. Scoring interno y segmentación A/B/C.
3. Asignación a vendedor por zona geográfica.
4. Verificación de cumplimiento fiscal (cruce 69-B).
5. Contacto comercial para propuestas.
6. Bitácora de interacciones comerciales.

### 3.2 Finalidades secundarias (requieren consentimiento)
1. Análisis de mercado agregado y anonimizado (futuro).
2. Compartir información con asociados estratégicos (futuro, requiere
   contrato y consentimiento explícito).

## 4. Mecanismos de ejercicio de derechos ARCO

### 4.1 Receptor
- **Email principal:** datos@intergranel.mx (pendiente de configurar).
- **Plazo legal de respuesta:** 20 días hábiles (Art. 32 LFPDPPP).
- **Plazo de ejecución tras respuesta procedente:** 15 días hábiles.

### 4.2 Workflow técnico

Implementado en `src/compliance/arco.py`:

```
1. Recepción → registrar_solicitud_arco()
   - Genera folio único (ARCO-YYYYMMDD-NNN)
   - Estatus: 'recibida'
   - Calcula fecha_limite_respuesta = +20 días hábiles
   - Compliance log automático

2. Validación de identidad → validar_identificacion()
   - Confirma que el solicitante es el titular
   - Estatus: 'en_proceso'

3. Procesamiento → preparar_respuesta()
   - Acceso: genera CSV con todos los datos del solicitante
   - Rectificación: actualiza campos
   - Cancelación: marca registros para borrado
   - Oposición: agrega flag de no-contactar

4. Respuesta → responder_solicitud()
   - Envía respuesta por mismo medio
   - Estatus: 'respondida' / 'no_procedente'
   - Compliance log automático

5. Vencimiento → check_vencidas() (job diario)
   - Marca como 'vencida' las que excedan 20 días hábiles sin respuesta
   - Genera alerta al equipo legal
```

### 4.3 Tabla de rastreo

`arco_solicitudes` (ver migración `e77ccdc77b2c`):

- `folio` único auditable
- `estatus` (recibida → en_proceso → respondida / no_procedente / vencida)
- `fecha_recepcion`, `fecha_limite_respuesta`, `fecha_respuesta`
- `usuario_responsable_id` para accountability
- `respuesta` y `documentos_anexos` (JSONB)

## 5. Plan de retención y eliminación

### Retención por defecto
- Datos comerciales activos (prospecto, contactado, visitado): retención
  indefinida mientras dure la relación comercial.
- Datos de prospectos sin actividad por 24 meses: revisión y posible
  cancelación o anonimización.
- Datos cancelados por solicitud ARCO: eliminación efectiva en ≤15 días
  hábiles tras respuesta procedente.

### Eliminación segura
1. Cancelación lógica: `establecimientos.estado_pipeline = 'descartado'` +
   blanqueo de campos PII (telefono, email, contacto_*).
2. Eliminación física: para registros con cancelación ARCO procedente, se
   ejecuta `DELETE` con `compliance_log` previo.
3. Backups: los respaldos pre-cancelación expiran en 90 días.

## 6. Bitácora de tratamiento

**Toda operación que toca PII** queda registrada en `compliance_log` con:
- `usuario_id` que ejecutó (o sistema)
- `tipo_operacion`: descarga_denue, enriquecimiento_google,
  exportacion_csv, contacto_comercial, descarga_sat_69b, cruce_sat_69b,
  carga_indicadores_geograficos, calcular_scores_prospectos,
  arco_acceso, arco_rectificacion, arco_cancelacion, arco_oposicion
- `establecimiento_id` afectado (cuando aplica)
- `columnas_pii_tocadas` (subset de `_columnas_pii`)
- `finalidad` (texto libre justificando)
- `base_legal` (alguna de las 4 listadas en §2)
- `arco_solicitud_id` y `arco_plazo_dias_habiles` cuando aplica

Esta bitácora es **el principal mecanismo de defensa ante auditoría**. Es
inmutable (sin UPDATE/DELETE) y debe respaldarse por separado.

## 7. Sanciones (referencia)

La LFPDPPP 2025 contempla multas hasta **320,000 días de salario mínimo**
para infracciones graves. La Secretaría Anticorrupción y Buen Gobierno es
la autoridad sancionadora.

Las infracciones más comunes:
- Falta de aviso de privacidad: hasta 320 días de salario mínimo.
- Tratamiento de datos sin base legal: hasta 320,000 días.
- Vulneración de medidas de seguridad: hasta 320,000 días.

## 8. Pendientes de cumplimiento (para el operador y asesor legal)

| # | Pendiente | Quién | Fecha objetivo |
|---|---|---|---|
| 1 | Revisar y aprobar avisos de privacidad simplificado e integral | Asesor legal | Antes del primer contacto comercial real |
| 2 | Configurar email datos@intergranel.mx | Operador | Antes de publicar avisos |
| 3 | Designar responsable de protección de datos personales | Operador | Antes de publicar avisos |
| 4 | Publicar aviso integral en sitio web | Operador | Cuando exista sitio web |
| 5 | Capacitar a vendedores sobre la captura de PII | Operador + RH | Antes del primer contacto comercial |
| 6 | Establecer respaldos seguros del compliance_log | Operador / IT | Antes de prod en Render |
| 7 | Revisar contratos con proveedores que tocan PII (Google, Render) | Asesor legal | Antes de prod |
