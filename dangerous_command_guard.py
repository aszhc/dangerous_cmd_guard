# $language = "Python3"
# $interface = "1.0"

import re
import traceback


# ============================================================
# SecureCRT 危险命令 Enter 拦截脚本
#
# 使用方法：
#   Session Options
#     -> Terminal
#     -> Emulation
#     -> Mapped Keys
#     -> Map a Key...
#     -> Enter
#     -> Run Script
#
# Arguments 留空。
#
# 工作原理：
#   1. Enter 被映射为运行本脚本
#   2. 脚本读取当前终端屏幕上的命令
#   3. 如果发现高危模式，则弹窗确认
#   4. 确认：发送真正的 "\r"
#   5. 取消：发送 Ctrl+C，不提交命令
#
# 注意：
#   这是"防误操作"工具，不是安全边界。
# ============================================================


# ------------------------------------------------------------
# 配置
# ------------------------------------------------------------

# 调试模式：
# True  = 每次按 Enter 都显示脚本识别到的命令
# False = 正常使用
DEBUG = False

# 最多向上回溯多少行，用于处理长命令自动折行
MAX_LOOKBACK_ROWS = 6

# 取消危险命令后是否再弹"已取消"提示
SHOW_CANCEL_NOTICE = False


# ------------------------------------------------------------
# Windows / SecureCRT MessageBox 常量
# ------------------------------------------------------------

MB_OK = 0
MB_YESNO = 4

MB_ICONERROR = 16
MB_ICONWARNING = 48
MB_ICONINFORMATION = 64

# 默认选择第二个按钮：
# 对 Yes/No 来说就是默认选中 No
MB_DEFBUTTON2 = 256

IDYES = 6
IDNO = 7


# ------------------------------------------------------------
# Shell Prompt 识别
#
# 目标是识别类似：
#
#   [root@server ~]# rm -rf /tmp/a
#   user@server:~$ rm -rf /tmp/a
#   bash-5.1# rm -rf /tmp/a
#   server$ rm -rf /tmp/a
#
# group(1) 必须是 prompt 后面的命令部分。
# ------------------------------------------------------------

PROMPT_PATTERNS = [

    # [root@server ~]# command
    # [user@host /tmp]$ command
    re.compile(
        r'^\[[^\r\n]*@[^\r\n]*\][#$]\s?(.*)$'
    ),

    # user@server:~$ command
    # root@server:/etc# command
    re.compile(
        r'^[^\s@]+@[^\s:]+:[^#$\r\n]*[#$]\s?(.*)$'
    ),

    # bash-5.1# command
    # bash$ command
    re.compile(
        r'^(?:bash|zsh|sh|ksh|dash)'
        r'(?:-[0-9.]+)?'
        r'[#$]\s?(.*)$',
        re.IGNORECASE
    ),

    # PostgreSQL (psql) / openGauss (gsql):
    #   postgres=# command
    #   oms=> command
    #   mydb-> command
    #   mydb*=> command
    #   user@host:5432/mydb=> command
    re.compile(
        r'^(?:[\w.@:/-]+)?[=*\!\-\(\[\'\"\$\?]{1,2}[#>]\s?(.*)$'
    ),

    # 比较宽松的 fallback：
    # server$ command
    # root# command
    re.compile(
        r'^[^#$\r\n]{0,180}[#$]\s+(.*)$'
    ),
]


# ------------------------------------------------------------
# 高危命令规则
#
# 每条规则：
#   ("提示名称", compiled regex)
# ------------------------------------------------------------

