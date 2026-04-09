"""MCP Calculadora — metricas clinicas"""
import asyncio, json, math, sys
from datetime import date, timedelta
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ── Logger ───────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from logger import get_logger
log = get_logger("calculator")

# ── Servidor ─────────────────────────────────────────────────────────────────
server = Server("calc")


def j(d) -> str:
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


@server.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="calculate_occupancy",
            description="Porcentaje ocupacion del turno",
            inputSchema={
                "type": "object",
                "required": ["patients_attended"],
                "properties": {
                    "patients_attended": {"type": "integer"},
                    "max_capacity":      {"type": "integer", "default": 20},
                    "shift_hours":       {"type": "number",  "default": 12},
                    "doctors_count":     {"type": "integer", "default": 2},
                },
            },
        ),
        types.Tool(
            name="project_stock",
            description="Proyeccion stock para manana",
            inputSchema={
                "type": "object",
                "required": ["medications"],
                "properties": {
                    "medications": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "n":  {"type": "string"},
                                "s":  {"type": "integer"},
                                "mn": {"type": "integer"},
                                "c":  {"type": "integer"},
                                "u":  {"type": "string"},
                            },
                        },
                    },
                    "sf": {"type": "number", "default": 1.1},
                },
            },
        ),
        types.Tool(
            name="generate_recommendations",
            description="Recomendaciones para el turno",
            inputSchema={
                "type": "object",
                "required": ["occ"],
                "properties": {
                    "occ":   {"type": "number"},
                    "zero":  {"type": "array", "items": {"type": "string"}},
                    "low":   {"type": "array", "items": {"type": "string"}},
                    "alert": {"type": "string"},
                    "dx":    {"type": "array", "items": {"type": "string"}},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    log.info("tool invocado", tool=name)
    try:

        # ── calculate_occupancy ──────────────────────────────────────────────
        if name == "calculate_occupancy":
            att   = arguments["patients_attended"]
            cap   = arguments.get("max_capacity", 20)
            hrs   = arguments.get("shift_hours", 12)
            docs  = arguments.get("doctors_count", 2)

            pct     = round(att / cap * 100, 1) if cap else 0
            avg_min = round(hrs * 60 / att, 1)  if att else 0
            per_doc = round(att / docs, 1)       if docs else att

            if pct >= 90:
                status = "SOBRECARGADO"
            elif pct >= 70:
                status = "ALTO"
            elif pct >= 40:
                status = "NORMAL"
            else:
                status = "BAJO"

            log.info(
                "ocupación calculada",
                patients_attended=att,
                max_capacity=cap,
                pct=pct,
                status=status,
                avg_min_per_patient=avg_min,
                per_doctor=per_doc,
            )

            return [types.TextContent(type="text", text=j(
                {"pct": pct, "status": status, "avg_min": avg_min, "per_doc": per_doc}
            ))]

        # ── project_stock ────────────────────────────────────────────────────
        if name == "project_stock":
            sf      = arguments.get("sf", 1.1)
            tom     = (date.today() + timedelta(days=1)).isoformat()
            proj, urgent = [], []

            for m in arguments["medications"]:
                nombre = m.get("n", m.get("nombre", "?"))
                s      = m.get("s", m.get("stock_actual", 0))
                mn     = m.get("mn", m.get("stock_minimo", 10))
                c      = m.get("c", m.get("consumo", m.get("consumo_hoy", 0)))
                u      = m.get("u", m.get("unidad", "u"))

                c2 = math.ceil(c * sf)          # consumo proyectado con factor seguridad
                s2 = max(0, s - c2)             # stock estimado mañana

                if s == 0:
                    estado = "CRITICO"
                    urgent.append(f"URGENTE:{nombre}")
                elif s2 < mn:
                    estado = "RIESGO"
                    urgent.append(f"PEDIR:{nombre}")
                else:
                    estado = "OK"

                proj.append({"n": nombre, "s": s, "s2": s2, "estado": estado})

            criticos = [p["n"] for p in proj if p["estado"] == "CRITICO"]
            riesgos  = [p["n"] for p in proj if p["estado"] == "RIESGO"]
            log.info(
                "proyección de stock calculada",
                fecha_proyeccion=tom,
                safety_factor=sf,
                total_meds=len(proj),
                criticos=criticos,
                riesgos=riesgos,
                acciones_urgentes=len(urgent),
            )

            return [types.TextContent(type="text", text=j(
                {"fecha": tom, "proj": proj, "urgent": urgent}
            ))]

        # ── generate_recommendations ─────────────────────────────────────────
        if name == "generate_recommendations":
            occ   = arguments.get("occ", 0)
            zero  = arguments.get("zero", [])
            low   = arguments.get("low", [])
            alert = arguments.get("alert", "BAJO")
            dx    = arguments.get("dx", [])
            recs  = []

            for m in zero:
                recs.append({"p": "URGENTE", "msg": f"SIN STOCK:{m}"})
            if occ >= 90:
                recs.append({"p": "ALTA", "msg": "Turno sobrecargado"})
            if low:
                recs.append({"p": "ALTA", "msg": f"Stock bajo:{','.join(low[:3])}"})
            if alert == "ALTO":
                recs.append({"p": "ALTA", "msg": "Alerta sanitaria alta"})
            if dx:
                recs.append({"p": "MEDIA", "msg": f"Dx frecuentes:{','.join(dx[:2])}"})
            recs.append({"p": "RUTINA", "msg": "Completar historias y verificar stock"})

            recs.sort(key=lambda x: {"URGENTE": 0, "ALTA": 1, "MEDIA": 2, "RUTINA": 3}.get(x["p"], 4))

            log.info(
                "recomendaciones generadas",
                occ=occ,
                sin_stock=zero,
                stock_bajo=low,
                alerta_sanitaria=alert,
                top_dx=dx[:2],
                total_recomendaciones=len(recs),
                urgentes=sum(1 for r in recs if r["p"] == "URGENTE"),
            )

            return [types.TextContent(type="text", text=j({"recs": recs}))]

        log.warning("tool desconocido", tool=name)
        return [types.TextContent(type="text", text=f"err:{name}")]

    except Exception as e:
        log.exception("error en tool", tool=name, error=str(e))
        return [types.TextContent(type="text", text=f"err:{e}")]


async def main():
    log.info("servidor calculator iniciado")
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())