# PayTrace 前端（Next.js 工作台）

> 状态：**M0a 骨架** —— 仅有占位首页。

## 技术栈（按方案 § 5.2）

- Next.js 16（stable）+ React 19 + TypeScript
- Tailwind CSS 4（CSS 优先配置）
- 使用 pnpm 作为包管理器

## 当前状态

- 最小化 `app/`：包含 `layout.tsx`、`page.tsx`、`globals.css`。
- 空的 `app/incidents/`、`app/eval/` 路由目录（M3 填充）。
- 空的 `components/`、`lib/api/`、`lib/sse/`（M0b/M2/M3 填充）。
- 尚未引入 OpenAPI 类型生成 —— M0b 接入。

## 命令

```bash
pnpm install
pnpm dev        # 在 :3000 启动开发服务器
pnpm build      # 生产构建（M0a 验收使用）
pnpm typecheck
pnpm lint
```

## 下一里程碑（M0b）

- 通过 `pnpm gen:api`（openapi-typescript）从 `backend/openapi.json`
  生成 `lib/api/schema.ts`。
- `app/page.tsx` 调用 `GET /api/v1/health/live` 并渲染返回值。
