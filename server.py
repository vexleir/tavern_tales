#!/usr/bin/env python3
"""
Tavern Tales — Server Entry Point

Run on port 7860. Serves the Gradio web UI.
"""

import sys
import os

# Ensure the project directory is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web import main

if __name__ == "__main__":
    print("=" * 60)
    print("  Tavern Tales — Server")
    print("  http://localhost:7860")
    print("=" * 60)
    main()
