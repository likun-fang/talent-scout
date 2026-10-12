#!/bin/zsh
cd -- "${0:A:h:h}" || exit 1
python3 scripts/setup_openalex.py
print '\nPress Enter to close this window.'
read -r
