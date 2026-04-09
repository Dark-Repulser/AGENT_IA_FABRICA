"""Agente Clínico — Google ADK. Gemini 2.5 flash."""
import asyncio, os, re, sys
from datetime import datetime, timedelta
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams, StdioServerParameters
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

# ── Logger ───────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from logger import get_logger
log = get_logger("agent")

# ── Fechas ───────────────────────────────────────────────────────────────────
TODAY    = datetime.now().strftime("%Y-%m-%d")
TOMORROW = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

log.info("agente inicializando", today=TODAY, tomorrow=TOMORROW)

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""You are a medical assistant that generates daily clinical shift reports.
Today's date is {TODAY}.

CRITICAL: You MUST use the exact real data returned by each tool. Never use placeholders or invented names.

Step-by-step instructions:

STEP 1: Call get_health_alerts(country="Colombia"). Save the result.
STEP 2: Call get_shift_summary(). Save total patients and doctors.
STEP 3: Call get_top_diagnoses(limit=3). Save the real diagnosis names and counts.
STEP 4: Call get_medication_stock(). Save every medication name, stock, and status.
STEP 5: Call calculate_occupancy(patients_attended=<real total from step 2>, max_capacity=20, shift_hours=12, doctors_count=2).
STEP 6: Call project_stock(medications=<exact list from step 4 with fields n, s, mn, c, u>).
STEP 7: Call generate_recommendations(occ=<pct from step 5>, zero=<names of CRITICO meds>, low=<names of BAJO meds>, alert=<level from step 1>, dx=<diagnosis names from step 3>).
STEP 8: Call write_file with path="cierre_{TODAY}.md" and the COMPLETE report below.

The file content MUST use the EXACT data from the tools. Format:

# Cierre de Turno — Centro Médico Norte — {TODAY}

## Resumen del Turno
- Clínica: [clinica from step 2]
- Fecha: {TODAY}
- Apertura: [apertura from step 2]
- Cierre: [cierre from step 2]
- Total pacientes: [total from step 2]
- Médicos: [list from step 2]

## Top 3 Diagnósticos
[For each diagnosis from step 3: - Name (code): N casos (X%)]

## Estado del Inventario
[For each medication from step 4: - Name: N unidades (STATUS)]

## Proyección de Stock para {TOMORROW}
[For each medication from step 6: - Name: N unidades mañana (STATUS)]
[List urgent actions]

## Alertas Sanitarias
- País: Colombia
- Nivel: [level from step 1]
- Casos activos: [active from step 1]

## Recomendaciones
[Each recommendation from step 7 with priority and message]