DANGEROUS_RULES = [

    # ============================================================
    # 一、文件与数据删除
    # ============================================================

    (
        "rm 删除文件",
        re.compile(r'\brm\b', re.IGNORECASE)
    ),

    (
        "truncate 将文件清零",
        re.compile(
            r'\btruncate\b'
            r'[^\r\n]*'
            r'(?:-s\s*0\b|--size(?:=|\s+)0\b)',
            re.IGNORECASE
        )
    ),

    (
        "shred 销毁文件",
        re.compile(r'\bshred\b', re.IGNORECASE)
    ),

    # ============================================================
    # 二、磁盘及文件系统破坏
    # ============================================================

    (
        "文件系统格式化 mkfs",
        re.compile(r'\bmkfs(?:\.[A-Za-z0-9_-]+)?\b', re.IGNORECASE)
    ),

    (
        "dd 直接写块设备",
        re.compile(
            r"\bdd\b"
            r"[^\r\n]*"
            r"\bof\s*=\s*[\"']?"
            r"/dev/"
            r"(?:"
            r"sd[a-z]\d*"
            r"|vd[a-z]\d*"
            r"|xvd[a-z]\d*"
            r"|nvme\d+n\d+(?:p\d+)?"
            r"|mmcblk\d+(?:p\d+)?"
            r"|mapper/[^\s;\"']+"
            r")\b",
            re.IGNORECASE
        )
    ),

    (
        "重定向直接写块设备",
        re.compile(
            r"(?:>|>>)\s*[\"']?"
            r"/dev/"
            r"(?:"
            r"sd[a-z]\d*"
            r"|vd[a-z]\d*"
            r"|xvd[a-z]\d*"
            r"|nvme\d+n\d+(?:p\d+)?"
            r"|mmcblk\d+(?:p\d+)?"
            r"|mapper/[^\s;\"']+"
            r")\b",
            re.IGNORECASE
        )
    ),

    (
        "wipefs 擦除文件系统签名",
        re.compile(
            r"\bwipefs\b"
            r"[^\r\n]*"
            r"/dev/"
            r"(?:"
            r"sd[a-z]\d*"
            r"|vd[a-z]\d*"
            r"|xvd[a-z]\d*"
            r"|nvme\d+n\d+(?:p\d+)?"
            r"|mmcblk\d+(?:p\d+)?"
            r")\b",
            re.IGNORECASE
        )
    ),

    (
        "磁盘分区操作",
        re.compile(r'\b(?:fdisk|parted|sfdisk)\b', re.IGNORECASE)
    ),

    (
        "LVM 删除操作",
        re.compile(r'\b(?:lvremove|vgremove|pvremove)\b', re.IGNORECASE)
    ),

    # ============================================================
    # 三、系统启停
    # ============================================================

    (
        "系统关机或重启",
        re.compile(r'\b(?:reboot|shutdown|halt|poweroff)\b', re.IGNORECASE)
    ),

    (
        "systemctl 关机或重启",
        re.compile(
            r'\bsystemctl\b'
            r'[^\r\n]*'
            r'\b(?:reboot|poweroff|halt)\b',
            re.IGNORECASE
        )
    ),

    (
        "init 改变运行级别",
        re.compile(r'\binit\s+[06]\b', re.IGNORECASE)
    ),

    # ============================================================
    # 四、进程控制
    # ============================================================

    (
        "kill 终止进程",
        re.compile(r'\bkill\b', re.IGNORECASE)
    ),

    (
        "pkill/killall 终止进程",
        re.compile(r'\b(?:pkill|killall)\b', re.IGNORECASE)
    ),

    # ============================================================
    # 五、账号与提权
    # ============================================================

    (
        "sudo 提权执行",
        re.compile(r'\bsudo\b', re.IGNORECASE)
    ),

    (
        "su 切换用户",
        re.compile(
            r'(?:^|(?<=[;&|])\s*)\bsu\b(?:\s|$)',
            re.IGNORECASE
        )
    ),

    (
        "新建用户 useradd",
        re.compile(r'\buseradd\b', re.IGNORECASE)
    ),

    (
        "删除用户 userdel",
        re.compile(r'\buserdel\b', re.IGNORECASE)
    ),

    (
        "修改用户属性 usermod",
        re.compile(r'\busermod\b', re.IGNORECASE)
    ),

    (
        "修改 sudoers",
        re.compile(r'\bvisudo\b', re.IGNORECASE)
    ),

    (
        "passwd 改删密码",
        re.compile(r'\bpasswd\b', re.IGNORECASE)
    ),

    (
        "批量修改密码 chpasswd",
        re.compile(r'\bchpasswd\b', re.IGNORECASE)
    ),

    # ============================================================
    # 六、防火墙清空
    # ============================================================

    (
        "iptables 清空规则",
        re.compile(
            r'\biptables\b'
            r'[^\r\n]*'
            r'(?:-F|-X)\b',
            re.IGNORECASE
        )
    ),

    (
        "iptables 设置默认放行",
        re.compile(
            r'\biptables\b'
            r'[^\r\n]*'
            r'-P\s+(?:INPUT|FORWARD|OUTPUT)\s+ACCEPT',
            re.IGNORECASE
        )
    ),

    (
        "ufw 关闭防火墙",
        re.compile(
            r'\bufw\b'
            r'[^\r\n]*'
            r'\b(?:disable|reset)\b',
            re.IGNORECASE
        )
    ),

    (
        "nft 清空规则集",
        re.compile(
            r'\bnft\b'
            r'[^\r\n]*'
            r'\bflush\s+ruleset\b',
            re.IGNORECASE
        )
    ),

    # ============================================================
    # 七、日志及历史记录篡改
    # ============================================================

    # 7.1 系统日志（/var/log/）

    (
        "vi/vim 编辑系统日志",
        re.compile(
            r'\b(?:vi|vim)\b'
            r'[^\r\n]*'
            r'/var/log/',
            re.IGNORECASE
        )
    ),

    (
        "重定向清空系统日志",
        re.compile(
            r'(?:>|>>)\s*["\x27]?/var/log/',
            re.IGNORECASE
        )
    ),

    (
        "dd 覆写日志文件",
        re.compile(
            r'\bdd\b'
            r'[^\r\n]*'
            r'\bof\s*=\s*["\x27]?'
            r'(?:'
            r'/var/log/'
            r'|[^\s;]*\.log\b'
            r')',
            re.IGNORECASE
        )
    ),

    # 7.2 普通日志文件（*.log）

    (
        "vi/vim 编辑日志文件",
        re.compile(
            r'\b(?:vi|vim)\b'
            r'[^\r\n]*'
            r'\.log\b',
            re.IGNORECASE
        )
    ),

    (
        "重定向覆写日志文件",
        re.compile(
            r'(?:>|>>)\s*["\x27]?[^\s;]*\.log\b',
            re.IGNORECASE
        )
    ),

    (
        "sed 修改日志文件",
        re.compile(
            r'\bsed\b'
            r'[^\r\n]*'
            r'-i\b'
            r'[^\r\n]*'
            r'\.log\b',
            re.IGNORECASE
        )
    ),

    # 7.3 Shell 历史记录

    (
        "清空 Shell 历史记录",
        re.compile(
            r'\bhistory\b'
            r'[^\r\n]*'
            r'-[^\r\n]*[cd]\b',
            re.IGNORECASE
        )
    ),

    (
        "禁用历史记录",
        re.compile(
            r'(?:'
            r'unset\s+HIST(?:FILE|SIZE|FILESIZE)'
            r'|HIST(?:FILE|SIZE|FILESIZE)\s*='
            r')',
        )
    ),

    # ============================================================
    # 八、审计系统破坏
    # ============================================================

    (
        "auditctl 清除审计规则",
        re.compile(
            r'\bauditctl\b'
            r'[^\r\n]*'
            r'(?:-D\b|-e\s*0\b)',
            re.IGNORECASE
        )
    ),

    (
        "停止审计服务 auditd",
        re.compile(
            r'\bsystemctl\b'
            r'[^\r\n]*'
            r'\b(?:stop|disable|mask)\b'
            r'[^\r\n]*'
            r'\bauditd\b',
            re.IGNORECASE
        )
    ),

    (
        "停止日志服务 rsyslog",
        re.compile(
            r'\bsystemctl\b'
            r'[^\r\n]*'
            r'\b(?:stop|disable|mask)\b'
            r'[^\r\n]*'
            r'\brsyslog\b',
            re.IGNORECASE
        )
    ),

    (
        "journalctl 清除历史日志",
        re.compile(
            r'\bjournalctl\b'
            r'[^\r\n]*'
            r'--vacuum',
            re.IGNORECASE
        )
    ),

    # ============================================================
    # 九、内核与安全策略
    # ============================================================

    (
        "关闭 SELinux",
        re.compile(r'\bsetenforce\s+0\b', re.IGNORECASE)
    ),

    (
        "加载内核模块 insmod",
        re.compile(r'\binsmod\b', re.IGNORECASE)
    ),

    (
        "LD_PRELOAD 环境变量劫持",
        re.compile(r'\bLD_PRELOAD\s*=')
    ),

    # ============================================================
    # 十、数据库增删改
    #
    # 支持在 Shell 命令行中直接执行的 SQL（如 mysql -e / psql -c），
    # 以及 PostgreSQL (psql) 交互控制台中的高危 SQL 检测。
    # ============================================================

    (
        "SQL 删除（DROP/TRUNCATE/DELETE）",
        re.compile(
            r'\b(?:'
            r'(?:drop|truncate)\s+(?:table|database)'
            r'|delete\s+from'
            r')\b',
            re.IGNORECASE
        )
    ),

    (
        "SQL 修改（UPDATE/ALTER）",
        re.compile(
            r'\b(?:'
            r'update\s+\S+\s+set'
            r'|alter\s+(?:table|database)'
            r')\b',
            re.IGNORECASE
        )
    ),

    (
        "SQL 新增（INSERT/CREATE）",
        re.compile(
            r'\b(?:'
            r'insert\s+into'
            r'|create\s+(?:table|database)'
            r')\b',
            re.IGNORECASE
        )
    ),

    # ============================================================
    # 十一、远程下载类
    # ============================================================

    (
        "curl 禁用",
        re.compile(r'\bcurl\b', re.IGNORECASE)
    ),

    (
        "wget 禁用",
        re.compile(r'\bwget\b', re.IGNORECASE)
    ),

    # ============================================================
    # 十二、网络抓包
    # ============================================================

    (
        "tcpdump 禁用",
        re.compile(r'\btcpdump\b', re.IGNORECASE)
    ),

    # ============================================================
    # 十三、远程连接与文件传输
    # ============================================================

    (
        "ssh 远程连接",
        re.compile(
            r'(?:^|(?<=[;&|`$\(\)])\s*|(?:sudo|nohup|exec|time|eval|command)\s+)'
            r'(?:[^\s;|\&]+?/)*'
            r'\\?'
            r'\bssh\b'
            r'(?:\s|$)',
            re.IGNORECASE
        )
    ),

    (
        "scp 远程文件传输",
        re.compile(
            r'(?:^|(?<=[;&|`$\(\)])\s*|(?:sudo|nohup|exec|time|eval|command)\s+)'
            r'(?:[^\s;|\&]+?/)*'
            r'\\?'
            r'\bscp\b'
            r'(?:\s|$)',
            re.IGNORECASE
        )
    ),

    (
        "sftp 远程文件传输",
        re.compile(
            r'(?:^|(?<=[;&|`$\(\)])\s*|(?:sudo|nohup|exec|time|eval|command)\s+)'
            r'(?:[^\s;|\&]+?/)*'
            r'\\?'
            r'\bsftp\b'
            r'(?:\s|$)',
            re.IGNORECASE
        )
    ),

    (
        "telnet 远程连接",
        re.compile(
            r'(?:^|(?<=[;&|`$\(\)])\s*|(?:sudo|nohup|exec|time|eval|command)\s+)'
            r'(?:[^\s;|\&]+?/)*'
            r'\\?'
            r'\btelnet\b'
            r'(?:\s|$)',
            re.IGNORECASE
        )
    ),

    (
        "ftp 远程文件传输",
        re.compile(
            r'(?:^|(?<=[;&|`$\(\)])\s*|(?:sudo|nohup|exec|time|eval|command)\s+)'
            r'(?:[^\s;|\&]+?/)*'
            r'\\?'
            r'\bftp\b'
            r'(?:\s|$)',
            re.IGNORECASE
        )
    ),
]


