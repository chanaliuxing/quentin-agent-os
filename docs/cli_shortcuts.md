# CLI 快捷命令

这些命令可直接用于驱动架构系统执行高层任务（编程、修改代码、测试等），按权限分两类：

## 普通权限（常规写代码，默认沙箱）
- Codex：
  ```bash
  codex exec "你的高层次任务描述"
  ```
- Claude Code：
  ```bash
  claude -p "你的高层次任务描述" --allowedTools "Bash,Edit"
  ```
- Gemini：
  ```bash
  gemini -p "你的高层次任务描述"
  ```

## 最大权限（无沙箱，需谨慎）
- Codex 无沙箱：
  ```bash
  codex exec --sandbox danger-full-access "你的高层次任务描述"
  ```

根据实际环境，确保对应 CLI 已安装并配置好认证参数。
