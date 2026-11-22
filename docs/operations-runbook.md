# JobFun 生产运行手册

适用版本：Web `0.41.0`、FastAPI `0.31.0`。本手册用于部署前演练和生产运行，不代表当前项目已经公开部署。

## 1. 进程职责

JobFun 至少包含三个独立进程：

1. FastAPI：认证、用户隔离的读写契约、上传和健康检查；
2. Worker：从 `operation_jobs` 领取任务，执行解析、匹配、转写和评价；
3. Next.js：浏览器入口和同源 BFF，不直接持有数据库或 AI 密钥。

生产环境不得把 Worker 合并到 Web 请求进程。FastAPI 重启不能中断已入队任务，Worker 异常退出后任务应由队列状态和重试策略恢复。

## 2. 启动顺序

1. 配置 PostgreSQL 和私有对象存储；
2. 启动 FastAPI，并确认 `/health/live`、`/health/ready`；
3. 启动 Worker 的持续轮询模式；
4. 确认 `/health/worker` 返回 `healthy`；
5. 启动 Next.js，再执行一条非敏感测试任务。

本地演练命令：

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m src.api.run_jobs --watch --limit 5 --poll-interval 2
```

生产进程管理器应负责自动重启、标准输出采集、优雅终止和资源限制。不要使用开发模式的 `--reload`。

## 3. 必要配置

- `DATABASE_BACKEND=postgres` 和有效的 `POSTGRES_DSN`；
- `OBJECT_STORAGE_BACKEND=s3`、私有 Bucket、Region，以及可选 KMS Key；
- 文本模型密钥和仅在需要语音转写时配置的 `OPENAI_API_KEY`；
- `JOBFUN_COOKIE_SECURE=true`；
- `JOBFUN_LOG_FORMAT=json`；
- 每个 Worker 使用稳定且唯一的 `JOBFUN_WORKER_NAME`；
- 告警平台可用时配置 `JOBFUN_ALERT_WEBHOOK_URL`，认证值只放在 Secret 管理服务中。

禁止把任何密钥写入镜像、仓库、日志或前端 `NEXT_PUBLIC_*` 变量。

## 4. 健康检查

### `/health/live`

只表示 API 进程仍在运行。失败时由进程管理器立即重启。

### `/health/ready`

表示 API 配置和必要依赖是否可接收流量。返回 503 时应从负载均衡器摘除实例。

### `/health/worker`

只返回聚合运行状态，不包含用户、简历、回答或任务输入：

- `heartbeat=missing/stale`：Worker 未启动、停止轮询或数据库连接异常；
- `queue=backlogged`：最老排队任务超过 `JOBFUN_WORKER_QUEUE_MAX_AGE_SECONDS`；
- `running=stale`：运行中任务超过 `JOBFUN_WORKER_RUNNING_STALE_SECONDS` 未更新；
- `worker=error`：最近一次最终失败后 Worker 尚未完成下一轮健康轮询；
- `failed_operations_24h`：过去 24 小时最终失败数，用于趋势观察，不直接决定健康状态；
- `processed_total/failed_total`：当前 Worker 心跳记录的累计完成与最终失败计数。

任何关键检查异常时接口返回 HTTP 503。监控系统应每 30 秒检查一次，连续 3 次失败再触发值班告警，避免短暂部署抖动造成误报。

### `/health/maintenance`

只返回音频到期清理的聚合运行状态：

- `schedule=missing/stale`：尚未有成功完成记录，或距离上次完成超过 `JOBFUN_AUDIO_CLEANUP_MAX_AGE_HOURS`；
- `runtime=stale`：任务保持 running 超过 `JOBFUN_AUDIO_CLEANUP_STALE_SECONDS`；
- `failures=warning`：出现连续失败，但尚未达到告警阈值；
- `failures=alerting`：连续失败达到 `JOBFUN_AUDIO_CLEANUP_FAILURE_THRESHOLD`；
- `last_checked/last_deleted/last_failed`：最近一轮聚合计数；
- `run_total/deleted_total/failed_total`：自状态表建立后的累计计数。
- `trend`：最近 12 次完成记录的成功率与扫描/删除/失败合计；
- `recent_runs`：最近 12 次安全运行记录，不包含用户或对象明细。

missing、stale 或 alerting 返回 HTTP 503；单次失败 warning 返回 HTTP 200，便于监控展示趋势而不立即升级事件。接口不返回用户、文件名、对象键或回答内容。

## 5. 结构化日志

设置 `JOBFUN_LOG_FORMAT=json` 后，每行输出一个 JSON 对象。允许字段包括：

- `timestamp`、`level`、`logger`、`message`；
- `event`、`request_id`；
- `operation_id`、`operation_type`、`retry_count`；
- `error_type`、安全 `error_code` 和状态。

日志格式器使用字段白名单，不记录 `user_id`、请求正文、简历、面试回答、转写文本、对象键、Token 或供应商错误原文。日志平台仍应配置访问控制和保留期限。

## 6. 失败告警

只有任务耗尽重试并进入最终 `failed` 状态时才发送 Webhook。事件仅包含任务编号、任务类型、安全错误码、重试次数、级别和时间。Webhook 发送失败不会覆盖原任务状态，系统会写入 `alert_delivery_failed` 安全日志。

建议在告警平台按 `operation_type` 聚合：

- 5 分钟内同类型最终失败 ≥ 3：高优先级；
- `/health/worker` 连续 3 次 503：高优先级；
- 24 小时失败率持续升高但无积压：普通优先级，检查供应商或输入质量。

## 7. 事件处理

### Worker 心跳缺失

1. 检查 Worker 进程和最近一次退出码；
2. 检查数据库连通性和连接池；
3. 使用一次性命令 `python -m src.api.run_jobs --limit 1` 验证领取任务；
4. 恢复持续模式并确认心跳年龄下降；
5. 不要直接把所有 `running` 任务批量改为 `queued`，应先确认没有另一 Worker 正在执行。

### 队列积压

1. 查看积压的任务类型分布，但不要读取用户输入；
2. 检查 AI 供应商限流、对象存储延迟和数据库锁；
3. 在确认任务幂等后逐步增加 Worker 数量；
4. 观察最老排队年龄回落后再解除告警。

### 最终失败增加

1. 使用 `operation_id` 关联安全日志；
2. 根据 `error_type/error_code` 判断配置、依赖或代码问题；
3. 修复后让用户用新的幂等键重新提交，或通过经过审计的运维工具重排任务；
4. 不在数据库中直接修改用户结果或伪造成功状态。

## 8. 数据保护与恢复

- PostgreSQL 采用加密备份和时间点恢复；对象存储启用私有访问、服务端加密和生命周期规则；
- 数据库备份与对象存储版本的恢复时间点必须一致；
- 恢复演练应使用隔离环境和合成数据，不使用真实简历或录音；
- 回滚应用版本前确认数据库变更向后兼容；运行监控、历史和策略审计均使用独立非用户表，不改变用户业务表；
- 删除账户产生的对象清理任务必须在恢复后继续执行。

### 保留音频到期清理

主动保留的面试原音频默认最多保存 30 天，通过 `JOBFUN_RETAINED_AUDIO_MAX_DAYS` 配置，允许范围为 1–365 天。生产任务调度器应至少每日运行一次：

```powershell
.\.venv\Scripts\python.exe -m src.api.run_audio_retention --limit 100
```

命令只处理已经达到到期时间的 `interview_audio`，单次最多 1,000 条。对象删除成功后才把元数据标记为 deleted，并同步清空面试记录中的音频引用；失败项保持可重试状态，退出码为 1。输出只有 checked、deleted、failed 和 retention_days 聚合计数。

建议阈值：

- `JOBFUN_AUDIO_CLEANUP_MAX_AGE_HOURS=36`：每日任务允许 12 小时调度余量；
- `JOBFUN_AUDIO_CLEANUP_STALE_SECONDS=1800`：运行超过 30 分钟视为卡住；
- `JOBFUN_AUDIO_CLEANUP_FAILURE_THRESHOLD=2`：连续两轮失败时触发告警。

连续失败首次达到阈值时使用现有安全 Webhook 发送一次 `maintenance_failed`；事件只包含任务类型、安全错误码、扫描/删除/失败数量和连续失败数。告警投递失败不覆盖清理结果。

每轮完成后写入一条 `maintenance_run_events`，每个任务只保留最近 90 条。首次运行同时建立当前保留天数基线；以后 `JOBFUN_RETAINED_AUDIO_MAX_DAYS` 发生真实变化时，写入 `retention_policy_audit_events`。基线不会伪装成变更，重复运行相同配置也不会重复记账。两类记录均不包含用户、文件名、对象键、音频内容或环境变量原文。

历史上限可通过 `JOBFUN_MAINTENANCE_HISTORY_MAX_ROWS` 配置为 12–1000 条，默认 90。降低上限后，下一次清理任务完成时裁剪旧运行记录；累计计数和保留策略审计不会因此重置。

需要离线排查或归档时，可导出安全维护数据：

```powershell
# 输出到终端
.\.venv\Scripts\python.exe -m src.ops.export_maintenance

