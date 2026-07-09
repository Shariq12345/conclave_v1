#!/bin/bash
set -e

# Setup server URL environment variable so that conclave config respects it
if [ -n "$CONCLAVE_SERVER_URL" ]; then
    export CONCLAVE_SERVER_URL
fi

NODE_DIR="/root/.conclave"
NODE_ID_FILE="$NODE_DIR/node_id.txt"

# Perform auto-registration if files do not exist and login credentials are provided
if [ ! -f "$NODE_ID_FILE" ]; then
    if [ -n "$CONCLAVE_USERNAME" ] && [ -n "$CONCLAVE_PASSWORD" ]; then
        echo "[Conclave Node Startup] Registration files not found. Attempting to log in..."
        conclave auth login --username "$CONCLAVE_USERNAME" --password "$CONCLAVE_PASSWORD"
        
        # Build node registration command
        REG_ARGS=""
        if [ -n "$NODE_NAME" ]; then
            REG_ARGS="$REG_ARGS --name $NODE_NAME"
        fi
        if [ -n "$NODE_ORG" ]; then
            REG_ARGS="$REG_ARGS --org $NODE_ORG"
        fi
        
        echo "[Conclave Node Startup] Registering node with args: $REG_ARGS..."
        conclave node register $REG_ARGS
        echo "[Conclave Node Startup] Node successfully registered."
    else
        echo "[Conclave Node Startup] Error: Registration files not found at $NODE_ID_FILE and auto-registration credentials (CONCLAVE_USERNAME/CONCLAVE_PASSWORD) were not provided."
        echo "Please mount your ~/.conclave configuration volume or pass credentials to auto-register."
        exit 1
    fi
fi

# Load Node ID
NODE_ID=$(cat "$NODE_ID_FILE")
echo "[Conclave Node Startup] Node ID loaded: $NODE_ID"

# Run heartbeat loop
HEARTBEAT_SECS="${HEARTBEAT_INTERVAL:-10}"
echo "[Conclave Node Startup] Starting heartbeat agent with interval of $HEARTBEAT_SECS seconds..."
exec conclave node heartbeat "$NODE_ID" --interval "$HEARTBEAT_SECS"
