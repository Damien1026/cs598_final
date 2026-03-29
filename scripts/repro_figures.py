#!/usr/bin/env python3
"""Regenerate evaluation console output for the report (tables / copy-paste)."""
import subprocess
import sys


def main() -> None:
    root = __file__.rsplit("scripts", 1)[0]
    exe = sys.executable
    subprocess.run([exe, "-m", "eval.run_synthetic"], cwd=root, check=True)
    subprocess.run([exe, "-m", "eval.run_practical"], cwd=root, check=True)


if __name__ == "__main__":
    main()
