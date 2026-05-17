# Frontend Conventions (Angular)

## Project Structure
```
/src/app
  /features          # 功能模組（sop, cpnt, failed）
    /[feature]
      /components    # 該功能的 UI 元件
      /services      # 該功能的 API 呼叫
      /models        # 型別定義
  /shared            # 跨功能共用元件
  /core              # 全域服務、guards、interceptors
```

## Naming
- 元件：`[feature]-[purpose].component.ts`（`cpnt-list.component.ts`）
- 服務：`[feature].service.ts`（`cpnt.service.ts`）
- 模型/介面：PascalCase（`CpntDetail`、`SopSummary`）

## Component Rules
- 使用 `OnPush` change detection 策略
- 避免直接操作 DOM；使用 Angular 的 binding 機制
- 每個功能模組有自己的 routing module

## Services
- API 呼叫集中在 service 層，不在 component 內直接使用 HttpClient
- 使用 `Observable`；不將 Observable 轉為 Promise
- 錯誤處理用 `catchError` 在 service 層統一處理

## Template
- 廠區選擇器（Fab selector）為共用元件，放在 `/shared`
- 表格分頁統一使用共用分頁元件
- 搜尋表單使用 Reactive Forms

## Types
- 所有 API response 都有對應的 TypeScript interface
- 使用 `Fab` type（union of fab codes）而非 string
