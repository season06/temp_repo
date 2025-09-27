#!/bin/bash

# 持續執行 `db.runCommand("ping")`，直到 MongoDB 回應 `ok: 1`
while true; do
  PING_RESULT=$(mongosh "mongodb://mongodb:27017/test" --quiet --eval 'db.runCommand("ping").ok' || echo 0)
  if [ "$PING_RESULT" -eq 1 ]; then
    echo "MongoDB 已啟動"
    break
  fi
  echo "MongoDB 尚未就緒，等待 1 秒..."
  sleep 1
done

# replica set 初始化
init_replica_set() {
  echo "MongoDB 副本集未初始化，執行 rs.initiate()..."
  mongosh "mongodb://mongodb:27017/admin" --quiet --eval "rs.initiate({_id: 'rs0', members: [{ _id: 0, host: 'mongodb:27017' }]})"
}

init_replica_set

# 檢查副本集狀態
STATUS=$(mongosh "mongodb://mongodb:27017/admin" --quiet --eval "rs.status().ok")
# 驗證 STATUS 是否為有效整數，避免 replica set 未初始化
if ! [[ "$STATUS" =~ ^[0-9]+$ ]]; then
  echo "MongoDB 副本集狀態無效 ($STATUS)，設置為 0"
  STATUS=0
fi

if [ "$STATUS" -eq 0 ]; then
  init_replica_set
else
  echo "MongoDB 副本集已初始化，無需執行 rs.initiate()。"
fi


echo "========= MongoDB init Script ========="
mongosh "mongodb://mongodb:27017/admin" /docker-entrypoint-initdb.d/mon-init.js

# 正常退出
exit 0