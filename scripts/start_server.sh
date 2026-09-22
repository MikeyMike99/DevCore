#!/bin/bash
source ~/.bashrc
source ~/alp-env/bin/activate
KEY=$(grep GEMINI_API_KEY ~/.bashrc | cut -d '=' -f 2- | tr -d '"' | tr -d "'")
export GEMINI_API_KEY=$KEY
cd .. && python3 server.py
