# 文件同步規則

每次修改 `main.py` 或 `gui/gui.py` 後，**必須同步更新**以下文件：

## CLI 引數異動
- `AGENTS.md` CLI Arguments 表格（flags, defaults, descriptions）
- `README.md` Options 表格

## Env vars 異動
- `AGENTS.md` Environment Variables 表格
- `README.md` Environment Variables 表格
- `.env.example`（確保所有變數都在其中）

## 相依套件異動（import 增減）
- `requirements.txt`（runtime deps）
- `requirements-dev.txt`（dev deps）
- `AGENTS.md` Dependencies 段落
- `README.md` Installation 段落（若有新增必要套件）

## 測試數量異動
- 檢查 `tests/test_main.py` 的 test function 數量
- 更新 `AGENTS.md` Testing 段落中的計數

## Features / 架構異動
- `README.md` Features 列表
- `AGENTS.md` Architecture 段落
- `AGENTS.md` Layout 表格（若有新增目錄或檔案）

## GUI 相關異動
- 若有修改 `gui/gui.py` 或 `gui/__init__.py`，確認：
  - `README.md` Features 有列出 GUI 模式
  - `README.md` Usage 有 `--gui` 範例
  - `AGENTS.md` Commands 有 `--gui` / `-m gui.gui` 範例
  - `AGENTS.md` Architecture 有提及 GUI
 
## 驗證方式
修改完成後執行以下指令確認無迴歸：
```powershell
python -m pytest tests/ -v
python main.py --help          # 確認引數正確
python main.py --show-config   # 確認設定正確
```
