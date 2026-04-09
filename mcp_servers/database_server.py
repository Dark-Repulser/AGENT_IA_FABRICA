"""MCP Database — PostgreSQL"""
import asyncio, json, os, sys, time
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
import psycopg2, psycopg2.extras
from psycopg2 import pool as pg_pool

# ── Logger ───────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from logger import get_logger
log = get_logger("database")

# ── Servidor ─────────────────────────────────────────────────────────────────
server = Server("db")


def _dsn() -> str:
    u = os.environ.get("DATABASE_URL")
    if u:
        return u
    return (
        f"host={os.environ.get('DB_HOST', 'localhost')} "
        f"port={os.environ.get('DB_PORT', '5432')} "
        f"dbname={os.environ.get('DB_NAME', 'clinica')} "
        f"user={os.environ.get('DB_USER', 'postgres')} "
        f"password={os.environ.get('DB_PASSWORD', '')} "
        f"connect_timeout=5"
    )


_pool = None


def pool():
    global _pool
    if _pool is None or _pool.closed:
        dsn = _dsn()
        log.info("creando pool de conexiones", min_conn=1, max_conn=3)
        _pool = pg_pool.ThreadedConnectionPool(1, 3, dsn=dsn)
        log.info("pool creado exitosamente")
    return _pool


@contextmanager
def db():
    conn = pool().getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool().putconn(conn)


def q(conn, sql: str, params=()):
    """Ejecuta una query y retorna filas como lista de dicts."""
    start = time.monotonic()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    elapsed_ms = round((time.monotonic() - start) * 1000, 2)

    result = []
    for r in rows:
        d = dict(r)
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
            elif hasattr(v, "__float__") and not isinstance(v, (int, float)):
                d[k] = float(v)
        result.append(d)

    log.debug(
        "query ejecutada",
        sql=sql[:120],
        params=str(params),
        rows=len(result),
        elapsed_ms=elapsed_ms,
    )
    return result


def j(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


@server.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="get_shift_summary",
            description="Resumen turno",
            inputSchema={"type": "object", "properties": {"fecha": {"type": "string", "default": ""}}},
        ),
        types.Tool(
            name="get_top_diagnoses",
            description="Top diagnosticos",
            inputSchema={
                "type": "object",
                "properties": {
                    "fecha": {"type": "string", "default": ""},
                    "limit": {"type": "integer", "default": 3},
                },
            },
        ),
        types.Tool(
            name="get_medication_stock",
            description="Stock medicamentos",
            inputSchema={"type": "object", "properties": {"fecha": {"type": "string", "default": ""}}},
        ),
        types.Tool(
            name="execute_query",
            description="SELECT en DB",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    log.info("tool invocado", tool=name)
    start = time.monotonic()

    try:
        fecha = arguments.get("fecha", "") or date.today().isoformat()

        with db() as conn:

            if name == "get_shift_summary":
                cfg = q(conn, "SELECT clinica_nombre,hora_apertura,hora_cierre FROM turno_config WHERE id=1")
                tot = q(conn, "SELECT COUNT(*) n FROM pacientes WHERE fecha_atencion=%s", (fecha,))
                mds = q(conn, "SELECT medico,COUNT(*) n FROM pacientes WHERE fecha_atencion=%s GROUP BY medico", (fecha,))
                total = tot[0]["n"] if tot else 0
                log.info(
                    "resumen de turno obtenido",
                    fecha=fecha,
                    total_pacientes=total,
                    medicos=len(mds),
                )
                return [types.TextContent(type="text", text=j({
                    "clinica":  cfg[0]["clinica_nombre"] if cfg else "Centro Medico Norte",
                    "fecha":    fecha,
                    "apertura": str(cfg[0]["hora_apertura"]) if cfg else "07:00",
                    "cierre":   str(cfg[0]["hora_cierre"])   if cfg else "19:00",
                    "total":    total,
                    "medicos":  [{"m": r["medico"], "n": r["n"]} for r in mds],
                }))]

            if name == "get_top_diagnoses":
                lim = int(arguments.get("limit", 3))
                dx = q(conn, """
                    SELECT diagnostico_principal d, diagnostico_codigo c, COUNT(*) n
                    FROM pacientes WHERE fecha_atencion=%s
                    GROUP BY d, c ORDER BY n DESC LIMIT %s
                """, (fecha, lim))
                tot = q(conn, "SELECT COUNT(*) n FROM pacientes WHERE fecha_atencion=%s", (fecha,))
                t = tot[0]["n"] or 1
                log.info("top diagnósticos obtenidos", fecha=fecha, count=len(dx), limit=lim)
                return [types.TextContent(type="text", text=j(
                    [{"r": i + 1, "d": x["d"], "c": x["c"], "n": x["n"], "pct": round(x["n"] / t * 100, 1)}
                     for i, x in enumerate(dx)]
                ))]

            if name == "get_medication_stock":
                rows = q(conn, """
                    SELECT m.nombre, m.stock_actual s, m.stock_minimo mn, m.unidad u,
                           COALESCE(SUM(d.cantidad), 0) consumo
                    FROM medicamentos m
                    LEFT JOIN dispensacion d ON d.medicamento_id=m.id AND d.fecha=%s
                    GROUP BY m.id ORDER BY m.nombre
                """, (fecha,))

                result = []
                criticos, bajos = [], []
                for r in rows:
                    s = r["s"]
                    if s == 0:
                        estado = "CRITICO"
                        criticos.append(r["nombre"])
                    elif s <= r["mn"]:
                        estado = "BAJO"
                        bajos.append(r["nombre"])
                    else:
                        estado = "OK"
                    result.append({"n": r["nombre"], "s": s, "mn": r["mn"], "u": r["u"], "c": int(r["consumo"]), "e": estado})

                log.info(
                    "stock de medicamentos obtenido",
                    fecha=fecha,
                    total=len(result),
                    criticos=criticos,
                    bajos=bajos,
                )
                return [types.TextContent(type="text", text=j(result))]

            if name == "execute_query":
                raw = arguments["query"].strip()
                if not raw.upper().startswith("SELECT"):
                    log.warning("query rechazada por seguridad", query=raw[:80])
                    return [types.TextContent(type="text", text="err:solo SELECT")]
                rows = q(conn, raw)
                log.info("execute_query completada", rows=len(rows), query=raw[:80])
                return [types.TextContent(type="text", text=j(rows))]

        log.warning("tool desconocido", tool=name)
        return [types.TextContent(type="text", text=f"err:tool desconocido {name}")]

    except Exception as e:
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        log.exception("error en tool", tool=name, error=str(e), elapsed_ms=elapsed_ms)
        return [types.TextContent(type="text", text=f"err:{e}")]

    finally:
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        log.debug("tool finalizado", tool=name, elapsed_ms=elapsed_ms)


async def main():
    log.info("servidor database iniciado")
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())