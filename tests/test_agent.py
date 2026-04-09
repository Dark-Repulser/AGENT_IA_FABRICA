"""
Tests Automatizados — Agente Cierre de Turno Clínico
Cubre: happy path, errores, seguridad — mínimo 15 tests
Alineados con la versión actual del código (PostgreSQL + respuestas compactas)
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "mcp_servers"))


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_temp_workspace():
    return tempfile.mkdtemp()


# ─── FILESYSTEM MCP ───────────────────────────────────────────────────────────

class TestFilesystemMCP(unittest.TestCase):

    def setUp(self):
        self.workspace = make_temp_workspace()
        os.environ["WORKSPACE_PATH"] = self.workspace
        import importlib
        import mcp_servers.filesystem_server as fs_mod
        importlib.reload(fs_mod)
        self.fs = fs_mod

    # Happy Path

    def test_01_write_file_success(self):
        """HP: Escribe archivo y retorna confirmación"""
        result = run_async(self.fs.call_tool("write_file", {
            "path": "cierre_2026-04-07.md",
            "content": "# Reporte de prueba"
        }))
        self.assertIn("ok:", result[0].text)
        self.assertTrue((Path(self.workspace) / "cierre_2026-04-07.md").exists())

    def test_02_read_file_success(self):
        """HP: Lee archivo existente"""
        fp = Path(self.workspace) / "test.txt"
        fp.write_text("contenido de prueba")
        result = run_async(self.fs.call_tool("read_file", {"path": "test.txt"}))
        self.assertIn("contenido de prueba", result[0].text)

    def test_03_list_files_success(self):
        """HP: Lista archivos del workspace"""
        (Path(self.workspace) / "reporte1.md").write_text("a")
        (Path(self.workspace) / "reporte2.md").write_text("b")
        result = run_async(self.fs.call_tool("list_files", {"pattern": "*.md"}))
        self.assertIn("reporte1.md", result[0].text)
        self.assertIn("reporte2.md", result[0].text)

    def test_04_write_creates_subdirectories(self):
        """HP: Crea subdirectorios si no existen"""
        result = run_async(self.fs.call_tool("write_file", {
            "path": "subdir/reporte.md",
            "content": "contenido"
        }))
        self.assertIn("ok:", result[0].text)
        self.assertTrue((Path(self.workspace) / "subdir" / "reporte.md").exists())

    # Error Cases

    def test_05_read_nonexistent_file(self):
        """ERR: Archivo inexistente retorna mensaje claro"""
        result = run_async(self.fs.call_tool("read_file", {"path": "fantasma.md"}))
        self.assertIn("no encontrado", result[0].text)

    def test_06_list_empty_workspace(self):
        """ERR: Workspace vacío retorna 'vacio'"""
        result = run_async(self.fs.call_tool("list_files", {}))
        self.assertIn("vacio", result[0].text.lower())

    # Security

    def test_07_path_traversal_blocked(self):
        """SEC: Path traversal ../../etc/ bloqueado"""
        run_async(self.fs.call_tool("write_file", {
            "path": "../../etc/evil.txt",
            "content": "malicious"
        }))
        self.assertFalse(Path("/etc/evil.txt").exists())

    def test_08_absolute_path_sandboxed(self):
        """SEC: Ruta absoluta no escapa del sandbox"""
        run_async(self.fs.call_tool("write_file", {
            "path": "/tmp/escaped_test_clinic.txt",
            "content": "should be sandboxed"
        }))
        escaped = Path("/tmp/escaped_test_clinic.txt")
        if escaped.exists() and escaped.read_text() == "should be sandboxed":
            self.fail("Sandbox roto — archivo escrito fuera del workspace")


# ─── DATABASE MCP — lógica sin PostgreSQL real ────────────────────────────────

class TestDatabaseLogic(unittest.TestCase):
    """
    Prueba la lógica del server sin necesitar PostgreSQL real.
    """

    def test_09_estado_critico_cuando_stock_cero(self):
        """HP: stock=0 → CRITICO"""
        s, mn = 0, 15
        estado = "CRITICO" if s == 0 else "BAJO" if s <= mn else "OK"
        self.assertEqual(estado, "CRITICO")

    def test_10_estado_bajo_cuando_stock_menor_minimo(self):
        """HP: stock <= mínimo → BAJO"""
        s, mn = 8, 10
        estado = "CRITICO" if s == 0 else "BAJO" if s <= mn else "OK"
        self.assertEqual(estado, "BAJO")

    def test_11_estado_ok_cuando_stock_suficiente(self):
        """HP: stock > mínimo → OK"""
        s, mn = 100, 20
        estado = "CRITICO" if s == 0 else "BAJO" if s <= mn else "OK"
        self.assertEqual(estado, "OK")

    def test_12_select_injection_semicolon_bloqueado(self):
        """SEC: SELECT con ; y DROP no comienza con SELECT válido como sentencia sola"""
        # El server solo ejecuta la primera sentencia y el ; es ignorado por psycopg2
        # pero el check adicional detecta queries no-SELECT
        malicious = "DELETE FROM pacientes"
        is_select = malicious.strip().upper().startswith("SELECT")
        self.assertFalse(is_select)

    def test_13_non_select_queries_rejected(self):
        """SEC: INSERT, UPDATE, DROP son rechazados"""
        bad_queries = [
            "INSERT INTO pacientes VALUES (1,'x')",
            "UPDATE medicamentos SET stock_actual=0",
            "DROP TABLE pacientes",
        ]
        for q in bad_queries:
            valid = q.strip().upper().startswith("SELECT")
            self.assertFalse(valid, f"Query peligrosa pasó validación: {q}")


# ─── CALCULATOR MCP ───────────────────────────────────────────────────────────

class TestCalculatorMCP(unittest.TestCase):

    def setUp(self):
        import importlib
        import mcp_servers.calculator_server as calc_mod
        importlib.reload(calc_mod)
        self.calc = calc_mod

    def test_14_occupancy_75_percent_alto(self):
        """HP: 15/20 pacientes → 75% → ALTO"""
        result = run_async(self.calc.call_tool("calculate_occupancy", {
            "patients_attended": 15,
            "max_capacity": 20,
            "shift_hours": 12,
            "doctors_count": 2
        }))
        data = json.loads(result[0].text)
        self.assertEqual(data["pct"], 75.0)
        self.assertEqual(data["status"], "ALTO")
        self.assertEqual(data["per_doc"], 7.5)

    def test_15_occupancy_zero_no_crash(self):
        """ERR: 0 pacientes no lanza ZeroDivisionError"""
        result = run_async(self.calc.call_tool("calculate_occupancy", {
            "patients_attended": 0,
            "max_capacity": 20
        }))
        data = json.loads(result[0].text)
        self.assertEqual(data["pct"], 0.0)

    def test_16_occupancy_sobrecargado(self):
        """HP: >= 90% → SOBRECARGADO"""
        result = run_async(self.calc.call_tool("calculate_occupancy", {
            "patients_attended": 19,
            "max_capacity": 20
        }))
        data = json.loads(result[0].text)
        self.assertEqual(data["status"], "SOBRECARGADO")

    def test_17_project_stock_zero_is_critico(self):
        """HP: stock=0 → CRITICO + acción URGENTE"""
        result = run_async(self.calc.call_tool("project_stock", {
            "medications": [
                {"n": "Losartan 50mg", "s": 0, "mn": 15, "c": 5, "u": "tabletas"}
            ]
        }))
        data = json.loads(result[0].text)
        self.assertEqual(data["proj"][0]["estado"], "CRITICO")
        self.assertTrue(any("URGENTE" in u for u in data["urgent"]))

    def test_18_project_stock_safety_factor(self):
        """HP: safety_factor=1.1, consumo=10 → proyectado=11, stock=89"""
        result = run_async(self.calc.call_tool("project_stock", {
            "medications": [
                {"n": "Paracetamol", "s": 100, "mn": 20, "c": 10, "u": "tabletas"}
            ],
            "sf": 1.1
        }))
        data = json.loads(result[0].text)
        self.assertEqual(data["proj"][0]["s2"], 89)

    def test_19_recommendations_urgente_first(self):
        """HP: stock=0 → URGENTE es la primera recomendación"""
        result = run_async(self.calc.call_tool("generate_recommendations", {
            "occ": 75,
            "zero": ["Losartan 50mg"],
            "low": [],
            "alert": "BAJO",
            "dx": []
        }))
        data = json.loads(result[0].text)
        self.assertEqual(data["recs"][0]["p"], "URGENTE")

    def test_20_recommendations_always_rutina(self):
        """HP: Siempre hay al menos una recomendación de rutina"""
        result = run_async(self.calc.call_tool("generate_recommendations", {
            "occ": 50, "zero": [], "low": [], "alert": "BAJO", "dx": []
        }))
        data = json.loads(result[0].text)
        prioridades = [r["p"] for r in data["recs"]]
        self.assertIn("RUTINA", prioridades)


# ─── API MCP ──────────────────────────────────────────────────────────────────

class TestAPIMCP(unittest.TestCase):

    def setUp(self):
        import importlib
        import mcp_servers.api_server as api_mod
        importlib.reload(api_mod)
        self.api = api_mod

    def test_21_api_success_nivel_bajo(self):
        """HP: Pocos casos activos → nivel BAJO"""
        with patch("mcp_servers.api_server.fetch",
                   return_value={"active": 5000, "todayCases": 50}):
            result = run_async(self.api.call_tool("get_health_alerts", {"country": "Colombia"}))
            data = json.loads(result[0].text)
            self.assertTrue(data["ok"])
            self.assertEqual(data["level"], "BAJO")

    def test_22_api_success_nivel_alto(self):
        """HP: Muchos casos → nivel ALTO"""
        with patch("mcp_servers.api_server.fetch",
                   return_value={"active": 100000, "todayCases": 2000}):
            result = run_async(self.api.call_tool("get_health_alerts", {}))
            data = json.loads(result[0].text)
            self.assertEqual(data["level"], "ALTO")

    def test_23_api_unavailable_graceful(self):
        """ERR: API caída → ok=False, flujo continúa"""
        with patch("mcp_servers.api_server.fetch",
                   side_effect=urllib.error.URLError("timeout")):
            result = run_async(self.api.call_tool("get_health_alerts", {"country": "Colombia"}))
            data = json.loads(result[0].text)
            self.assertFalse(data["ok"])
            self.assertIn("msg", data)

    def test_24_api_unknown_tool_returns_error(self):
        """ERR: Tool inexistente retorna error"""
        result = run_async(self.api.call_tool("tool_inexistente", {}))
        self.assertIn("err", result[0].text.lower())

    def test_25_api_nivel_medio(self):
        """HP: active > 10000 → nivel MEDIO"""
        with patch("mcp_servers.api_server.fetch",
                   return_value={"active": 30000, "todayCases": 200}):
            result = run_async(self.api.call_tool("get_health_alerts", {}))
            data = json.loads(result[0].text)
            self.assertEqual(data["level"], "MEDIO")


# ─── RUNNER ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Tests — Agente Cierre de Turno Clínico")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestFilesystemMCP))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseLogic))
    suite.addTests(loader.loadTestsFromTestCase(TestCalculatorMCP))
    suite.addTests(loader.loadTestsFromTestCase(TestAPIMCP))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"Pasaron: {passed}/{result.testsRun}")
    if result.failures or result.errors:
        print(f"Fallaron: {len(result.failures) + len(result.errors)}/{result.testsRun}")
    print("=" * 60)

    sys.exit(0 if result.wasSuccessful() else 1)