# ============================================================
# 基础函数
# ============================================================

def send_enter():
    """
    真正向远端发送 Enter。

    Screen.Send() 是直接向远端发送字符，
    不会再次触发 SecureCRT 的 Enter Key Mapping。
    """
    crt.Screen.Send("\r")


def cancel_current_input():
    """
    取消当前 shell 输入。

    Ctrl+C = ASCII 3
    """
    crt.Screen.Send(chr(3))


def get_screen_lines():
    """
    读取当前光标所在行，以及前面的若干屏幕行。

    用于解决长命令在 SecureCRT 中自动换行的问题。

    返回：
        [
            (row_number, "screen text"),
            ...
        ]
    """

    current_row = crt.Screen.CurrentRow
    columns = crt.Screen.Columns

    first_row = current_row - MAX_LOOKBACK_ROWS + 1

    if first_row < 1:
        first_row = 1

    result = []

    for row in range(first_row, current_row + 1):
        try:
            text = crt.Screen.Get(
                row,
                1,
                row,
                columns
            )

            # 只去掉屏幕右边填充的空格，
            # 不 lstrip，避免破坏实际命令。
            text = text.rstrip()

        except Exception:
            text = ""

        result.append((row, text))

    return result


def match_prompt(line):
    """
    判断某一屏幕行是不是 shell prompt 行。

    如果是：
        返回 prompt 后面的命令字符串

    如果不是：
        返回 None

    注意：
        空命令 "" 和 None 必须区分。
        "" 表示成功检测到 prompt，但用户还没输入内容。
    """

    for pattern in PROMPT_PATTERNS:
        m = pattern.match(line)

        if m:
            return m.group(1)

    return None


