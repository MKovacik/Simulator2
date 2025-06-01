#!/bin/bash

# Run script for Deutsche Telekom Tariff Simulator
# This script ensures the correct Python path is set

# Set PYTHONPATH to include the project root
export PYTHONPATH=$(pwd):$PYTHONPATH

# Run the application
python3 main.py
