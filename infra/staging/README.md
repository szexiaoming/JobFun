# JobFun 私有预发布环境

这个目录只提供本机或受控 CI 中的隔离依赖模板，不会自动启动容器，也不是生产部署清单。所有端口只绑定 `127.0.0.1`，MinIO Bucket 初始化后保持私有。

## 使用边界

- 只放合成测试数据，不导入真实简历、录音、Token 或生产备份；
- `.env` 不提交仓库，每次使用前更换示例密码并固定经过审核的镜像；
- 不把这里的数据卷当作备份；演练结束后按团队留存规则处理；
- 启停、清理卷和恢复操作都必须由操作者明确执行，本项目不会自动运行。

## 准备

```powershell
Copy-Item infra/staging/.env.example infra/staging/.env
# 编辑 infra/staging/.env，替换占位密码并确认镜像版本
docker compose --env-file infra/staging/.env -f infra/staging/compose.yaml config
docker compose --env-file infra/staging/.env -f infra/staging/compose.yaml up -d
```

根据 `.env` 生成应用配置，示例：

```text
JOBFUN_API_ENV=staging
DATABASE_BACKEND=postgres
POSTGRES_DSN=postgresql://jobfun_staging:<password>@127.0.0.1:55432/jobfun_staging
OBJECT_STORAGE_BACKEND=s3
S3_BUCKET=jobfun-private-staging
S3_REGION=local
S3_ENDPOINT_URL=http://127.0.0.1:59000
JOBFUN_COOKIE_SECURE=true
JOBFUN_LOG_FORMAT=json
JOBFUN_WORKER_NAME=staging-worker-01
```

复制并编辑合并配置模板，然后先运行配置门禁，再启动 API、Worker 和 Web：

```powershell
Copy-Item infra/staging/application.env.example infra/staging/application.env
.\.venv\Scripts\python.exe -m src.ops.preflight --env-file infra/staging/application.env --strict
```

启动后用显式地址执行只读健康验收：

```powershell
.\.venv\Scripts\python.exe -m src.ops.verify_health --base-url http://127.0.0.1:8000
```

完整演练顺序、备份恢复和停止条件见 [`../../docs/staging-release-rehearsal.md`](../../docs/staging-release-rehearsal.md)。

