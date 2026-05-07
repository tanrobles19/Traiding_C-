#!/bin/bash
while true; do
  sudo sntp -sS time.apple.com >/dev/null 2>&1
  echo "test"
  sleep 60  # cada 5 minutos
done