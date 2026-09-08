# Allows `python -m coding_best_practices_for_oss`, which the Docker action uses.
import sys

from coding_best_practices_for_oss.cli import main

if __name__ == "__main__":
    sys.exit(main())
