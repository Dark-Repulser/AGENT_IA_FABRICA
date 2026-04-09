"""MCP API — disease.sh sin API key"""
import asyncio, json, sys, time, urllib.request, urllib.error
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ── Logger ───────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from logger import get_logger
log = get_logger("api")

# ── Servidor ─────────────────────────────────────────────────────────────────
server = Server("api")

DISEASE_SH_BASE = "https://disease.sh/v3/covid-19/countries"


def fetch(url: str) -> dict:
    with urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "CA/1"}), timeout=6
    ) as r:
        return json.loads(r.read())


@server.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="get_health_alerts",
            description="Alertas sanitarias del pais",
            inputSchema={
                "type": "object",
                "properties": {"country": {"type": "string", "default": "Colombia"}},
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    log.info("tool invocado", tool=name, args=arguments)

    if name == "get_health_alerts":
        country = arguments.get("country", "Colombia")
        url = f"{DISEASE_SH_BASE}/{country}?strict=false"
        start = time.monotonic()

        try:
            log.debug("llamando a disease.sh", url=url, country=country)
            d = fetch(url)
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)

            active    = d.get("active", 0)
            today     = d.get("todayCases", 0)
            recovered = d.get("recovered", 0)
            deaths    = d.get("deaths", 0)

            if active > 50_000 or today > 1_000:
                level = "ALTO"
            elif active > 10_000:
                level = "MEDIO"
            else:
                level = "BAJO"

            log.info(
                "alertas sanitarias obtenidas",
                country=country,
                alert_level=level,
                active=active,
                today_cases=today,
                recovered=recovered,
                deaths=deaths,
                elapsed_ms=elapsed_ms,
            )

            result = {
                "ok":      True,
                "country": country,
                "level":   level,
                "active":  active,
                "today":   today,
            }

        except urllib.error.URLError as e:
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            log.warning(
                "API disease.sh no disponible",
                country=country,
                error=str(e),
                elapsed_ms=elapsed_ms,
            )
            result = {"ok": False, "msg": "API no disponible"}

        except Exception as e:
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            log.exception(
                "error inesperado al consultar alertas",
                country=country,
                error=str(e),
                elapsed_ms=elapsed_ms,
            )
            result = {"ok": False, "msg": str(e)}

        return [types.TextContent(type="text", text=json.dumps(result, separators=(",", ":")))]

    log.warning("tool desconocido", tool=name)
    return [types.TextContent(type="text", text="err:desconocido")]


async def main():
    log.info("servidor api iniciado", upstream=DISEASE_SH_BASE)
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())