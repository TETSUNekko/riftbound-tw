# 符文戰場 台灣賽事

手機/桌面通用的單頁查詢工具，資料即時取自官方 API（`lol-api.playloltcg.com`），只列出台灣場次。

- `index.html` — 網頁版（GitHub Pages 直接開）。可用 GPS 或輸入地址，依距離／費用／人數／時間篩選排序。連不到 API 時自動改用頁面內建的資料快照。
- `lol_tw_events.py` — CLI 版：`python lol_tw_events.py "台北市信義區市府路45號"`
- `lol_tw_gui.py` — Windows 桌面版（tkinter）

場地座標由 OpenStreetMap Nominatim 預先查好內建，距離為直線距離。