Do NOT use placeholder names like Medicamento1. Use the REAL names from the tool results."""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _conn(args: list, env: dict = None) -> StdioConnectionParams:
    p = StdioServerParameters(command="python", args=args, env=env or {})
    try:
        return StdioConnectionParams(server_params=p)
    except Exception:
        return StdioConnectionParams(command="python", args=args, env=env or {})


def create_agent() -> Agent:
    d  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ws = os.environ.get("WORKSPACE_PATH", f"{d}/workspace")
    model = os.environ.get("MODEL", "gemini-2.5-flash")

    db = {k: os.environ.get(k, v) for k, v in {
        "DATABASE_URL": "", "DB_HOST": "localhost", "DB_PORT": "5432",
        "DB_NAME": "clinica", "DB_USER": "postgres", "DB_PASSWORD": "",
    }.items()}

    log.info("creando agente", model=model, workspace=ws)

    agent = Agent(
        name="clinic_agent",
        model=model,
        instruction=SYSTEM_PROMPT,
        tools=[
            McpToolset(connection_params=_conn([f"{d}/mcp_servers/filesystem_server.py"], {"WORKSPACE_PATH": ws})),
            McpToolset(connection_params=_conn([f"{d}/mcp_servers/database_server.py"], db)),
            McpToolset(connection_params=_conn([f"{d}/mcp_servers/api_server.py"])),
            McpToolset(connection_params=_conn([f"{d}/mcp_servers/calculator_server.py"])),
        ],
    )
    log.info("agente creado", name="clinic_agent", model=model, mcp_servers=4)
    return agent


REPORT_KEYWORDS = ["cierre", "turno", "reporte", "informe", "genera", "report", "shift"]


def is_report_request(prompt: str) -> bool:
    return any(k in prompt.lower() for k in REPORT_KEYWORDS)


# ── Ejecución con retry ───────────────────────────────────────────────────────

async def run_once(prompt: str, runner: Runner, sid: str):
    from google.genai.types import Content, Part

    tool_calls_made = []
    final_text = ""

    log.info("iniciando ejecución", session_id=sid, prompt_len=len(prompt))

    async for ev in runner.run_async(
        user_id="u1",
        session_id=sid,
        new_message=Content(role="user", parts=[Part(text=prompt)]),
    ):
        if hasattr(ev, "content") and ev.content:
            for part in ev.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    tool_name = part.function_call.name
                    tool_calls_made.append(tool_name)
                    log.debug("tool call detectado", tool=tool_name, call_index=len(tool_calls_made))

        if ev.is_final_response() and ev.content:
            for p in ev.content.parts:
                if hasattr(p, "text") and p.text:
                    final_text += p.text

    log.info(
        "ejecución completada",
        session_id=sid,
        tools_called=tool_calls_made,
        total_tool_calls=len(tool_calls_made),
        response_len=len(final_text),
    )

    if is_report_request(prompt):
        if final_text and not tool_calls_made:
            log.warning("posible alucinación detectada", prompt=prompt[:80])
            raise ValueError("ALUCINACION: respondió sin usar herramientas.")
        if tool_calls_made and "write_file" not in tool_calls_made:
            log.warning(
                "flujo incompleto — write_file no fue invocado",
                tools_called=tool_calls_made,
            )
            raise ValueError(f"Flujo incompleto — tools: {', '.join(tool_calls_made)}")

    return final_text, tool_calls_made


async def run_with_retry(prompt: str, runner: Runner, sid: str, max_retries: int = 4):
    for attempt in range(max_retries):
        try:
            return await run_once(prompt, runner, sid)

        except ValueError as e:
            log.warning(
                "reintentando por validación fallida",
                attempt=attempt + 1,
                max_retries=max_retries,
                reason=str(e),
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(3)
                continue
            log.error("máximo de reintentos alcanzado", reason=str(e))
            raise

        except Exception as e:
            err = str(e)
            if "rate_limit" in err.lower() or "429" in err:
                wait = 20.0
                match = re.search(r"try again in ([\d.]+)s", err)
                if match:
                    wait = float(match.group(1)) + 3
                log.warning(
                    "rate limit alcanzado",
                    attempt=attempt + 1,
                    wait_seconds=wait,
                    error=err[:120],
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait)
                    continue
            log.error("error no recuperable", error=err, attempt=attempt + 1)
            raise

    raise Exception(f"Falló después de {max_retries} intentos")


# ── CLI ───────────────────────────────────────────────────────────────────────

async def cli():
    model = os.environ.get("MODEL", "gemini-2.5-flash")
    print(f"\n=== Agente Clínico | {model} | {TODAY} | 'salir' para terminar ===\n")

    ss  = InMemorySessionService()
    sid = f"s{datetime.now().strftime('%H%M%S')}"
    await ss.create_session(app_name="clinic", user_id="u1", session_id=sid)
    runner = Runner(agent=create_agent(), app_name="clinic", session_service=ss)

    log.info("CLI iniciada", session_id=sid, model=model)

    print("Ejemplo:")
    print(f"  > Genera el cierre del turno de hoy para la clínica Centro Médico Norte\n")

    while True:
        try:
            prompt = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            log.info("CLI terminada por el usuario")
            print("Hasta luego....")
            break

        if not prompt:
            continue
        if prompt.lower() in ("salir", "exit", "quit"):
            log.info("CLI terminada por comando", command=prompt)
            print("Hasta luego....")
            break

        log.info("prompt recibido", prompt=prompt[:120])
        print("\nProcesando...\n")

        try:
            text, tools = await run_with_retry(prompt, runner, sid)
            if tools:
                print(f"[Tools: {', '.join(tools)}]\n")
            print(text)
        except Exception as e:
            log.exception("error procesando prompt", prompt=prompt[:80], error=str(e))
            print(f"[ERROR] {e}")
        print()


if __name__ == "__main__":
    asyncio.run(cli())

# Expuesto para `adk web`
root_agent = create_agent()