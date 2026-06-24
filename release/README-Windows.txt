Better CoolPC - Windows 下載版
================================

【使用方式】
1. 將整個 ZIP 解壓縮到任意資料夾（例如 D:\BetterCoolPC）
2. 雙擊 Launch-BetterCoolPC.bat 啟動
3. 程式會自動開啟瀏覽器；若未自動開啟，請手動前往：
   http://127.0.0.1:5000
4. 關閉黑色命令列視窗即可結束服務

【系統需求】
- Windows 10 / 11（64 位元）
- 可連線至原價屋網站（coolpc.com.tw）
- 建議安裝 Chromium、Google Chrome 或 Microsoft Edge 其中之一

【注意事項】
- 請勿只複製 BetterCoolPC.exe，必須保留 _internal 資料夾
- 本下載版已內建 Python 與相依套件，不需另外安裝 Python
- 菜單與篩選偏好儲存在瀏覽器本機，與原價屋無關

【自訂瀏覽器路徑（選用）】
若系統找不到瀏覽器，可在啟動前設定環境變數：
COOLPC_CHROMIUM_PATH=C:\路徑\chrome.exe

【問題排除】
- 防火牆詢問時請允許本機連線
- 若 5000 埠被占用，可設定 COOLPC_PORT=5001 後再啟動
