# JobFun Web

Iteration 0.41 的 Next.js/PWA 业务客户端。当前已覆盖简历与岗位导入、证据匹配、申请推进、文字/语音面试练习、保留音频管理及安全运维导出；项目仍未连接真实基础设施或公开部署。

## 本地运行

1. 在项目根目录启动 FastAPI：

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn src.api.app:app --reload --port 8000
   ```

2. 为已有用户签发可撤销 Token：

   ```powershell
   .\.venv\Scripts\python.exe -m src.api.provision_token --user-id 1
   ```

3. 创建本地配置并启动客户端：

   ```powershell
   Copy-Item .env.example .env.local
   npm install
   npm run dev
   ```

4. 打开 `http://localhost:3000/login`，粘贴 Token。

## 安全边界

- FastAPI 地址只使用服务端 `JOBFUN_API_BASE_URL`，不得改成 `NEXT_PUBLIC_*`。
- Token 由 Next.js Route Handler 验证后写入 `HttpOnly + SameSite=Strict` Cookie。
- 浏览器业务请求只访问同源 `/api/backend/*` 白名单代理；写请求校验 Origin。
- Service Worker 不缓存 `/api/*` 响应，只缓存静态壳资源和离线页。
- 生产 HTTPS 环境必须设置 `JOBFUN_COOKIE_SECURE=true`。

## 验证

```powershell
npm run check
```

该命令依次执行 ESLint、TypeScript 和生产构建。

## Iteration 0.29 导入能力

- `/dashboard/resumes/new`：粘贴简历文本后调用 `POST /api/v1/resumes`，轮询 `GET /api/v1/operations/{operation_id}`；
- `/dashboard/jobs/new`：粘贴岗位文本后调用 `POST /api/v1/jobs`，使用相同的任务状态闭环；
- 两类写入都通过同源 BFF 和一次性 `Idempotency-Key` 提交，浏览器不读取 Bearer Token；
- 任务状态显示等待、执行、成功、失败、进度和后端自动重试次数；
- 简历文件支持 `.txt/.pdf/.zip`（最大 50 MB），岗位文件支持 `.png/.jpg/.jpeg/.webp/.pdf`（最大 20 MB）；
- `POST /api/v1/uploads/{kind}` 当前只完成账户隔离的安全暂存，尚未把对象接入解析队列；页面会明确提示用户改用文本导入来立即解析。

## Iteration 0.30 匹配能力

- `/dashboard/matches/new` 一次加载当前账户最多 100 份简历和 100 个岗位作为显式选择项；
- 用户确认组合后调用 `POST /api/v1/matches`，请求只包含正整数 `resume_id` 与 `job_id`；
- 每次提交生成新的 `Idempotency-Key`，并通过 `/operations/{operation_id}` 展示排队、执行、自动重试、失败和完成状态；
- 成功任务读取 `result_refs.match_id`，进入所选岗位详情的最新匹配报告；
- 报告展示总分与技能、经验、教育、软技能、文化契合五维证据，并明确说明分数不是录用概率；
- 匹配工作区不调用 applications 或 interview-attempts 写入端点。

## Iteration 0.31 申请能力

- 匹配完成后通过 `/dashboard/applications/new?job_id=...&resume_id=...&match_id=...` 进入申请确认页；
- 服务端重新读取当前账户的岗位和简历，并要求 `match_id` 仍是岗位最新报告；最终资源关系继续由 FastAPI 校验；
- 创建前必须确认岗位、简历版本和匹配报告，`POST /applications` 初始状态固定为 `saved`；
- 申请详情通过 `PATCH /applications/{id}` 更新，客户端只发送实际变化字段；
- 状态选择严格遵循后端状态机，不允许从“已收藏”直接跳到面试或 Offer；
- 备注通过 `note` 追加，不覆盖历史内容；下一步最多 500 字符，日期统一转换为 `YYYY-MM-DD HH:MM`；
- 所有创建和更新请求使用独立 `Idempotency-Key`，且不调用 interview-attempts。

## Iteration 0.32 文字面试练习