def get_current_command():
    """
    从屏幕内容中重建当前 shell 命令。

    例如屏幕可能是：

        [root@server ~]# very-long-command --abc ...
        --more-options rm -rf /tmp/test
                               ↑ 当前光标

    我们会向上寻找最近的 shell prompt，
    然后把后续自动折行拼起来。

    返回：
        (command, lines)

    command:
        str  -> 成功检测 shell prompt
        None -> 没检测到 shell prompt，可能处于 vim/top/less 等程序

    lines:
        原始屏幕内容，用于 DEBUG。
    """

    lines = get_screen_lines()

    # 从当前行向上找最近的 prompt
    for index in range(len(lines) - 1, -1, -1):

        line = lines[index][1]

        first_part = match_prompt(line)

        if first_part is not None:

            command = first_part

            # Prompt 后面的下一屏幕行，很可能只是终端自动折行，
            # 所以直接拼接，不额外加入空格。
            for next_index in range(index + 1, len(lines)):
                command += lines[next_index][1]

            return command.strip(), lines

    return None, lines


# ============================================================
# 危险命令检测
# ============================================================

def detect_danger(command):
    """
    检测危险命令。

    返回：
        None
            没有检测到危险模式

        "规则名称"
            命中了某条规则
    """

    if not command:
        return None

    for name, pattern in DANGEROUS_RULES:

        if pattern.search(command):
            return name

    return None


