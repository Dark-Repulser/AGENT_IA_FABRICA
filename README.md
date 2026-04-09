# Agente de Cierre de Turno Clínico

Agente de IA construido con **Google ADK** que automatiza el cierre de turno diario de clínicas ambulatorias. Con un solo prompt en lenguaje natural, el agente consulta APIs externas, la base de datos, calcula métricas y genera un reporte completo en markdown.


<!--horizontal divider(gradiant)-->
<img src="https://user-images.githubusercontent.com/73097560/115834477-dbab4500-a447-11eb-908a-139a6edaec5c.gif">
<h2>Hecho por david Romero con mucho amor UwU</h2>
<br>
<!--horizontal divider(gradiant)-->
<img src="https://user-images.githubusercontent.com/73097560/115834477-dbab4500-a447-11eb-908a-139a6edaec5c.gif">


---

## Stack

| Componente | Elección | Razón |
|---|---|---|
| Framework agente | Google ADK | Requerimiento obligatorio |
| LLM | Gemini 2.5 Flash | Nativo en ADK, function calling robusto, free tier real |
| Base de datos | PostgreSQL | Estándar producción, concurrencia real |
| API externa | disease.sh | Pública, gratuita, sin API key |
| Transport MCP | stdio | Simple, proceso aislado por server |
| Contenedor | Docker + Compose | Entorno reproducible |
| Logging | JSON estructurado | Trazabilidad completa por componente |

---

## Estructura

```
clinic-agent/
├── agent/
│   ├── __init__.py           # Expone el agente para adk web
│   └── agent.py              # Agente principal Google ADK
├── mcp_servers/
│   ├── __init__.py
│   ├── filesystem_server.py  # MCP 1: Leer/escribir archivos (sandboxed)
│   ├── database_server.py    # MCP 2: CRUD PostgreSQL
│   ├── api_server.py         # MCP 3: API disease.sh (sin API key)
│   └── calculator_server.py  # MCP 4: Métricas clínicas + proyecciones
├── tests/
│   └── test_agent.py         # 25 tests automatizados
├── use_cases/
│   └── cierre_turno.md       # Documentación del caso práctico
├── workspace/                # Reportes generados (montado en Docker)
├── logs/                     # Logs JSON persistidos (montado en Docker)
├── logger.py                 # Módulo de logging estructurado JSON compartido
├── schema.sql                # Esquema PostgreSQL + datos de prueba
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Requisitos

- Docker y Docker Compose
- Google API Key gratis en [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
---

## Instalación y Ejecución

```bash
# 1. Configurar variables de entorno
cp .env.example .env
# Editar .env y agregar tu GOOGLE_API_KEY

# 2. Crear carpetas de salida (Linux/Mac)
mkdir -p logs workspace

# 2. Crear carpetas de salida (Windows PowerShell)
mkdir logs, workspace

# 3. Levantar los servicios
docker-compose up -d --build

# 4. Verificar que todo está corriendo
docker-compose ps

# 5. Abrir ADK Web UI
# >>>>>>>>>> http://localhost:8000 <<<<<<<<<<

# 6. En la UI, ejecutar el prompt del caso práctico
>>> Genera el cierre del turno de hoy para la clínica Centro Médico Norte

# 7. Ver el reporte generado (aparece directamente en tu PC)
cat workspace/cierre_2026-04-07.md 
```

El servicio `agent` inicia directamente con `adk web`, no necesitas abrir la CLI manualmente.

---

## Ejecutar Tests

```bash
# Dentro del contenedor
docker exec -it clinic_agent python -m pytest tests/test_agent.py -v

# Con detalle de errores
docker exec -it clinic_agent python -m pytest tests/test_agent.py -v --tb=short

# Directamente sin pytest
docker exec -it clinic_agent python tests/test_agent.py
```

---

## Variables de Entorno

```env
# Google API Key — obtener gratis en https://aistudio.google.com/apikey
- En caso de tener problemas por tokens por el free trial contactar a david_romerom@cun.edu.co
- O escribir al numero : 3045953836 para solicitar una api key con mas tokens
GOOGLE_API_KEY=AIza...

# Modelo Gemini (opcional — este es el default)
MODEL=gemini-2.5-flash

# PostgreSQL
DB_PASSWORD=clinic_secret

