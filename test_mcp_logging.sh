#!/bin/bash
# Test script to show MCP server logging

echo "Starting Inspekt MCP server with verbose logging..."
echo ""

# Set logging level to DEBUG
export PYTHONUNBUFFERED=1

# Start the server (will wait for stdio input)
inspekt mcp start 2>&1 | while IFS= read -r line; do
    echo "[MCP] $line"
done
