#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python eda_analysis_v3.py
python run_full_forecast_v3.py