# Logging (opcional)
LOG_LEVEL=INFO      # DEBUG | INFO | WARNING | ERROR
LOG_FILE=/logs/agent.log
```

Ver `.env.example` para la plantilla completa.

---

## Logging Estructurado JSON

El proyecto incluye un módulo `logger.py` compartido que todos los componentes utilizan. Cada línea de log es un objeto JSON independiente, lo que facilita su ingesta en cualquier herramienta de observabilidad.

### Formato de cada línea

```json
{
  "timestamp": "2026-04-07T14:23:01.482Z",
  "level": "INFO",
  "logger": "database",
  "pid": 42,
  "message": "stock de medicamentos obtenido",
  "server": "database",
  "fecha": "2026-04-07",
  "total": 10,
  "criticos": ["Losartán 50mg"],
  "bajos": ["Ibuprofeno 400mg"]
}
```

### Qué loguea cada componente

| Componente | Eventos registrados |
|---|---|
| `agent.py` | Inicialización, tool calls detectados, resultado final, reintentos, rate limits, alucinaciones |
| `database_server.py` | Creación del pool, cada query SQL con tiempo en ms, medicamentos CRITICO/BAJO, queries, rechazadas |
| `filesystem_server.py` | Arranque del servidor, escrituras con tamaño en bytes, path traversal bloqueado |
| `api_server.py` | Llamada a disease.sh, nivel de alerta resultante, tiempo de respuesta, errores de red |
| `calculator_server.py` | Ocupación con status, medicamentos críticos/en riesgo, recomendaciones urgentes generadas |

### Dónde se guardan los logs

| Configuración | Destino |
|---|---|
| Sin `LOG_FILE` | Solo `stderr` — visible con `docker-compose logs -f agent` |
| `LOG_FILE=/logs/agent.log` | `stderr` + archivo `./logs/agent.log` en tu PC |

### Ver logs en tiempo real

```bash
# Desde Docker (stderr) — formato JSON crudo
docker-compose logs -f agent

# Desde el archivo en tu PC — con pretty print
tail -f logs/agent.log | python -m json.tool

# Filtrar solo errores
tail -f logs/agent.log | grep '"level":"ERROR"'

# Filtrar por componente
tail -f logs/agent.log | grep '"logger":"database"'

# Ver solo tool calls del agente
tail -f logs/agent.log | grep '"tool"'
```

### Niveles de log

```env
LOG_LEVEL=INFO   # Default — muestra eventos relevantes de cada operación
LOG_LEVEL=DEBUG  # Verbose — incluye cada query SQL, tiempo en ms y cada tool call individual
```

### Uso en código

```python
from logger import get_logger

log = get_logger("mi_componente")

log.info("operación completada", filas=15, elapsed_ms=42.3)
log.warning("stock bajo", medicamento="Ibuprofeno", stock=8, minimo=20)
log.error("conexión fallida", host="localhost", error=str(e))
log.exception("error inesperado", tool="write_file")  # incluye traceback automático

# Campos fijos para todo el módulo
log = get_logger("database").bind(host="postgres", db="clinica")
log.info("conectado")  # → incluye host y db en cada línea
```

---

## Conectarse a PostgreSQL

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

# Ver pacientes de hoy
docker exec clinic_postgres psql -U clinic_user -d clinica \
  -c "SELECT nombre, diagnostico_principal FROM pacientes WHERE fecha_atencion = CURRENT_DATE;"
```

---

## Bajar los servicios

```bash
# Bajar pero conservar datos
docker-compose down

# Bajar y borrar todo (reset completo)
docker-compose down -v
```

---

## MCP Servers

| Server | Tools | Seguridad |
|---|---|---|
| Filesystem | write_file, read_file, list_files | Sandbox con Path.resolve(), path traversal bloqueado |
| Base de datos | get_shift_summary, get_top_diagnoses, get_medication_stock, execute_query | Solo SELECT en execute_query, params separados (anti SQL injection) |
| API externa | get_health_alerts | Fallback graceful si disease.sh no responde |
| Calculadora | calculate_occupancy, project_stock, generate_recommendations | División por cero protegida, stock negativo imposible |

---

## Puntos Bonus Implementados

- Docker funcional
- Implementación asíncrona completa
- 4to MCP server con utilidad real (calculadora clínica)
- ADK Web UI para operar el agente desde navegador
- Detección de alucinación con retry automático
- Logging estructurado JSON con trazabilidad completa por componente
