# Azure Release Pipeline Task 監控規格

## 目標

建立一個 Python 終端機監控工具，用來即時顯示 Azure release pipeline 中 release 與 task 的執行狀態。

此版本採用 mock-first 設計，先定義資料流、監控行為與終端機輸出格式，不直接綁定真實 Azure DevOps REST API endpoint。

## 使用情境

使用者需要監控一個或多個 release。每個 release 可能包含多個 task，例如：

- release name: `test_release`
- tasks: `task-A`, `task-B`

如果某個 task 依賴或觸發另一個 task，監控畫面必須把 dependency task 展開顯示在原 task 下方。

範例：

- `task-A` 的狀態資料指出它有 dependency task：`task-B`
- 監控畫面需顯示 `task-A`
- 同時在 `task-A` 下方縮排顯示 `task-B`

## Mock 資料介面

### Release task 清單

`release_info` 用來表示目前要監控的 release 與初始 task。

```python
release_info = [
    (rls_id, rls_name, task_id, task_name),
]
```

欄位說明：

- `rls_id`: release ID
- `rls_name`: release 名稱
- `task_id`: task ID
- `task_name`: task 名稱

範例：

```python
release_info = [
    (1, "test_release", 101, "task-A"),
]
```

### Task 狀態查詢

`get_release_task_info(task_id)` 用來查詢指定 task 的目前狀態，以及是否有 dependency task。

```python
def get_release_task_info(task_id):
    return {
        "status": "InProgress",
        "dependency_task_id": 102,
        "dependency_task_name": "task-B",
    }
```

回傳欄位說明：

- `status`: task 目前狀態，例如 `NotStarted`, `InProgress`, `Succeeded`, `Failed`
- `dependency_task_id`: dependency task ID；若無 dependency，回傳 `None`
- `dependency_task_name`: dependency task 名稱；若無 dependency，回傳 `None`

## 監控行為

監控工具需定期輪詢 mock API，並更新終端機畫面。

基本流程：

1. 讀取 `release_info`，取得要監控的 release 與初始 task。
2. 對每個 task 呼叫 `get_release_task_info(task_id)`。
3. 顯示 release name、task name 與 task status。
4. 如果 task 有 dependency task，額外查詢 dependency task 狀態。
5. 在原 task 下方縮排顯示 dependency task。
6. 每次輪詢後重新整理畫面，反映最新狀態。

## 終端機輸出格式

```text
===== Monitoring =====
test_release - task-A : InProgress
             |_task-B : InProgress
test_release_2 - ...
```

格式要求：

- 第一行固定顯示 `===== Monitoring =====`
- release 的主要 task 顯示為 `{release_name} - {task_name} : {status}`
- dependency task 顯示在下一行，使用縮排與 `|_` 表示階層關係
- 多個 release 依序列出

## 錯誤處理

如果 mock API 查詢失敗，監控工具不應中斷整體監控流程。

建議顯示方式：

```text
===== Monitoring =====
test_release - task-A : Error
```

錯誤狀態需可被後續輪詢更新覆蓋。

## 測試情境

- 單一 release、單一 task，無 dependency。
- 單一 release，`task-A` 有 dependency `task-B`。
- 多個 release 同時監控。
- dependency task 狀態改變時，終端機輸出同步更新。
- mock API 回傳失敗時，畫面顯示 `Error`，但不中斷其他 release 或 task 的監控。

## 範圍

本文件只定義監控行為規格，不包含 Python 程式實作。

後續實作時可先使用 mock function 驗證資料流與終端機輸出，再接入真實 Azure DevOps API。
