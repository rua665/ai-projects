#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理/恢复隐藏会话 v2.0 —— 交互式管理已从 VS Code 侧栏删除（隐藏）的 Claude Code 会话。

双击 exe 启动后进入命令循环，输入命令管理隐藏会话。

交互命令：
  删除模式（默认）：
    --all              列出全部可删除会话（全目录扫描）
    --dir <项目路径>    列出指定项目的可删除会话（路径含空格可不加引号）
    --ad               删除全部可删除会话（需输入 Y 确认）
    --d1,2,3           删除指定编号会话（基于上次清单，需输入 Y 确认）
    --d                引导模式：提示输入要删除的编号
  恢复模式（restore 进入 / del 返回）：
    --all              列出全部可恢复会话
    --dir <项目路径>    列出指定项目的可恢复会话
    --ar               恢复全部可恢复会话（免确认）
    --r1,2,3           恢复指定编号会话（基于上次清单）
    --r                引导模式：提示输入要恢复的编号
  通用：
    restore            切换到恢复模式
    del                切换回删除模式
    help               显示用法
    q / exit           退出程序

命令行参数预填：启动时传入的命令会立即执行，然后进入交互界面。如：
  清理隐藏会话.exe --dir D:\\web tool\\ai\\contest
  清理隐藏会话.exe --restore
  清理隐藏会话.exe --ad

安全性设计：
  - 只处理 hiddenSessionIds 中记录的会话，未删除的会话绝不动；
  - memory/ 目录永不匹配（会话 ID 为 UUID，不会撞上 memory）；
  - 正在运行的活跃会话一律跳过；
  - 删除模式删除前必须输入 Y 二次确认，操作不可逆。
