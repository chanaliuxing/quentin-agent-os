# Headless ChatGPT/Gemini Login Guide

保存登录状态，便于 headless 脚本和自编程流程使用。建议使用方案 1（真实浏览器 + CDP 导出）。

## 方案 1：真实浏览器 + CDP 导出 storage_state.json（推荐）
1) 关闭所有 Chrome 窗口。
2) 启动带远程调试端口、独立数据目录的真实 Chrome：
```
mkdir -p /tmp/playwright_chrome_profile
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/playwright_chrome_profile
```
3) 在打开的 Chrome 窗口中手动登录 ChatGPT 或 Gemini。
4) 导出登录状态（在仓库根目录）：
```
venv/bin/python scripts/save_storage_state.py --output chatgpt_state.json
venv/bin/python scripts/save_storage_state.py --output gemini_state.json
```
5) 运行时使用：
```
venv/bin/python scripts/headless_chatgpt_research.py --query "..." --storage-state chatgpt_state.json
venv/bin/python scripts/headless_gemini_research.py  --query "..." --storage-state gemini_state.json
```
可选：导出为环境变量，便于默认加载：
```
export CHATGPT_STORAGE_STATE=/path/chatgpt_state.json
export GEMINI_STORAGE_STATE=/path/gemini_state.json
```

## 方案 2：Playwright codegen + 持久化 profile（保留指纹）
1) 准备用户目录：`mkdir -p my_profile_temp`
2) 登录并保存：
```
npx playwright codegen https://chatgpt.com --save-storage=chatgpt_state.json --user-data-dir=./my_profile_temp
npx playwright codegen https://gemini.google.com/app --save-storage=gemini_state.json --user-data-dir=./my_profile_temp
```
3) 运行时同时传 storage_state 和 user-data-dir：
```
venv/bin/python scripts/headless_chatgpt_research.py --query "..." \
  --storage-state chatgpt_state.json --user-data-dir ./my_profile_temp
```

## 方案 3：增加隐身参数/改内核（备用）
- Firefox：`npx playwright codegen https://chatgpt.com --save-storage=chatgpt_state.json --browser=firefox`
- 隐身参数：`npx playwright codegen https://chatgpt.com --save-storage=chatgpt_state.json --browser=chromium -- --disable-blink-features=AutomationControlled`

## 日常提示
- storage_state 过期时，重复方案 1 或 2 重新导出。
- 如果用 CDP 直连运行脚本，设置：`export PLAYWRIGHT_CDP_URL=http://localhost:9222`，保证打开的浏览器已登录。
- 非 headless 更易通过验证；若需要 headless，可加 `--headless` 参数或 `PLAYWRIGHT_HEADLESS=true`。
