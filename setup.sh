#!/bin/bash
#
# Tavern Tales — Setup Script
# Run this once to install dependencies and pull the LLM model.
#

set -e

echo "🍺 Setting up Tavern Tales..."

# Create project directory
mkdir -p ~/projects/tavern_tales
cd ~/projects/tavern_tales

# Install Python dependencies
echo "Installing Python packages..."
pip install gradio ollama 2>/dev/null || pip3 install gradio ollama

# Create data directory
mkdir -p ~/.local/share/tavern_tales

# Pull Ollama model
echo "Pulling Ollama model (this may take a while on first run)..."
echo "If it fails, run manually: ollama pull qwen2.5-uncensored:14b"
ollama pull qwen2.5-uncensored:14b 2>/dev/null || echo "Warning: ollama pull failed. Make sure Ollama is running."

echo ""
echo "========================================"
echo "  Setup complete!"
echo ""
echo "  To start the server:"
echo "    cd ~/projects/tavern_tales"
echo "    python3 server.py"
echo ""
echo "  Then open: http://localhost:7860"
echo "========================================"
