#!/bin/bash
set -a
source .env
set +a

uv run python -m nl2sql_data_agent.cli
