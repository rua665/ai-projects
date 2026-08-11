# 清理隐藏会话工具

管理从 VS Code 侧栏删除（隐藏）的 Claude Code 会话：**永久删除文件**或**取消隐藏恢复显示**。

背景：在 VS Code 侧栏删除会话只是「隐藏」（把 sessionId 写入 VS Code 全局状态 `hiddenSessionIds`），
`.jsonl` 会话文件一直留在 `~/.claude/projects/<项目>/` 下。本工具负责真正管理这些文件。

## 快速开始

直接双击 `清理隐藏会话.exe`（Windows，无需安装 Python），进入交互式界面：

```
清理隐藏会话 v2.0
[删除] >
```

提示符显示当前模式：`[删除] >` / `[恢复] >`。

### 删除模式（默认）

| 命令 | 说明 |
|------|------|
| `--all` | 列出全部可删除会话（全目录扫描） |
| `--dir <项目路径>` | 列出指定项目会话（如 `--dir D:\web tool\ai\contest`） |
| `--ad` | 删除全部（需输入 Y 确认） |
| `--d1,2,3` | 按编号删除（需 Y 确认） |
| `--d` | 引导模式：提示输入要删除的编号 |

### 恢复模式（`restore` 进入，`del` 返回）

| 命令 | 说明 |
|------|------|
| `--ar` | 恢复全部（免确认） |
| `--r1,2,3` | 按编号恢复（免确认） |
| `--r` | 引导模式：提示输入要恢复的编号 |

### 通用

- `restore` / `del`：切换恢复 / 删除模式
- `help`：显示用法
- `q` / `exit`：退出程序

### 命令行参数预填

启动时传入的命令会立即执行，然后进入交互界面：

```
清理隐藏会话.exe --dir "D:\web tool\ai\contest"
清理隐藏会话.exe --restore
```

## 工作原理

- 隐藏列表读自 VS Code 全局状态库：`%AppData%\Roaming\Code\User\globalStorage\state.vscdb`
  （SQLite，key = `Anthropic.claude-code` 下的 `hiddenSessionIds`）
- 会话文件匹配：`~/.claude/projects/*/<session-id>.jsonl`（session-id 为 UUID）
- 删除时连带清理 `<session-id>/subagents/` 和 `<session-id>/tool-results/` 子目录
- 删除/恢复后写回 `hiddenSessionIds`，需 **VS Code 完全关闭**后才能安全写入
- 正在运行的活跃会话一律跳过，绝不误删

## 安全性

- 只处理 `hiddenSessionIds` 记录的会话，未删除的对话绝不动
- `memory/` 目录永不匹配（会话 ID 为 UUID 格式校验）
- 删除前必须输入 `Y` 二次确认（不可逆）；恢复免确认

## 文件说明

| 文件 | 说明 |
|------|------|
| `清理隐藏会话.py` | Python 源码（v2.0，交互式 CLI） |
| `清理隐藏会话.exe` | PyInstaller 打包成品（双击即用） |
| `01-项目笔记.md` | 项目开发笔记（技术踩坑与需求演进） |
| `05-使用说明.md` | 详细使用文档 |

## 从源码打包

```bash
python -m PyInstaller --onefile --console --name "清理隐藏会话" "清理隐藏会话.py"
```

## 注意

- 执行删除/恢复前必须完全关闭 VS Code，否则程序拒绝执行（列清单不需要）
- 需先「隐藏」过会话（在 VS Code 侧栏删除）才会出现在清单里
