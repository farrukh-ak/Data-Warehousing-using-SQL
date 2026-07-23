"""
RUN PIPELINE
------------
Runs the full Bronze -> Silver -> Gold pipeline in order.

Usage:
    python run_pipeline.py
"""

import sys
import time
sys.path.insert(0, "scripts")

import importlib


def run():
    stages = [
        ("Bronze", "01_bronze"),
        ("Silver", "02_silver"),
        ("Gold", "03_gold"),
    ]

    start = time.time()
    for name, module_name in stages:
        print(f"\n{'=' * 50}")
        print(f"Running {name} stage")
        print("=" * 50)
        module = importlib.import_module(module_name)
        module.run()

    elapsed = time.time() - start
    print(f"\n{'=' * 50}")
    print(f"Pipeline complete in {elapsed:.2f}s")
    print("=" * 50)


if __name__ == "__main__":
    run()
