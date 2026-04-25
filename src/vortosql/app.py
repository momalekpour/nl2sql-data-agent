import random
from typing import Any

import yaml

from vortosql.core.logger import Logger
from vortosql.pipeline.nl2sql_pipeline import NL2SQLPipeline

logger = Logger(__name__)

DEPARTMENTS = [
    "Engineering",
    "Sales",
    "Marketing",
]


class NL2SQLApp:
    def __init__(self, config_path: str = "config.yaml", department: str | None = None):
        with open(config_path) as f:
            config = yaml.safe_load(f)

        self._department = (
            department if department in DEPARTMENTS else random.choice(DEPARTMENTS)
        )  # fallback only
        logger.log("info", "DEPARTMENT_SELECTED", {"department": self._department})

        self._schema_guardrails: dict[str, list[str]] = {
            "Employee": ["*"],
            "Certification": ["*"],
            "Benefits": ["*"],
        }
        self._row_guardrails: dict[str, dict[str, Any]] = {
            "Employee": {"Department": self._department}
        }
        self._fk_guardrails: dict[str, dict[str, str]] = {
            "Certification": {
                "fk_column": "EmployeeId",
                "ref_table": "Employee",
                "ref_column": "EmployeeId",
            },
            "Benefits": {
                "fk_column": "EmployeeId",
                "ref_table": "Employee",
                "ref_column": "EmployeeId",
            },
        }
        self._pipeline = NL2SQLPipeline(config=config["nl2sql_pipeline"])

    @property
    def department(self) -> str:
        return self._department

    def ask(self, user_question: str) -> dict[str, Any]:
        return self._pipeline.execute(
            user_question=user_question,
            schema_guardrails=self._schema_guardrails,
            row_guardrails=self._row_guardrails,
            fk_guardrails=self._fk_guardrails,
        )
