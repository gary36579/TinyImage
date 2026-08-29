# TinyImage 開發規範

本專案旨在提供一個高效的批次圖片壓縮工具，專注於在不改變圖片基本屬性（尺寸、色彩空間、元數據）的前提下，極大化地減少檔案容量。

## 核心目標 (Core Goals)
- **零損尺寸**：嚴禁在壓縮過程中變更圖片的解析度 (Width x Height)。
- **色彩保真**：必須保留 ICC 色彩設定檔 (ICC Profiles)，確保在不同顯示設備上的色彩表現一致。
- **資訊保留**：必須保留 EXIF 元數據（如拍攝時間、相機參數、GPS 資訊等）。
- **高效壓縮**：針對不同格式（JPG, PNG, WebP）採用最佳化的壓縮演算法。

## 專案架構 (Architecture)
- `input/`: 存放待處理的原始圖片（可透過 `--input` 指定其他資料夾）。
- `output/`: 存放處理完成的壓縮圖片（可透過 `--output` 指定其他資料夾）。
- `main.py`: 核心執行腳本，負責圖片遍歷與壓縮邏輯。
- `requirements.txt`: 專案依賴清單。

## 技術規範 (Technical Standards)
- **依賴庫**：主要使用 `Pillow (PIL)` 進行圖片處理。
- **支援格式**：
    - 圖片：JPEG (`.jpg`, `.jpeg`), PNG (`.png`), WebP (`.webp`)
    - 壓縮檔：ZIP (`.zip`), 7z (`.7z`)

## 壓縮檔處理規範 (Archive Handling)
- **自動處理**：腳本會自動解壓支援的檔案，優化圖片後按原路徑重新封裝。
- **加密保護**：**自動略過所有加密（需密碼）的壓縮檔**，以確保安全性。
- **壓縮策略**：
    - **JPEG**: 開啟 `optimize=True`, `progressive=True`，預設品質 `quality=80`。
    - **PNG**: 開啟 `optimize=True`，`compress_level=9` (最大無損壓縮)。
    - **WebP**: 使用 `quality=80`, `method=6` (最高效能壓縮比例)。

## 開發流程 (Workflow)
1. **圖片讀取**：使用 `Image.open` 開啟圖片。
2. **資訊提取**：提取 `icc_profile` 與 `exif` 資料。
3. **執行壓縮**：調用 `img.save()` 時帶入 `optimize=True` 及對應格式的參數，並重新寫回提取的資訊。
4. **驗證**：壓縮後需確保檔案大小確實下降，且視覺品質無明顯差異。

## 注意事項 (Notes)
- 處理大量圖片時需注意記憶體釋放，建議使用 `with` 語句確保檔案正確關閉。
- 嚴禁修改 `/input` 資料夾中的原始檔案。
- `--delete-original`：壓縮完成後永久刪除原始檔案。
- `--soft-delete-original`：壓縮完成後將原始檔案移至資源回收筒（與 `--delete-original` 互斥）。
