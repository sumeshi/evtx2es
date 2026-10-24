#!/usr/bin/fish
mkdir -p $HOME/.local/bin
fish_add_path --universal --append $HOME/.local/bin
uv sync --locked
