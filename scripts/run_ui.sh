#!/bin/bash
set -a
source .env
set +a

uv run streamlit run src/vortosql/ui.py
