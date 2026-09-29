#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo '请由老师使用sudo/root运行'; exit 1; }
if [[ $# -ne 4 ]]; then
  echo '用法: sudo bash scripts/create_student.sh s001 9101 https://你的公共域名 https://你的公共域名/students/s001'; exit 2
fi
SID=$1; PORT=$2; PUBLIC_EXTERNAL=$3; BRAIN_EXTERNAL=$4
PUBLIC_PORT=$(sed -n 's/^PUBLIC_PORT=\([0-9]\{1,5\}\)$/\1/p' /etc/english-class/public.env 2>/dev/null | tail -1)
PUBLIC_PORT=${PUBLIC_PORT:-18090}
[[ $SID =~ ^[a-z][a-z0-9_-]{1,23}$ && $PORT =~ ^[0-9]+$ && $PORT -ge 1024 && $PORT -le 65535 && $PORT -ne $PUBLIC_PORT ]] || { echo 'ID或端口无效'; exit 2; }
ROOT=/opt/english-class
[[ -x "$ROOT/.venv/bin/python" ]] || { echo '请先安装服务器公共层'; exit 1; }
[[ ! -e "$ROOT/students/$SID" && ! -e "/etc/english-class/students/$SID.env" && ! -e "/root/english-class-students/$SID" ]] || { echo '该学生目录或配置已经存在，未覆盖'; exit 1; }
if grep -l -x "BRAIN_PORT=$PORT" /etc/english-class/students/*.env 2>/dev/null | grep -q .; then echo '端口已分配给其他学生'; exit 1; fi
if command -v ss >/dev/null && ss -lntH | awk '{print $4}' | grep -Eq ":${PORT}$"; then echo '端口已在监听'; exit 1; fi
install -d -o english-public -g english-public -m 700 /var/lib/english-class/provision
cd "$ROOT"
runuser -u english-public -- "$ROOT/.venv/bin/python" -m english_class.cli --dictionary "$ROOT/data/dictionary.json" --database /var/lib/english-class/class.sqlite3 add-student \
  --id "$SID" --port "$PORT" --public-url "http://127.0.0.1:$PUBLIC_PORT" --output "/var/lib/english-class/provision/$SID" --external-api-url "$PUBLIC_EXTERNAL" --brain-url "$BRAIN_EXTERNAL"
getent passwd "english-$SID" >/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin "english-$SID"
install -d -o "english-$SID" -g "english-$SID" -m 700 "$ROOT/students/$SID"
cp -a "$ROOT/english_class" "$ROOT/prompts" "$ROOT/students/$SID/"
chown -R "english-$SID:english-$SID" "$ROOT/students/$SID"
install -o root -g "english-$SID" -m 640 "/var/lib/english-class/provision/$SID/brain.env" "/etc/english-class/students/$SID.env"
install -d -m 700 /root/english-class-students
mv "/var/lib/english-class/provision/$SID" "/root/english-class-students/$SID"
chown -R root:root "/root/english-class-students/$SID"
systemctl enable --now "english-brain@$SID.service"
echo "已创建 $SID。代码：$ROOT/students/$SID；凭证导出：/root/english-class-students/$SID"
echo "添加nginx /students/$SID/ -> 127.0.0.1:$PORT/ 映射，详见部署说明。"
echo '导出的brain.env留在老师端；pi.env给对应树莓派；english-env.local.js给对应小程序。'
