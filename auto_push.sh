#!/usr/bin/env bash

# Caminho para o seu repositório
REPO_DIR="/root/scalper_dino"

cd "$REPO_DIR" || exit 1

# Puxa eventuais mudanças remotas (opcional, se houver commit direto no GitHub)
git pull origin main

# Adiciona novos arquivos e detecta modificações/exclusões
git add -A

# Só commita se houver algo para commitar
if ! git diff-index --quiet HEAD --; then
  git commit -m "Auto-update: $(date '+%Y-%m-%d %H:%M:%S')"
  git push origin main
fi