"""

import os
import sys
import json
import glob
import re
import shutil
import sqlite3
import subprocess
import uuid
from collections import deque
from datetime import datetime

# ---------- 常量 ----------
VSCDB = os.path.expanduser(r"~\AppData\Roaming\Code\User\globalStorage\state.vscdb")
PROJECTS = os.path.expanduser(r"~\.claude\projects")
SESSIONS_DIR = os.path.expanduser(r"~\.claude\sessions")
VSC_KEY = "Anthropic.claude-code"
BANNER = "=" * 62


class Options:
    mode = "delete"      # delete | restore
    startup_cmds = []    # 启动时自动执行的命令列表
    help = False


def setup_console():
    """Windows 下切到 UTF-8 代码页，保证中文正常显示"""
    if sys.platform == "win32":
        try:
            os.system("chcp 65001 >nul 2>&1")
        except Exception:
            pass
        for stream in (sys.stdout, sys.stderr, sys.stdin):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def show_banner():
    print(BANNER)
    print("  清理隐藏会话工具 v2.0")
    print("  功能：永久删除 / 恢复已从 VS Code 侧栏删除（隐藏）的对话")
    print("  安全：未删除的对话 / 正在运行的对话绝不动")
    print(BANNER)
    print("  交互命令：--all 全局清单 | --dir <路径> 指定项目 | --ad 删除全部")
    print("            --d1,2,3 删除编号 | --d 引导删除 | --ar 恢复全部")
    print("            --r1,2,3 恢复编号 | --r 引导恢复 | restore/del 切换模式")
    print("            help 帮助 | q/exit 退出")


def print_help():
    print(BANNER)
    print("  清理隐藏会话工具 用法")
    print(BANNER)
    print("  删除模式（默认）")
    print("    --all               列出全部可删除会话（全目录扫描）")
    print("    --dir <项目路径>     列出指定项目的可删除会话（路径含空格可不加引号）")
    print("    --ad                删除全部可删除会话（需输入 Y 确认）")
    print("    --d1,2,3            删除指定编号会话，如 --d1 --d2 --d1,3,5（需 Y 确认）")
    print("    --d                 引导模式：提示输入要删除的编号")
    print()
    print("  恢复模式（restore 进入 / del 返回）")
    print("    --ar                恢复全部可恢复会话（免确认）")
    print("    --r1,2,3            恢复指定编号会话，如 --r1 --r2 --r1,3,5（免确认）")
    print("    --r                 引导模式：提示输入要恢复的编号")
    print()
    print("  通用")
    print("    restore             切换到恢复模式")
    print("    del                 切换回删除模式")
    print("    help                显示本帮助")
    print("    q / exit            退出程序")
    print()
    print("  命令行参数预填：启动时传入的命令会立即执行后进入交互界面，")
    print('    如：清理隐藏会话.exe --dir "D:\\web tool\\ai\\contest"')
    print()


def pause_exit():
    """错误退出前的暂停，管道/重定向输入下优雅跳过"""
    try:
        input("按回车键退出...")
    except (EOFError, KeyboardInterrupt):
        pass


def show_help():
    print_help()
    pause_exit()


def parse_args(argv):
    """解析命令行参数，返回 Options。命令收集到 startup_cmds 作为启动预填。"""
    opts = Options()
    cmds = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--help", "-h"):
            opts.help = True
        elif arg == "--restore":
            opts.mode = "restore"
        elif arg == "--preview":
            print("[提示] v2.0 起取消 --preview 参数：交互式界面天然带预览（列清单确认后才删除）。")
        elif arg == "--dir":
            parts = []
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                parts.append(argv[i])
                i += 1
            if not parts:
                print("[错误] --dir 缺少路径参数。示例：--dir \"<项目路径>\"")
                print("       （--help 查看完整用法）")
                pause_exit()
                sys.exit(1)
            cmds.append("--dir " + " ".join(parts))
            continue
        elif arg in ("--all", "--ad", "--d", "--ar", "--r"):
            cmds.append(arg)
        elif re.fullmatch(r"--[dr]\d[\d,]*", arg):
            cmds.append(arg)
        elif arg in ("restore", "del"):
            cmds.append(arg)
        else:
            print(f"[错误] 未知参数：{arg}")
            print("       （--help 查看完整用法）")
            pause_exit()
            sys.exit(1)
        i += 1
    opts.startup_cmds = cmds
    return opts


def process_exists(name=None, pid=None):
    """通过 tasklist 判断进程是否存在（name 或 pid 二选一）"""
    try:
        if pid is not None:
            cmd = ["tasklist", "/FI", f"PID eq {pid}"]
        else:
            cmd = ["tasklist", "/FI", f"IMAGENAME eq {name}"]
        out = subprocess.run(
            cmd, capture_output=True, text=True, encoding="gbk", errors="replace"
        ).stdout
        if pid is not None:
            return str(pid) in out
        return name.lower() in out.lower()
    except Exception:
        return False


def get_active_session_ids():
    """读取 ~/.claude/sessions/*.json，返回进程仍存活的活跃会话 ID 集合"""
    active = set()
    for f in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            sid = d.get("sessionId")
            if not sid:
                continue
            if process_exists(pid=d.get("pid")):
                active.add(sid)
        except Exception:
            continue
    return active


def get_session_title(path):
    """从 jsonl 尾部读取会话标题：custom-title 优先，ai-title 备用"""
    title = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = deque(f, maxlen=500)
    except Exception:
        return "（读取失败）"
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = d.get("type")
        if t == "custom-title":
            v = d.get("customTitle")
            if v:
                title = v
        elif t == "ai-title" and title is None:
            v = d.get("aiTitle")
            if v:
                title = v
    return title or "（无标题）"


def fmt_time(ts):
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "未知"


def is_valid_uuid(s):
    """校验是否为合法会话 ID（UUID 格式），防止误匹配其它文件"""
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError):
        return False


def read_hidden_ids():
    """从 VS Code 状态库读取 hiddenSessionIds"""
    if not os.path.exists(VSCDB):
        print(f"[错误] 未找到 VS Code 状态库：{VSCDB}")
        print("请确认已安装 VS Code 的 Claude Code 扩展。")
        pause_exit()
        sys.exit(1)
    try:
        conn = sqlite3.connect(VSCDB)
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key=?", (VSC_KEY,)
        ).fetchone()
        conn.close()
        if not row:
            print("[错误] 未找到 Claude Code 状态数据，可能尚未使用过扩展。")
            pause_exit()
            sys.exit(1)
        data = json.loads(row[0])
        return data, set(data.get("hiddenSessionIds", []))
    except Exception as e:
        print(f"[错误] 读取 VS Code 状态库失败：{e}")
        pause_exit()
        sys.exit(1)


def write_hidden_ids(data):
    """写回 hiddenSessionIds（需 VS Code 已关闭，否则可能被占用）"""
    conn = sqlite3.connect(VSCDB)
    try:
        conn.execute(
            "UPDATE ItemTable SET value=? WHERE key=?",
            (json.dumps(data), VSC_KEY),
        )
        conn.commit()
    finally:
        conn.close()


def scan_one(directory, hidden, active, proj_name):
    """扫描单个目录下的隐藏会话，返回 [(project, sid, title, mtime, path)]"""
    res = []
    for f in os.listdir(directory):
        if not f.endswith(".jsonl"):
            continue
        sid = f[:-6]
        if sid not in hidden or not is_valid_uuid(sid):
            continue
        if sid in active:
            continue
        path = os.path.join(directory, f)
        res.append((proj_name, sid, get_session_title(path), os.path.getmtime(path), path))
    return res


def project_dir_name(path):
    """把项目路径转成 Claude Code 的会话目录名。
    规则：路径统一为 / 分隔并去末尾斜杠，ASCII 字母数字保留，其余字符替换为 -，整体小写。
    如 D:\\web tool\\ai\\contest → d--web-tool-ai-contest
    """
    norm = path.replace("\\", "/").rstrip("/")
    out = []
    for ch in norm.lower():
        if "a" <= ch <= "z" or "0" <= ch <= "9":
            out.append(ch)
        else:
            out.append("-")
    return "".join(out)


def resolve_project_dir(dir_path):
    """把用户输入的 --dir 值解析为 ~/.claude/projects/ 下的会话目录。
    支持三种输入：
      1. 项目路径，如 D:\\web tool\\ai\\contest（自动转换匹配）
      2. 会话目录完整路径，如 C:\\Users\\rua\\.claude\\projects\\d--web-tool-ai-contest
      3. 会话目录名，如 d--web-tool-ai-contest
    返回 (会话目录绝对路径, 项目名)；匹配不到返回 (None, None)。
    """
    projects_abs = os.path.normpath(os.path.abspath(PROJECTS))
    if os.path.isdir(dir_path):
        abs_in = os.path.abspath(dir_path).rstrip("\\/")
        if os.path.normpath(os.path.dirname(abs_in)) == projects_abs:
            return abs_in, os.path.basename(abs_in)
    name = project_dir_name(dir_path)
    cand = os.path.join(PROJECTS, name)
    if os.path.isdir(cand):
        return cand, name
    return None, None


def scan_all(hidden, active, dir_path):
    """按范围扫描，返回 (found, missing, dir_label)。
    指定目录模式下 missing 恒为空（无法确认全局文件状态）。"""
    found = []
    missing = set()
    dir_label = ""
    if dir_path:
        scan_path, proj_name = resolve_project_dir(dir_path)
        if not scan_path or not os.path.isdir(scan_path):
            print(f"[错误] 无法定位项目对应的会话目录：{dir_path}")
            print(f"       已尝试匹配：{os.path.join(PROJECTS, project_dir_name(dir_path))}")
            print("       请确认输入的是项目路径（如 D:\\web tool\\ai\\contest），")
            print("       或已存在的会话目录名。")
            return found, missing, dir_label
        found = scan_one(scan_path, hidden, active, proj_name)
        dir_label = f"指定项目：{dir_path} → {scan_path}"
    else:
        missing = hidden - active
        for proj_dir in sorted(os.listdir(PROJECTS)):
            full = os.path.join(PROJECTS, proj_dir)
            if not os.path.isdir(full):
                continue
            found.extend(scan_one(full, hidden, active, proj_dir))
        found_ids = {x[1] for x in found}
        missing -= found_ids
        dir_label = "全目录扫描（所有项目）"
    return found, missing, dir_label


def show_list(found, missing, dir_label, action_label, skip_missing=False):
    """展示清单，返回是否有待处理项"""
    print()
    if found:
        print(f"以下 {len(found)} 个会话已被删除（隐藏），文件仍存在，{action_label}：")
        print("-" * 62)
        for i, (proj, sid, title, mtime, _path) in enumerate(found, 1):
            print(f"[{i}] {title}")
            print(f"     项目：{proj}")
            print(f"     最后活动：{fmt_time(mtime)}")
            print(f"     ID：{sid}")
        print("-" * 62)
        print(f"[信息] 当前扫描范围：{dir_label}")
    else:
        print("[信息] 没有找到文件仍存在的隐藏会话。")

    if missing and not skip_missing:
        print(f"\n[提示] 另有 {len(missing)} 个隐藏会话的文件已被系统清理（历史遗留），")
        print("       运行删除程序将一并把它们从隐藏列表中移除（不影响任何文件）。")
    return bool(found)


def delete_sessions(found):
    """执行删除，返回 (deleted_ids, failed_list)"""
    deleted = []
    failed = []
    print()
    for proj, sid, title, _mtime, path in found:
        try:
            os.remove(path)
            session_dir = os.path.join(os.path.dirname(path), sid)
            if os.path.isdir(session_dir):
                shutil.rmtree(session_dir, ignore_errors=True)
            deleted.append(sid)
            print(f"[已删除] {title}  （项目：{proj}）")
        except Exception as e:
            failed.append((proj, sid, str(e)))
            print(f"[失败]   {title}  （{proj}）：{e}")
    return deleted, failed


def parse_indices(text):
    """解析 '1,3,5' → [1, 3, 5]"""
    out = []
    for part in text.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def confirm(action_desc):
    """二次确认（支持 help 类输入），返回是否确认"""
    while True:
        choice = input(f"输入 Y 确认{action_desc}；输入 help 查看用法；其他任意字符取消：").strip()
        if choice.lower() in ("--help", "-h", "help", "?", "/?"):
            print_help()
            print()
            continue
        return choice.upper() == "Y"


def check_vscode_closed():
    """执行删除/恢复前检测 VS Code 是否关闭，未关闭返回 False"""
    if process_exists(name="Code.exe"):
        print("\n[警告] 检测到 VS Code 正在运行！")
        print("为保证会话隐藏列表能安全更新，请先完全关闭 VS Code 再执行此操作。")
        print("（可先输入 --all 查看清单，关闭 VS Code 后再执行删除/恢复）")
        return False
    return True


def scan_and_show(state, dir_path):
    """按当前模式扫描并列出清单，结果存入 state"""
    print()
    data, hidden = read_hidden_ids()
    active = get_active_session_ids()
    found, missing, dir_label = scan_all(hidden, active, dir_path)
    if state["mode"] == "delete":
        show_list(found, missing, dir_label, "将被永久删除")
    else:
        show_list(found, set(), dir_label, "可恢复显示", skip_missing=True)
    state["found"] = found
    state["missing"] = missing
    state["dir"] = dir_path
    state["scanned"] = True


def do_delete_all(state):
    """--ad：删除全部可删除会话"""
    if state["mode"] != "delete":
        print("[提示] 当前为恢复模式，删除命令不可用。输入 del 切回删除模式。")
        return
    print()
    print("[操作] 删除全部可删除会话")
    data, hidden = read_hidden_ids()
    active = get_active_session_ids()
    found, missing, dir_label = scan_all(hidden, active, None)
    state["found"] = found
    state["missing"] = missing
    state["dir"] = None
    state["scanned"] = True
    show_list(found, missing, dir_label, "将被永久删除")
    if not found and not missing:
        print("\n没有可删除的会话。")
        return
    if not check_vscode_closed():
        return
    print()
    print("[警告] 此操作不可逆！删除后无法恢复，请确认清单无误。")
    if not confirm("永久删除全部会话"):
        print("\n已取消，未做任何更改。")
        return
    deleted, failed = delete_sessions(found)
    if deleted or missing:
        remove_ids = set(deleted) | missing
        data["hiddenSessionIds"] = [s for s in hidden if s not in remove_ids]
        try:
            write_hidden_ids(data)
            print(f"\n[信息] 隐藏列表已更新，移除了 {len(remove_ids)} 个条目。")
        except Exception as e:
            print(f"\n[警告] 隐藏列表更新失败：{e}")
            print("       会话文件已删除，残留条目不影响使用。")
    print()
    print(BANNER)
    print(f"  删除成功：{len(deleted)} 个会话")
    print(f"  删除失败：{len(failed)} 个会话")
    if failed:
        for proj, sid, e in failed:
            print(f"    - {proj}/{sid}: {e}")
    if missing:
        print(f"  隐藏列表清理：移除 {len(missing)} 个历史遗留条目")
    print(BANNER)
    state["found"] = [x for x in found if x[1] not in set(deleted)]
    state["missing"] = set()
    state["scanned"] = bool(state["found"])


def do_delete_indices(state, indices):
    """--d1,2,3：按编号删除（基于上次清单，需 Y 确认）"""
    if state["mode"] != "delete":
        print("[提示] 当前为恢复模式，删除命令不可用。输入 del 切回删除模式。")
        return
    found = state["found"]
    if not state["scanned"] or not found:
        print("[提示] 还没有清单。请先输入 --all 或 --dir <项目路径> 查看可删除会话。")
        return
    valid = [i for i in indices if 1 <= i <= len(found)]
    if not valid:
        print(f"[提示] 没有有效的编号。可用范围：1 - {len(found)}")
        return
    selected = [found[i - 1] for i in valid]
    print()
    print(f"以下 {len(selected)} 个会话将被永久删除：")
    print("-" * 62)
    for i, (proj, sid, title, _mtime, _path) in enumerate(selected, 1):
        print(f"[{i}] {title}")
        print(f"     项目：{proj}")
    print("-" * 62)
    if not check_vscode_closed():
        return
    print()
    if not confirm("删除所选会话"):
        print("\n已取消，未做任何更改。")
        return
    deleted, failed = delete_sessions(selected)
    remove_ids = set(deleted)
    try:
        data, hidden = read_hidden_ids()
        data["hiddenSessionIds"] = [s for s in hidden if s not in remove_ids]
        write_hidden_ids(data)
        print(f"\n[信息] 隐藏列表已更新，移除了 {len(remove_ids)} 个条目。")
    except Exception as e:
        print(f"\n[警告] 隐藏列表更新失败：{e}")
        print("       会话文件已删除，残留条目不影响使用。")
    print(f"\n删除成功：{len(deleted)} 个，失败：{len(failed)} 个。")
    state["found"] = [x for x in found if x[1] not in remove_ids]


def do_delete_guided(state):
    """--d：引导模式，逐个输入要删除的编号"""
    if state["mode"] != "delete":
        print("[提示] 当前为恢复模式，删除命令不可用。输入 del 切回删除模式。")
        return
    if not state["scanned"] or not state["found"]:
        print("[提示] 还没有清单。请先输入 --all 或 --dir <项目路径> 查看可删除会话。")
        return
    print()
    print("进入部分删除模式。输入编号（逗号分隔，如 1,3,5）后回车；直接回车返回。")
    while True:
        raw = input("> ").strip()
        if raw.lower() in ("help", "--help", "-h", "?", "/?"):
            print_help()
            continue
        if not raw:
            print("已返回。")
            return
        indices = parse_indices(raw)
        if indices:
            do_delete_indices(state, indices)
            return
        print("[提示] 请输入有效编号，如 1,3,5。")


def do_restore_all(state):
    """--ar：恢复全部可恢复会话（免确认）"""
    if state["mode"] != "restore":
        print("[提示] 当前为删除模式，恢复命令不可用。输入 restore 切换到恢复模式。")
        return
    print()
    print("[操作] 恢复全部可恢复会话")
    data, hidden = read_hidden_ids()
    active = get_active_session_ids()
    found, _missing, dir_label = scan_all(hidden, active, None)
    state["found"] = found
    state["dir"] = None
    state["scanned"] = True
    show_list(found, set(), dir_label, "将恢复显示", skip_missing=True)
    if not found:
        print("\n没有可恢复的会话。")
        return
    if not check_vscode_closed():
        return
    restore_ids = [x[1] for x in found]
    try:
        data["hiddenSessionIds"] = [s for s in hidden if s not in restore_ids]
        write_hidden_ids(data)
        print(f"\n[已恢复] {len(restore_ids)} 个会话，刷新/重启 VS Code 侧栏后即可看到。")
    except Exception as e:
        print(f"\n[警告] 恢复失败：{e}")
        print("       请确认 VS Code 已关闭后重试。")
    state["found"] = []
    state["scanned"] = False


def do_restore_indices(state, indices):
    """--r1,2,3：按编号恢复（基于上次清单，免确认）"""
    if state["mode"] != "restore":
        print("[提示] 当前为删除模式，恢复命令不可用。输入 restore 切换到恢复模式。")
        return
    found = state["found"]
    if not state["scanned"] or not found:
        print("[提示] 还没有清单。请先输入 --all 或 --dir <项目路径> 查看可恢复会话。")
        return
    valid = [i for i in indices if 1 <= i <= len(found)]
    if not valid:
        print(f"[提示] 没有有效的编号。可用范围：1 - {len(found)}")
        return
    selected = [found[i - 1] for i in valid]
    restore_ids = [x[1] for x in selected]
    print()
    print(f"将恢复 {len(restore_ids)} 个会话：")
    print("-" * 62)
    for i, (proj, sid, title, _mtime, _path) in enumerate(selected, 1):
        print(f"[{i}] {title}")
        print(f"     项目：{proj}")
    print("-" * 62)
    if not check_vscode_closed():
        return
    data, hidden = read_hidden_ids()
    try:
        data["hiddenSessionIds"] = [s for s in hidden if s not in restore_ids]
        write_hidden_ids(data)
        print(f"\n[已恢复] {len(restore_ids)} 个会话，刷新/重启 VS Code 侧栏后即可看到。")
    except Exception as e:
        print(f"\n[警告] 恢复失败：{e}")
        print("       请确认 VS Code 已关闭后重试。")
    state["found"] = [x for x in found if x[1] not in restore_ids]


def do_restore_guided(state):
    """--r：引导模式，逐个输入要恢复的编号"""
    if state["mode"] != "restore":
        print("[提示] 当前为删除模式，恢复命令不可用。输入 restore 切换到恢复模式。")
        return
    if not state["scanned"] or not state["found"]:
        print("[提示] 还没有清单。请先输入 --all 或 --dir <项目路径> 查看可恢复会话。")
        return
    print()
    print("进入部分恢复模式。输入编号（逗号分隔，如 1,3,5）后回车；直接回车返回。")
    while True:
        raw = input("> ").strip()
        if raw.lower() in ("help", "--help", "-h", "?", "/?"):
            print_help()
            continue
        if not raw:
            print("已返回。")
            return
        indices = parse_indices(raw)
        if indices:
            do_restore_indices(state, indices)
            return
        print("[提示] 请输入有效编号，如 1,3,5。")


def handle_command(state, cmd):
    """分发一条交互命令"""
    mode = state["mode"]
    if cmd in ("--help", "help", "-h", "?", "/?"):
        print_help()
        return
    if cmd == "--all":
        scan_and_show(state, None)
        return
    if cmd.startswith("--dir "):
        path = cmd[6:].strip()
        if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
            path = path[1:-1]
        scan_and_show(state, path)
        return
    if cmd == "--ad":
        do_delete_all(state)
        return
    if cmd == "--d":
        do_delete_guided(state)
        return
    if re.fullmatch(r"--d\d[\d,]*", cmd):
        do_delete_indices(state, parse_indices(cmd[3:]))
        return
    if cmd == "--ar":
        do_restore_all(state)
        return
    if cmd == "--r":
        do_restore_guided(state)
        return
    if re.fullmatch(r"--r\d[\d,]*", cmd):
        do_restore_indices(state, parse_indices(cmd[3:]))
        return
    if cmd in ("restore", "res"):
        if mode == "restore":
            print("[提示] 当前已在恢复模式。")
        else:
            state["mode"] = "restore"
            state["found"] = []
            state["missing"] = set()
            state["scanned"] = False
            print("已切换到恢复模式。输入 del 切回删除模式；先输入 --all 或 --dir <路径> 查看可恢复会话。")
        return
    if cmd == "del":
        if mode == "delete":
            print("[提示] 当前已在删除模式。")
        else:
            state["mode"] = "delete"
            state["found"] = []
            state["missing"] = set()
            state["scanned"] = False
            print("已切换到删除模式。")
        return
    print(f"未知命令：{cmd}（输入 help 查看用法）")


def shell_run(mode="delete", startup_cmds=None):
    """交互式主循环"""
    state = {"mode": mode, "found": [], "missing": set(), "dir": None, "scanned": False}
    print()
    print("输入 help 查看用法；q / exit 退出。提示符会显示当前模式：[删除] 或 [恢复]。")
    if startup_cmds:
        for c in startup_cmds:
            print(f"\n>>> 执行启动命令：{c}")
            handle_command(state, c)
    while True:
        prompt = "[删除] > " if state["mode"] == "delete" else "[恢复] > "
        try:
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if not raw:
            continue
        if raw.lower() in ("q", "exit", "quit"):
            print("再见！")
            break
        handle_command(state, raw)


def main():
    setup_console()
    opts = parse_args(sys.argv[1:])

    if opts.help:
        show_help()
        sys.exit(0)

    show_banner()
    shell_run(mode=opts.mode, startup_cmds=opts.startup_cmds)


if __name__ == "__main__":
    main()
