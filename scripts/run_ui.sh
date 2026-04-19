#!/bin/bash
set -a
source .env
set +a

uv run streamlit run src/nl2sql_data_agent/ui.py
