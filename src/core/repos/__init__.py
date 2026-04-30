"""repositorios — patrón Repository por dominio.

Cada repositorio encapsula queries SQL/ORM contra una tabla o un agregado
de tablas. Las funciones de negocio (en `enrichment/`, `audit/`, `api/`)
NO deben hacer queries directas; pasan por aquí.

Razón: si el schema cambia, solo se toca la capa de repositorios. Si una
función de negocio mete `session.query(...)` directo, el cambio se propaga.

Convención:
- Cada repo es una clase con métodos que reciben `Session` como primer arg.
- Los métodos de lectura devuelven modelos ORM o tipos primitivos.
- Los métodos de escritura devuelven el objeto recién creado/actualizado.
- NO se hace `session.commit()` dentro del repo — el caller decide.
"""
