# PayTrace 前端（Next.js 工作台）

> 状态：**M4 工程基线已实现** —— Incident 工作台、诊断 Trace 与 Eval Lab 已接入后端 API。

## 技术栈（按方案 § 5.2）

- Next.js 16（stable）+ React 19 + TypeScript
- Tailwind CSS 4（CSS 优先配置）
- 使用 pnpm 作为包管理器

## 当前状态

- `/incidents`：状态/场景筛选、分页、确定性模拟事故创建。
- `/incidents/[id]`：漏斗、诊断触发与重试、SSE 进度、报告、证据、工具 trace。
- `/eval`：B0/B1 模式选择、7 类场景、运行状态、聚合指标、badcase 与报告下载。
- `lib/api/schema.ts`：从后端 OpenAPI 契约生成的类型；`lib/api/client.ts` 统一处理请求错误。
- `@tanstack/react-query` 管理查询缓存与轮询，ECharts 负责漏斗/评测图表。

B1 会明确提示可能产生模型费用及自动回退边界；运行结果区分请求模式与配置模型，
不把请求 B1 表述为已经成功调用外部模型。

## 命令

```bash
pnpm install
pnpm dev        # 在 :3000 启动开发服务器
pnpm build      # 生产构建
pnpm typecheck
pnpm lint
```

## API 契约同步

后端路由变更后，在仓库根目录执行：

```bash
make gen-openapi
```

该命令先导出 `backend/openapi.json`，再通过 `pnpm gen:api` 更新
`lib/api/schema.ts`。浏览器端 API 地址通过 `NEXT_PUBLIC_PAYTRACE_API_BASE` 配置，
服务端渲染可使用 `PAYTRACE_API_BASE` 覆盖，默认均为 `http://localhost:8000`。