# ============================================================
# DEBUG
# ============================================================

def show_debug(command, lines, danger_reason):

    text = "SecureCRT Dangerous Command Guard DEBUG\r\n\r\n"

    text += "----- Screen -----\r\n"

    for row, line in lines:
        text += "{0}: [{1}]\r\n".format(row, line)

    text += "\r\n----- Parsed command -----\r\n"

    if command is None:
        text += "<NO SHELL PROMPT DETECTED>"
    else:
        text += "[{0}]".format(command)

    text += "\r\n\r\n----- Danger -----\r\n"

    if danger_reason:
        text += danger_reason
    else:
        text += "False"

    crt.Dialog.MessageBox(
        text,
        "DEBUG",
        MB_OK | MB_ICONINFORMATION
    )


# ============================================================
# 主逻辑
# ============================================================

def main():

    command, lines = get_current_command()

    # --------------------------------------------------------
    # 没检测到 shell prompt
    #
    # 很可能当前处于：
    #   vim
    #   less
    #   top
    #   htop
    #   nano
    #   Python REPL
    #   mysql
    #   ...
    #
    # 不做危险判断，直接保持正常 Enter 行为。
    # --------------------------------------------------------

    if command is None:

        if DEBUG:
            show_debug(
                command,
                lines,
                None
            )

        send_enter()
        return

    # --------------------------------------------------------
    # 检测危险命令
    # --------------------------------------------------------

    danger_reason = detect_danger(command)

    if DEBUG:
        show_debug(
            command,
            lines,
            danger_reason
        )

    # --------------------------------------------------------
    # 普通命令
    # --------------------------------------------------------

    if danger_reason is None:
        send_enter()
        return

    # --------------------------------------------------------
    # 高危命令
    # --------------------------------------------------------

    message = (
        "检测到可能的高危命令：\r\n"
        "\r\n"
        "    {0}\r\n"
        "\r\n"
        "命中规则：{1}\r\n"
        "\r\n"
        "是否确认执行？"
    ).format(
        command,
        danger_reason
    )

    # 4   = Yes / No
    # 48  = Warning icon
    # 256 = 默认第二个按钮，即 No
    result = crt.Dialog.MessageBox(
        message,
        "危险命令拦截 - SecureCRT",
        MB_YESNO |
        MB_ICONWARNING |
        MB_DEFBUTTON2
    )

    # --------------------------------------------------------
    # 用户明确选择 Yes
    # --------------------------------------------------------

    if result == IDYES:
        send_enter()
        return

    # --------------------------------------------------------
    # 用户选择 No / 关闭对话框
    #
    # 不发送 Enter。
    # 发送 Ctrl+C 取消当前 shell 输入。
    # --------------------------------------------------------

    cancel_current_input()

    if SHOW_CANCEL_NOTICE:

        crt.Dialog.MessageBox(
            "危险命令已取消，没有发送 Enter。",
            "SecureCRT",
            MB_OK | MB_ICONINFORMATION
        )


# ============================================================
# Fail-closed
#
# Guard 本身如果发生异常：
#
#   不！发！送！Enter！
#
# 防止：
#   脚本出错 -> 危险命令反而直接执行
# ============================================================

try:

    main()

except Exception as exc:

    error_message = (
        "危险命令保护脚本运行异常。\r\n"
        "\r\n"
        "为了安全，本次没有向远端发送 Enter。\r\n"
        "\r\n"
        "错误：\r\n"
        "{0}"
    ).format(str(exc))

    if DEBUG:

        error_message += (
            "\r\n\r\n"
            "----- traceback -----\r\n"
            "{0}"
        ).format(traceback.format_exc())

    crt.Dialog.MessageBox(
        error_message,
        "SecureCRT Dangerous Command Guard Error",
        MB_OK | MB_ICONERROR
    )
