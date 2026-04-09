# Caso Práctico: Cierre de Turno Clínico

## Descripción

Una clínica ambulatoria necesita automatizar el cierre de turno diario. El proceso manual
es lento y propenso a errores. El agente lo resuelve con un solo prompt en lenguaje natural.

## Prompt de Entrada

```
"Genera el cierre del turno de hoy para la clínica Centro Médico Norte"
```

## Flujo de Ejecución

El agente ejecuta de forma autónoma 8 llamadas a herramientas en este orden:

```
1. get_health_alerts     → API disease.sh  → alertas sanitarias Colombia
2. get_shift_summary     → PostgreSQL       → total pacientes, horas turno
3. get_top_diagnoses     → PostgreSQL       → top 3 diagnósticos del día
4. get_medication_stock  → PostgreSQL       → stock actual + consumo del día
5. calculate_occupancy   → Calculadora      → % ocupación, min/paciente
6. project_stock         → Calculadora      → stock proyectado para mañana
7. generate_recommendations → Calculadora  → recomendaciones automáticas
8. write_file            → Filesystem       → /workspace/cierre_YYYY-MM-DD.md
```

## Reporte Generado

El archivo `/workspace/cierre_YYYY-MM-DD.md` incluye:

- **Resumen del turno**: clínica, fecha, hora apertura/cierre, total pacientes, médicos
- **Top 3 diagnósticos**: con conteo y porcentaje del total
- **Estado del inventario**: cada medicamento clasificado como OK / BAJO / CRITICO
- **Proyección de stock**: estimación para el día siguiente con factor de seguridad 1.1
- **Alertas sanitarias**: nivel (BAJO/MEDIO/ALTO) desde disease.sh API
- **Recomendaciones automáticas**: ordenadas por prioridad (URGENTE → RUTINA)

## Manejo de Errores

| Escenario | Comportamiento |
|---|---|
| API no responde | Continúa el flujo, indica "API no disponible" en el reporte |
| No hay pacientes hoy | Reporta total: 0, no falla, sugiere verificar carga |
| Stock en cero | Marca como CRITICO y agrega URGENTE en recomendaciones |
| Error de escritura | El agente informa el error con detalle al usuario |

## Arquitectura

```
Usuario
  │
  ▼
agent.py  ──── Google ADK (Runner + Agent)
  │               │
  │               └── gemini-2.5-flash (nativo ADK)
  │
  ├── McpToolset ──► filesystem_server.py   (stdio)
  ├── McpToolset ──► database_server.py     (stdio)
  ├── McpToolset ──► api_server.py          (stdio)
  └── McpToolset ──► calculator_server.py   (stdio)
```

Cada MCP server es un proceso Python independiente que se comunica con el agente
vía stdin/stdout usando el protocolo MCP.

## Decisiones de Diseño

**¿Por qué PostgreSQL y no SQLite?**
PostgreSQL soporta concurrencia real, tipos de datos más ricos y es el estándar
en producción clínica. La migración desde SQLite es trivial cambiando solo la
cadena de conexión.

**¿Por qué disease.sh?**
Es la única API epidemiológica pública, gratuita y sin API key que devuelve datos
reales por país. Tiene fallback graceful si no responde.

**¿Por qué Gemini?**
Gemini es el LLM nativo de Google ADK — sin adaptadores adicionales. Tiene soporte
robusto de function calling y free tier real desde AI Studio sin necesidad de billing.
El modelo se configura con una sola variable de entorno `MODEL`.

**¿Por qué transport stdio para MCP?**
Simplicidad de despliegue local. Cada server es un proceso aislado — si un MCP
falla, los demás siguen funcionando. Para producción en nube se migraría a SSE/HTTP
sin cambiar la lógica del agente.

## Cómo Ejecutar

```bash
# 1. Configurar variables de entorno
cp .env.example .env
# Editar .env y agregar GOOGLE_API_KEY (obtener en https://aistudio.google.com/apikey)

# 2. Levantar todos los servicios
docker-compose up -d --build

# 3. Verificar que todo está corriendo
docker-compose ps

# 4. Entrar a la consola del agente
docker exec -it clinic_agent python agent/agent.py

# 5. Ejecutar el prompt
>>> Genera el cierre del turno de hoy para la clínica Centro Médico Norte

# 6. Ver el reporte generado (aparece en tu PC)
cat workspace/cierre_2026-04-07.md
```

## Ejecutar Tests

```bash
# Dentro del contenedor
docker exec -it clinic_agent python -m pytest tests/test_agent.py -v

# Ver solo los que fallan
docker exec -it clinic_agent python -m pytest tests/test_agent.py -v --tb=short
```

## Conectarse a la Base de Datos

```
Host:     localhost
Port:     5432
Database: clinica
User:     clinic_user
Password: clinic_secret
```

```bash
# Desde terminal
psql -h localhost -p 5432 -U clinic_user -d clinica
```
