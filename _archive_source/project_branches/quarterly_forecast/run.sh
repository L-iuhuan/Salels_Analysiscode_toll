#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python run_quarterly_forecast.py
python run_customer_forecast.py
