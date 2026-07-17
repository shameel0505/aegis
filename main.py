import sys
import os

# Add src to python path so 'aegis' package is resolvable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from aegis.cli import main

if __name__ == "__main__":
    main()
