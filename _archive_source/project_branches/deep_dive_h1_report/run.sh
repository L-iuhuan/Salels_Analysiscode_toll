#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python deep_all.py
python deep_action.py
python deep_sales_products.py
python deep_zxkx.py
python make_word.py