- 申请详情提供 `/dashboard/applications/{id}/interview` 入口，题目、历史次数和洞察均来自当前用户拥有的申请与匹配关系；
- FastAPI 新增 `GET /applications/{id}/interview-questions` 和 `GET /interview-attempts/{id}`，API 版本升级为 `0.26.0`；
- 题目只读响应不返回参考答案，作答详情也不返回服务器音频路径或转写内部字段；
- 文字回答只调用 `POST /interview-attempts`，包含申请、题目和回答文本，并使用独立 `Idempotency-Key`；
- 页面轮询 `/operations/{operation_id}`，成功后从 `result_refs.attempt_id` 读取本次评估；
- 复盘展示完整性、真实性、技术正确性和表达结构四维分数，以及总结、优势、改进项、待核实表达和下一次练习建议；
- 12,000 字符上限和题目归属在客户端提供即时反馈，最终所有权与关系校验仍由 FastAPI 执行；
- 390px 手机宽度下题目、回答与复盘自动单列，避免中文内容在窄栏中被过度拆分；
- 本轮明确不访问麦克风，不调用音频上传，也不迁移语音转写。

## Iteration 0.33 受控语音练习

- 文字/语音回答使用同一题目、同一申请上下文和同一四维评价标准；
- 只有用户勾选音频处理同意后，录音和文件选择才可用；麦克风权限只在点击“开始录音”时请求；
- 支持 `.flac/.mp3/.mp4/.mpeg/.mpga/.m4a/.ogg/.wav/.webm`，最大 10 MB，WAV 最长 5 分钟由后端校验；
- 音频通过私有对象存储上传，HTTP 响应不再暴露内部 `object_key`；
- `POST /interview-transcriptions` 创建独立异步转写任务，草稿通过用户隔离的详情接口读取；
- 转写草稿可修改，24 小时后失效；用户必须明确确认内容后才能提交评价；
- 原音频默认在转写完成后立即删除。主动保留时会持续保存，直到用户调用删除接口或删除账户；
- `DELETE /uploads/{object_id}` 提供当前用户范围内的原音频删除路径；
- 语音评价记录只公开“语音转写”和“音频是否保留”，不公开音频路径或内部转写字段；
- FastAPI 版本升级为 `0.27.0`，Web 包版本升级为 `0.33.0`。

## Iteration 0.34 生产运行准备

- Worker 支持 `--watch --limit 5 --poll-interval 2` 持续轮询，并在空闲时继续更新心跳；
- `/health/worker` 只返回心跳年龄、队列数量、最老排队时间、停滞任务和安全累计计数；
- 心跳缺失/过期、队列积压、运行任务停滞或 Worker 错误状态时返回 HTTP 503；
- `JOBFUN_LOG_FORMAT=json` 启用字段白名单的 JSON 日志，不记录用户 ID、任务正文、简历、回答、转写或密钥；
- 任务只有在耗尽重试并最终失败时才触发可选 Webhook，告警正文不包含用户数据；
- 告警未配置时使用空实现，不发起网络请求；告警发送失败不改变任务状态；
- 运行阈值和告警配置已加入根目录 `.env.example`；
- 详细启动、健康检查、告警、事故处理、备份恢复和发布门禁见 `docs/operations-runbook.md`；
- FastAPI 版本升级为 `0.28.0`，Web 包版本升级为 `0.34.0`。

## Iteration 0.35 私有预发布验收包

- `python -m src.ops.preflight --strict` 以安全字段检查预发布配置，输出不包含 DSN、Bucket 名或任何密钥；
- `python -m src.ops.verify_health --base-url <API origin>` 只读验证 live、ready 和 worker 三个健康契约；
- `infra/staging` 提供只绑定本机端口的 PostgreSQL 与私有 MinIO 模板，但不会自动启动或清理；
- `docs/staging-release-rehearsal.md` 定义合成数据冒烟、Worker 崩溃、队列积压和隔离恢复演练；
- FastAPI HTTP 契约未改变，版本保持 `0.28.0`；Web 迭代标记升级为 `0.35.0`；
- 当前仅完成验收工具与文档，真实 PostgreSQL、S3、告警通道和公开部署仍未执行。

## Iteration 0.36 保留音频自动到期与批量删除

