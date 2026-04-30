"""compliance — capa de cumplimiento LFPDPPP 2025.

Módulos planeados (Fase 7):
- lfpdppp.py             → catálogo `_columnas_pii` + bitácora `compliance_log`
- aviso_privacidad.py    → generación de aviso simplificado e integral
- arco.py                → endpoint y workflow para Acceso/Rectificación/Cancelación/Oposición

Reglas no negociables:
- Toda operación que toque PII pasa por `lfpdppp.registrar_operacion(...)` antes
  de devolver datos al caller.
- ARCO debe responderse dentro de 20 días hábiles (timer en `compliance_log`).
- Datos del Listado 69-B se cruzan, no se almacenan crudos del SAT más allá del registro
  necesario para evidenciar el cruce.
"""
