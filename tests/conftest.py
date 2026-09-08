import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
SKILL_ROOT = os.path.join(REPO_ROOT, "skills", "scientific-figures")
SCRIPTS = os.path.join(SKILL_ROOT, "scripts")

for path in (SCRIPTS, TESTS_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import matplotlib  # noqa: E402

matplotlib.use("Agg")
