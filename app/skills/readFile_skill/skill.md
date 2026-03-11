---
name: read_file
description: 读取指定路径文件内容
entrypoint: app.skills.readFile_skill.readFile:read_file
---
输入参数 `file_path`，返回 UTF-8 文本内容；失败时返回错误信息。
