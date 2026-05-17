# Tech Stack

## Frontend
- Angular (latest stable) with TypeScript
- 使用 Angular CLI 管理專案
- 元件樣式使用 SCSS

## Backend
- Golang
- RESTful API 設計
- Sidecar Adapter 模式整合 Python SDK（Oracle DB 存取）

## Infrastructure
- 本地開發: Docker Compose
- 生產環境: Kubernetes
- 服務以容器化方式部署

## Database
- Oracle DB（公司內部共用基礎建設，非自行架設）
- 透過 Sidecar Adapter 以 plain SQL 存取特定 table
- 不使用 ORM；所有查詢皆為原生 SQL

## Other
- Python sidecar 作為 Oracle SDK 橋接層，開放 HTTP 端口供後端串接