- 主动保留的面试原音频默认最多保存 30 天，使用 `JOBFUN_RETAINED_AUDIO_MAX_DAYS` 在 1–365 天内配置；
- `/dashboard/audio` 只展示当前账户已关联面试记录的保留音频，不公开对象键、校验和或服务器路径；
- 页面支持全选和批量删除，删除请求通过同源 BFF，其他用户对象按“不存在”处理；
- 删除对象后同步清空面试记录中的音频引用，历史评价继续保留，但不会继续显示“原音频已保留”；
- `python -m src.api.run_audio_retention --limit 100` 按到期时间进行有界清理，可安全重复执行；
- 清理失败保留元数据供下一次重试，日志只记录安全错误码，不记录用户、文件名或对象键；
- FastAPI 版本升级为 `0.29.0`，Web 包版本升级为 `0.36.0`。

## Iteration 0.37 清理计划任务监控

- 新增 `maintenance_runs` 非用户数据表，记录音频清理的开始/完成时间、上次扫描/删除/失败数量、累计数量和连续失败；
- `/health/maintenance` 返回计划、运行时和连续失败三个安全检查，不包含用户、文件名、对象键或回答内容；
- 未运行、超过最大间隔、运行超时或连续失败达到阈值时返回 HTTP 503；单次失败返回 warning 和 HTTP 200；
- 连续失败首次达到 `JOBFUN_AUDIO_CLEANUP_FAILURE_THRESHOLD` 时发送一次安全 Webhook，后续失败不重复轰炸；
- 音频管理页展示最近运行、上次扫描、累计删除和连续失败状态，不显示用户级明细；
- `src.ops.verify_health` 现在同时验证 live、ready、worker 和 maintenance 四个健康契约；
- FastAPI 版本升级为 `0.30.0`，Web 包版本升级为 `0.37.0`。

## Iteration 0.38 清理历史趋势与策略审计

- 每次完成的音频清理新增一条非用户运行记录，最多保留最近 90 条；
- `/health/maintenance` 和音频管理页展示最近 12 次成功率、扫描、删除与失败趋势；
- 运行记录只包含任务状态、时间和聚合数量，不包含用户、文件名、对象键或回答内容；
- 清理任务首次读取保留天数时建立基线，之后仅在天数真实变化时写入审计事件；
- 策略审计只保存旧天数、新天数、时间和 `configuration` 来源，不保存配置值之外的环境信息；
- 音频管理页展示最近运行记录和最近五次策略变更，已有列表与批量删除能力保持不变；
- FastAPI 版本升级为 `0.31.0`，Web 包版本升级为 `0.38.0`。

## Iteration 0.39 维护数据导出与历史边界

- `JOBFUN_MAINTENANCE_HISTORY_MAX_ROWS` 将每个维护任务的历史上限配置为 12–1000 条，默认 90；
- 新上限会在下一次清理完成时执行裁剪，不影响累计计数和策略审计；
- `python -m src.ops.export_maintenance` 将安全维护数据以 JSON 输出到终端；
- 使用 `--output <path>` 可创建导出文件，但不会覆盖已经存在的文件；
- 导出包含当前任务状态、运行历史和保留策略变更，不包含用户、文件名、对象键、回答或音频内容；
- 发布前配置门禁会校验历史上限；FastAPI HTTP 契约保持 `0.31.0`，Web 迭代标记升级为 `0.39.0`。

## Iteration 0.40 维护导出完整性与离线验证

- 维护导出升级为 schema v2，并附带确定性 JSON 的 SHA-256 校验和；
- `python -m src.ops.verify_maintenance_export <file>` 可在不连接数据库的情况下验证文件；
- 验证同时检查校验和、严格字段结构、数量边界、时间格式和敏感字段禁用清单；
- 超过 10 MB、非 UTF-8、无效 JSON、未知版本或不支持的算法均被拒绝；
- 校验和用于发现损坏和普通篡改，不作为带密钥的来源签名；
- FastAPI HTTP 契约保持 `0.31.0`，Web 迭代标记升级为 `0.40.0`。

## Iteration 0.41 可选导出认证与密钥轮换

- `--authenticate` 使用配置的 active key 为维护导出增加 HMAC-SHA256 来源认证；
- 导出只记录非敏感 `key_id`，密钥使用 32–64 字节随机值的 Base64 表示，并只从环境 keyring 读取；
- `--require-authentication` 可让离线验证拒绝仅有普通校验和的导出；
- keyring 可同时保存新旧密钥：active key 用于新导出，旧 key ID 继续验证历史导出；
- 发布门禁校验 active key、keyring、Base64 和密钥长度，但不输出密钥内容；
- FastAPI HTTP 契约保持 `0.31.0`，Web 迭代标记升级为 `0.41.0`。
