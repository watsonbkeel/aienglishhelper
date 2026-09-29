#!/usr/bin/env bash
# First installation only. Existing aibot services/directories are never touched.
set -euo pipefail
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
DEST=/opt/english-class
DICT_SOURCE=""
while (($#)); do
  case "$1" in
    --dictionary) DICT_SOURCE=${2:?需要原fullDictionary.js路径}; shift 2 ;;
    *) echo "用法: sudo bash scripts/install_server.sh [--dictionary /路径/fullDictionary.js]" >&2; exit 2 ;;
  esac
done
[[ $EUID -eq 0 ]] || { echo '请使用sudo/root运行安装器'; exit 1; }
[[ ! -e "$DEST" ]] || { echo "$DEST 已存在。为避免覆盖你的修改，本安装器已停止。请看部署说明的升级部分。"; exit 1; }
command -v apt-get >/dev/null || { echo '自动安装器面向Debian/Ubuntu；其他系统请使用手工部署步骤'; exit 1; }
apt-get update
apt-get install -y python3 python3-venv python3-pip ffmpeg ca-certificates
python3 -c 'import sys; assert sys.version_info >= (3,11), "需要Python3.11+"'
if [[ -n "$DICT_SOURCE" ]]; then
  python3 "$SOURCE/scripts/prepare_sources.py" --dictionary "$DICT_SOURCE"
elif [[ ! -s "$SOURCE/data/dictionary.json" ]]; then
  python3 "$SOURCE/scripts/prepare_sources.py"
fi
python3 - "$SOURCE" "$DEST" <<'PY'
import shutil,sys
shutil.copytree(sys.argv[1],sys.argv[2],ignore=shutil.ignore_patterns('.git','.venv','__pycache__','.pytest_cache','var','output','sources'))
PY
python3 -m venv "$DEST/.venv"
"$DEST/.venv/bin/pip" install -r "$DEST/requirements.txt" -r "$DEST/requirements-voice.txt"
getent passwd english-public >/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin english-public
install -d -o english-public -g english-public -m 700 /var/lib/english-class
install -d -o root -g root -m 755 /etc/english-class /etc/english-class/students "$DEST/students"
install -o root -g english-public -m 640 "$DEST/deploy/public.env.example" /etc/english-class/public.env
install -m 644 "$DEST/deploy/english-public.service" /etc/systemd/system/english-public.service
install -m 644 "$DEST/deploy/english-brain@.service" /etc/systemd/system/english-brain@.service
cd "$DEST"
runuser -u english-public -- "$DEST/.venv/bin/python" -m english_class.cli --dictionary "$DEST/data/dictionary.json" --database /var/lib/english-class/class.sqlite3 init
systemctl daemon-reload
systemctl enable --now english-public.service
PUBLIC_PORT=$(sed -n 's/^PUBLIC_PORT=\([0-9]\{1,5\}\)$/\1/p' /etc/english-class/public.env | tail -1)
PUBLIC_PORT=${PUBLIC_PORT:-18090}
# 只认本服务的 /health（service=public），避免把端口上其他服务的响应当成安装成功。
HEALTH_CHECK="import urllib.request,json; d=json.load(urllib.request.urlopen('http://127.0.0.1:$PUBLIC_PORT/health',timeout=2)); assert d['ok'] and d['service']=='public'; print(json.dumps(d,ensure_ascii=False))"
ok=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if "$DEST/.venv/bin/python" -c "$HEALTH_CHECK" 2>/dev/null; then ok=1; break; fi
  sleep 1
done
[[ $ok -eq 1 ]] || { echo "公共服务未在127.0.0.1:$PUBLIC_PORT正常响应；请看 journalctl -u english-public"; exit 1; }
echo '公共数据服务已启动；这不代表真实AI/语音已经验收。'
echo '下一步：编辑 /etc/english-class/public.env 填写LLM_API_KEY；按部署说明下载语音模型，再创建学生。'
echo '原aibot没有被停止或修改。'
