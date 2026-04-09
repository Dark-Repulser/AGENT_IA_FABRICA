"""
logger.py — Logging estructurado JSON para el Agente Clínico
Uso:
    from logger import get_logger
    log = get_logger("database")
    log.info("query ejecutada", query="SELECT ...", rows=15)
    log.error("conexión fallida", error=str(e), host="localhost")
"""
import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone


# Campos internos de LogRecord que NO se pueden sobreescribir vía extra={}
# Si algún campo del usuario colisiona, se le agrega el prefijo "f_"
_LOGRECORD_RESERVED = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname",
    "filename", "module", "exc_info", "exc_text", "stack_info",
    "lineno", "funcName", "created", "msecs", "relativeCreated",
    "thread", "threadName", "processName", "process", "taskName",
    "message", "asctime",
    # parámetros propios de BoundLogger._log que no deben pasarse como fields
    "level",
})

# Claves que el JSONFormatter ya incluye en el entry base — no duplicar
_JSON_SKIP = frozenset({
    "timestamp", "level", "logger", "pid", "message",
    "exception",
})


def _safe_extra(fields: dict) -> dict:
    """
    Renombra cualquier clave que colisione con campos reservados de LogRecord
    añadiéndole el prefijo 'f_'  (ej: name → f_name, level → f_level).
    """
    return {
        (f"f_{k}" if k in _LOGRECORD_RESERVED else k): v
        for k, v in fields.items()
    }


class JSONFormatter(logging.Formatter):
    """Formatea cada log record como una línea JSON."""

    # Atributos internos de LogRecord que NO queremos en el JSON de salida
    _INTERNAL = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "taskName",
        "message", "asctime",
    })

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level":     record.levelname,
            "logger":    record.name,
            "pid":       os.getpid(),
            "message":   record.getMessage(),
        }

        # Campos extra inyectados vía extra={}
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in self._INTERNAL:
                continue
            if key not in _JSON_SKIP:
                entry[key] = value

        # Excepción si existe
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            entry["exception"] = record.exc_text

        return json.dumps(entry, ensure_ascii=False, default=str)


class BoundLogger:
    """
    Logger con campos fijos (context binding).
    Uso: log = get_logger("db").bind(server="database", host="localhost")
         log.info("conectado")   → incluye server y host en cada línea
    """

    def __init__(self, logger: logging.Logger, **context):
        self._logger = logger
        self._context = context

    def bind(self, **kwargs) -> "BoundLogger":
        return BoundLogger(self._logger, **{**self._context, **kwargs})

    # Parámetros propios de _log que no pueden venir en **fields
    _OWN_PARAMS = frozenset({"level", "message"})

    def _log(self, level: int, message: str, **fields):
        safe_fields = {
            (f"f_{k}" if k in self._OWN_PARAMS else k): v
            for k, v in fields.items()
        }
        extra = _safe_extra({**self._context, **safe_fields})
        self._logger.log(level, message, extra=extra)

    def debug(self, message: str, **fields):
        self._log(logging.DEBUG, message, **fields)

    def info(self, message: str, **fields):
        self._log(logging.INFO, message, **fields)

    def warning(self, message: str, **fields):
        self._log(logging.WARNING, message, **fields)

    def error(self, message: str, **fields):
        self._log(logging.ERROR, message, **fields)

    def critical(self, message: str, **fields):
        self._log(logging.CRITICAL, message, **fields)

    def exception(self, message: str, **fields):
        """Loguea ERROR + traceback actual automáticamente."""
        fields["exception"] = traceback.format_exc()
        self._log(logging.ERROR, message, **fields)


# ── Configuración global (se ejecuta una sola vez) ──────────────────────────

def _setup_root_handler() -> None:
    root = logging.getLogger()

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root.setLevel(level)

    # Evitar agregar handlers duplicados si ya fueron registrados por este módulo
    existing_types = {type(h) for h in root.handlers}

    if logging.StreamHandler not in existing_types:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(JSONFormatter())
        root.addHandler(sh)

    log_file = os.environ.get("LOG_FILE")
    if log_file:
        # Verificar si ya existe un FileHandler apuntando al mismo archivo
        already = any(
            isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(log_file)
            for h in root.handlers
        )
        if not already:
            os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(JSONFormatter())
            root.addHandler(fh)


_setup_root_handler()


def get_logger(name: str, **context) -> BoundLogger:
    """
    Retorna un BoundLogger listo para usar.

    Args:
        name:    Nombre del componente (p.ej. "database", "calculator").
        **context: Campos que se incluirán en todos los logs de este logger.

    Returns:
        BoundLogger con campos fijos.
    """
    return BoundLogger(logging.getLogger(name), server=name, **context)