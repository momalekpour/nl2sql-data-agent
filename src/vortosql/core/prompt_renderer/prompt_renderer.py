from typing import Any

import jinja2

from vortosql.core.logger import Logger

logger = Logger(__name__)


class PromptRenderer:
    def __init__(self, templates_dir_path: str):
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(searchpath=templates_dir_path),
            undefined=jinja2.StrictUndefined,
        )
        self.template_cache: dict[str, jinja2.Template] = {}

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        try:
            template = self._load_template(f"{template_name}.jinja")
            return template.render(context)
        except Exception as e:
            logger.log(
                "error",
                "ERROR_IN_PROMPT_RENDERER",
                {"template_name": template_name, "error": str(e)},
            )
            raise

    def _load_template(self, template_file: str) -> jinja2.Template:
        if template_file not in self.template_cache:
            self.template_cache[template_file] = self.env.get_template(template_file)
        return self.template_cache[template_file]
