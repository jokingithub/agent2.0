---
name: read_file
description: 读取当前 session 目录内指定路径文件内容（禁止访问 session 外）
metadata:
  entrypoint: app.skills.readFile_skill.readFile:read_file
---
输入参数 `file_path`，支持相对路径（相对 `sessions/<session_id>/`）；返回 UTF-8 文本内容；失败时返回错误信息。
