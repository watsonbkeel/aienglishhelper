#!/usr/bin/env bash
set -euo pipefail
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
DEST=/opt/english-class-edge
ENV_SOURCE=""; MODEL_SOURCE=""
while (($#)); do
  case "$1" in
    --env) ENV_SOURCE=${2:?需要本人pi.env路径}; shift 2 ;;
    --model) MODEL_SOURCE=${2:?需要原中文Vosk模型目录}; shift 2 ;;
    *) echo '用法: sudo bash scripts/install_pi.sh --env /路径/pi.env [--model /原中文模型目录]'; exit 2 ;;
  esac
done
[[ $EUID -eq 0 && -f "$ENV_SOURCE" ]] || { echo '请使用sudo，并提供老师生成的本人pi.env'; exit 1; }
[[ ! -e "$DEST" ]] || { echo "$DEST 已存在，未覆盖；请按说明备份后升级"; exit 1; }
apt-get update
apt-get install -y python3 python3-venv alsa-utils espeak-ng ca-certificates
python3 -c 'import sys; assert sys.version_info >= (3,11), "需要64位Raspberry Pi OS和Python3.11+"'
python3 - "$SOURCE" "$DEST" <<'PY'
import shutil,sys
shutil.copytree(sys.argv[1],sys.argv[2],ignore=shutil.ignore_patterns('.git','.venv','__pycache__','.pytest_cache','var','output','sources','data','tests','tests_js','miniprogram'))
PY
python3 -m venv "$DEST/.venv"
"$DEST/.venv/bin/pip" install -r "$DEST/requirements-pi.txt"
getent passwd english-edge >/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin english-edge
usermod -a -G audio english-edge
install -d -o root -g root -m 755 /etc/english-class
install -o root -g english-edge -m 640 "$ENV_SOURCE" /etc/english-class/pi.env
mkdir -p "$DEST/models"
if [[ -n "$MODEL_SOURCE" ]]; then
  [[ -f "$MODEL_SOURCE/am/final.mdl" ]] || { echo '原中文Vosk模型目录无效'; exit 1; }
  cp -a "$MODEL_SOURCE" "$DEST/models/vosk-model-small-cn-0.22"
  chmod -R a+rX "$DEST/models/vosk-model-small-cn-0.22"
else
  "$DEST/.venv/bin/python" "$DEST/scripts/download_models.py" --language zh --dest "$DEST/models"
fi
install -m 644 "$DEST/deploy/english-edge.service" /etc/systemd/system/english-edge.service
systemctl daemon-reload
echo '已安装但尚未切换；现有aibot仍保持原状态。'
echo '先检查 /etc/english-class/pi.env 的脑端地址和USB声卡。'
echo "开启课程模式：sudo python3 $DEST/scripts/course_mode.py on"
echo "恢复原机器人：sudo python3 $DEST/scripts/course_mode.py off"