# 创建新文件；已有文件不会被覆盖
.\.venv\Scripts\python.exe -m src.ops.export_maintenance --output .\maintenance-export.json
```

导出文件包含版本、导出时间、当前任务状态、受上限约束的运行历史和策略变更。它不包含用户编号、文件名、对象键、回答或音频内容，但仍应按内部运行资料限制访问。

导出采用 schema v2，并包含对确定性 JSON 计算的 SHA-256 校验和。复制或归档后应离线验证：

```powershell
.\.venv\Scripts\python.exe -m src.ops.verify_maintenance_export .\maintenance-export.json
```

验证命令不连接数据库、不修改文件，也不输出文件内容。它检查文件不超过 10 MB、UTF-8 JSON、版本和字段结构、数据边界、敏感字段禁用清单以及校验和。成功返回退出码 `0`，任何损坏或不支持内容返回 `1`。SHA-256 校验和用于发现损坏和普通篡改，不是带密钥的数字签名，不能单独证明文件来源。

### 可选 HMAC 来源认证

需要验证导出来源时，在 Secret Manager 中生成 32–64 字节随机密钥并以 Base64 注入以下配置。不要把真实密钥写入仓库、命令行参数、日志或导出文件：

```text
JOBFUN_MAINTENANCE_EXPORT_ACTIVE_KEY_ID=2026-q4
JOBFUN_MAINTENANCE_EXPORT_HMAC_KEYS_JSON={"2026-q3":"<old-base64-key>","2026-q4":"<active-base64-key>"}
```

生成和验证认证导出：

```powershell
.\.venv\Scripts\python.exe -m src.ops.export_maintenance --authenticate --output .\maintenance-export.json
.\.venv\Scripts\python.exe -m src.ops.verify_maintenance_export .\maintenance-export.json --require-authentication
```

轮换步骤：

1. 先把新 key ID 和密钥加入 keyring，同时保留旧密钥；
2. 把 `JOBFUN_MAINTENANCE_EXPORT_ACTIVE_KEY_ID` 切换为新 key ID；
3. 运行严格配置门禁，并生成一个合成导出进行认证验证；
4. 在历史导出的验证期限结束后，才从 keyring 移除旧密钥；
5. 如果密钥疑似泄露，立即停止信任对应 key ID，轮换密钥并重新生成需要长期保存的导出。

HMAC 认证覆盖完整导出和普通校验和。`key_id` 可以公开用于选择验证密钥，但 Base64 密钥本身必须始终作为 Secret 管理。

用户可以在 `/dashboard/audio` 查看自己仍保留的音频并批量提前删除。接口不返回对象键、SHA-256 或其他用户的数据。

## 9. 发布前门禁

- `python -m src.ops.preflight --strict` 通过，输出中没有任何配置值或密钥；
- `npm run check` 通过；
- Python 完整测试通过，真实 PostgreSQL 契约测试在隔离测试库运行；
- `/health/live`、`/health/ready`、`/health/worker` 全部符合预期；
- `/health/maintenance` 已完成首次成功运行并符合预期；
- 告警测试发送到非生产测试通道，确认无敏感字段；
- 完成备份恢复、Worker 崩溃恢复和队列积压演练；
- 确认生产域名、HTTPS、Cookie、安全响应头和密钥轮换流程。

隔离依赖、只读健康验证、Worker 故障与备份恢复的逐步流程见 `docs/staging-release-rehearsal.md`。真实基础设施目标未确认前，不执行恢复或公开部署。
