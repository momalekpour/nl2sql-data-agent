from typing import Union

from nl2sql_data_agent.core.database.database_handler import DBMS
from nl2sql_data_agent.core.model_manager import ModelProvider, OllamaModel, OpenAIModel
from pydantic import BaseModel, confloat, model_validator

from nl2sql_data_agent.pipeline.example_selector import ExampleSelectionTechnique
from nl2sql_data_agent.pipeline.schema_linker import SchemaLinkingTechnique
from nl2sql_data_agent.pipeline.sql_corrector import SQLCorrectionPromptTemplate
from nl2sql_data_agent.pipeline.sql_generator import SQLGenerationPromptTemplate


class SchemaLinkerConfig(BaseModel):
    db_file_path: str
    technique: SchemaLinkingTechnique
    model_provider: ModelProvider | None = None
    model_name: Union[OllamaModel, OpenAIModel] | None = None

    @model_validator(mode="after")
    def validate_technique_fields(self):
        if self.technique in (SchemaLinkingTechnique.TCSL, SchemaLinkingTechnique.SCSL):
            if not self.model_provider or not self.model_name:
                raise ValueError(
                    "model_provider and model_name are required for TCSL/SCSL techniques"
                )
        return self


class ExampleSelectorConfig(BaseModel):
    technique: ExampleSelectionTechnique
    number_of_examples: int
    embedding_model_provider: ModelProvider | None = None
    embedding_model_name: Union[OllamaModel, OpenAIModel] | None = None
    random_seed: int | None = None

    @model_validator(mode="after")
    def validate_technique_fields(self):
        if self.technique == ExampleSelectionTechnique.QUESTION_SIMILARITY:
            if not self.embedding_model_provider or not self.embedding_model_name:
                raise ValueError(
                    "embedding_model_provider and embedding_model_name are required for QUESTION_SIMILARITY technique"
                )
        return self


class SQLGeneratorConfig(BaseModel):
    prompt_template: SQLGenerationPromptTemplate
    chat_completion_model_provider: ModelProvider
    chat_completion_model_name: Union[OllamaModel, OpenAIModel]
    temperature: confloat(ge=0, le=2)
    random_seed: int | None


class SQLCorrectorConfig(BaseModel):
    prompt_template: SQLCorrectionPromptTemplate
    max_correction_attempts: int
    dbms: DBMS
    chat_completion_model_provider: ModelProvider
    chat_completion_model_name: Union[OllamaModel, OpenAIModel]
    temperature: confloat(ge=0, le=2)
    random_seed: int | None


class NL2SQLPipelineConfig(BaseModel):
    schema_linker: SchemaLinkerConfig
    example_selector: ExampleSelectorConfig
    sql_generator: SQLGeneratorConfig
    sql_corrector: SQLCorrectorConfig
