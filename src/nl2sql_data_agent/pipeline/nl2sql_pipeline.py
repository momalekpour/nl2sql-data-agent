import time
import yaml
from datetime import datetime
from typing import List, Dict, Any

from nl2sql_data_agent.core.logger import Logger
from nl2sql_data_agent.pipeline.config import NL2SQLPipelineConfig
from nl2sql_data_agent.pipeline.example_selector import ExampleSelector
from nl2sql_data_agent.pipeline.operator import Operator
from nl2sql_data_agent.pipeline.schema_linker import SchemaLinker
from nl2sql_data_agent.pipeline.sql_corrector import SQLCorrector
from nl2sql_data_agent.pipeline.sql_generator import (
    SQLGenerator,
    SQLGenerationPromptTemplate,
)

logger = Logger(__name__)


class NL2SQLPipeline:
    def __init__(self, config: Dict[str, Any]):
        self.config = NL2SQLPipelineConfig(**config)
        self.operators = self.build(self.config)

    @staticmethod
    def build(config: NL2SQLPipelineConfig) -> List[Operator]:
        operators = list()

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

        return operators

    def execute(
        self,
        user_question: str,
        accessible_schema: dict[str, list[str]] | None = None,
    ) -> Dict[str, Any]:
        context = {
            "user_question": user_question,
            "accessible_schema": accessible_schema,
        }
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_time = time.time()
        for operator in self.operators:
            operator.execute(context)
        end_time = time.time()
        context["pipeline_latency"] = end_time - start_time
        context["timestamp"] = timestamp
        return context


if __name__ == "__main__":
    with open("scripts/config.yaml") as f:
        config = yaml.safe_load(f)

    pipeline = NL2SQLPipeline(config=config["nl2sql_pipeline"])

    result = pipeline.execute(
        user_question="What is the name of the employee with the highest salary?",
        accessible_schema={"Employee": ["*"]},
    )

    print(f"Generated SQL : {result.get('sql_generator_sql_query')}")
    print(f"Latency       : {result['pipeline_latency']:.2f}s")
