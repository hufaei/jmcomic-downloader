#!/bin/zsh
# 双击此文件即可按 config.toml 中的任务开始下载。
set -e

PROJECT_DIR="${0:A:h}"
PYTHON="$PROJECT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "初始化尚未完成：找不到项目虚拟环境。"
  echo "请在终端执行：python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
  read -k 1 "?按任意键退出..."
  exit 1
fi

cd "$PROJECT_DIR"

if ! "$PYTHON" -c 'import jmcomic' 2>/dev/null; then
  echo "正在安装项目依赖（首次运行时仅需一次）..."
  "$PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt"
fi

# 只有选择 PDF 时才下载额外依赖，其他格式可立即运行。
OUTPUT_FORMAT=$("$PYTHON" -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb")).get("output", {}).get("format", "images"))' "$PROJECT_DIR/config.toml")
if [[ "$OUTPUT_FORMAT" == "pdf" ]] && ! "$PYTHON" -c 'import img2pdf' 2>/dev/null; then
  echo "正在安装 PDF 导出组件（首次使用时仅需一次）..."
  "$PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt"
fi

if ! "$PYTHON" downloader.py --config "$PROJECT_DIR/config.toml"; then
  echo
  read -k 1 "?任务未完成；按任意键退出..."
fi
