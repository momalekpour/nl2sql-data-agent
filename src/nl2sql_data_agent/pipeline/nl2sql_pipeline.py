import time
from datetime import datetime
from typing import Any

import yaml

from nl2sql_data_agent.core.logger import Logger
from nl2sql_data_agent.pipeline.config import NL2SQLPipelineConfig
from nl2sql_data_agent.pipeline.example_selector import ExampleSelector
from nl2sql_data_agent.pipeline.intent_guardrail import IntentGuardrail
from nl2sql_data_agent.pipeline.operator import Operator
from nl2sql_data_agent.pipeline.schema_linker import SchemaLinker
from nl2sql_data_agent.pipeline.sql_corrector import SQLCorrector
from nl2sql_data_agent.pipeline.sql_executor import SQLExecutor
from nl2sql_data_agent.pipeline.sql_generator import (
    SQLGenerator,
    SQLGenerationPromptTemplate,
)

logger = Logger(__name__)


class NL2SQLPipeline:
    def __init__(self, config: dict[str, Any]):
        self.config = NL2SQLPipelineConfig(**config)
        self.operators = self.build(self.config)

    @staticmethod
    def build(config: NL2SQLPipelineConfig) -> list[Operator]:
        operators = list()

        operators.append(IntentGuardrail(config=config.intent_guardrail.model_dump()))
        operators.append(SchemaLinker(config=config.schema_linker.model_dump()))
        if (
            config.sql_generator.prompt_template
            != SQLGenerationPromptTemplate.ZERO_SHOT
        ):
            operators.append(
                ExampleSelector(config=config.example_selector.model_dump())
            )
        operators.append(SQLGenerator(config=config.sql_generator.model_dump()))
        if config.sql_corrector.max_correction_attempts > 0:
            operators.append(SQLCorrector(config=config.sql_corrector.model_dump()))
        operators.append(SQLExecutor(config=config.sql_executor.model_dump()))

        return operators

    def execute(
        self,
        user_question: str,
        accessible_schema: dict[str, list[str]] | None = None,
        row_guardrails: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        context = {
            "user_question": user_question,
            "accessible_schema": accessible_schema,
            "row_guardrails": row_guardrails,
        }
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_time = time.time()
        for operator in self.operators:
            operator.execute(context)
            if context.get("pipeline_early_stop"):
                break
        end_time = time.time()
        context["pipeline_latency"] = end_time - start_time
        context["timestamp"] = timestamp
        return context


if __name__ == "__main__":
    # ad-hoc testing
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    pipeline = NL2SQLPipeline(config=config["nl2sql_pipeline"])

    result = pipeline.execute(
        user_question="What is the name of the employee with the highest salary?",
        accessible_schema={"Employee": ["*"]},
        row_guardrails={"Employee": {"Department": "Engineering"}},
    )

    print(f"Generated SQL : {result.get('sql_generator_sql_query')}")
    print(f"Executed SQL  : {result.get('sql_executor_sql_query')}")
    print(f"Rows          : {result.get('sql_executor_rows')}")
    print(f"Latency       : {result['pipeline_latency']:.2f}s")
