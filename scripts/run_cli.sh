#!/bin/bash
set -a
source .env
set +a

uv run python -m vortosql.cli
