#!/bin/zsh
cd -- "${0:A:h:h}" || exit 1
python3 scripts/setup_openalex.py
print '\n按回车关闭窗口。'
read -r
