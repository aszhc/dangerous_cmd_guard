#$language = "VBScript"
#$interface = "1.0"

' SecureCRT Enter guard. Keep this file in ANSI (GBK) encoding.
' Map Enter to Run Script in Terminal / Emulation / Mapped Keys.
Option Explicit

Const DEBUG_MODE = False
Const MAX_LOOKBACK_ROWS = 6
Const SHOW_CANCEL_NOTICE = False
Const MB_OK = 0
Const MB_YESNO = 4
Const MB_ICONERROR = 16
Const MB_ICONWARNING = 48
Const MB_ICONINFORMATION = 64
Const MB_DEFBUTTON2 = 256
Const IDYES = 6

Dim arrPromptPatterns(), arrDangerousRules()

Function CreateRegExp(pattern, ignoreCase)
    Dim reg
    Set reg = CreateObject("VBScript.RegExp")
    reg.Pattern = pattern
    reg.IgnoreCase = ignoreCase
    reg.Global = False
    Set CreateRegExp = reg
End Function

Sub InitPromptPatterns()
    ReDim arrPromptPatterns(4)
    Set arrPromptPatterns(0) = CreateRegExp("^\[[^\r\n]*@[^\r\n]*\][#$]\s?(.*)$", False)
    Set arrPromptPatterns(1) = CreateRegExp("^[^\s@]+@[^\s:]+:[^#$\r\n]*[#$]\s?(.*)$", False)
    Set arrPromptPatterns(2) = CreateRegExp("^(?:bash|zsh|sh|ksh|dash)(?:-[0-9.]+)?[#$]\s?(.*)$", True)
    Set arrPromptPatterns(3) = CreateRegExp("^(?:[\w.@:/-]+)?[=*\!\-\(\['""\$\?]{1,2}[#>]\s?(.*)$", False)
    Set arrPromptPatterns(4) = CreateRegExp("^[^#$\r\n]{0,180}[#$]\s+(.*)$", False)
End Sub

Sub InitDangerousRules()
    ReDim arrDangerousRules(51)
    arrDangerousRules(0) = Array("rm 删除文件", CreateRegExp("\brm\b", True))
    arrDangerousRules(1) = Array("truncate 清空文件", CreateRegExp("\btruncate\b[^\r\n]*(?:-s\s*0\b|--size(?:=|\s+)0\b)", True))
    arrDangerousRules(2) = Array("shred 销毁文件", CreateRegExp("\bshred\b", True))
    arrDangerousRules(3) = Array("mkfs 格式化文件系统", CreateRegExp("\bmkfs(?:\.[A-Za-z0-9_-]+)?\b", True))
    arrDangerousRules(4) = Array("dd 写入块设备", CreateRegExp("\bdd\b[^\r\n]*\bof\s*=\s*[""']?/dev/(?:sd[a-z]\d*|vd[a-z]\d*|xvd[a-z]\d*|nvme\d+n\d+(?:p\d+)?|mmcblk\d+(?:p\d+)?|mapper/[^\s;""']+)\b", True))
    arrDangerousRules(5) = Array("重定向写入块设备", CreateRegExp("(?:>|>>)\s*[""']?/dev/(?:sd[a-z]\d*|vd[a-z]\d*|xvd[a-z]\d*|nvme\d+n\d+(?:p\d+)?|mmcblk\d+(?:p\d+)?|mapper/[^\s;""']+)\b", True))
    arrDangerousRules(6) = Array("wipefs 擦除文件系统签名", CreateRegExp("\bwipefs\b[^\r\n]*/dev/(?:sd[a-z]\d*|vd[a-z]\d*|xvd[a-z]\d*|nvme\d+n\d+(?:p\d+)?|mmcblk\d+(?:p\d+)?)\b", True))
    arrDangerousRules(7) = Array("fdisk/parted 修改分区", CreateRegExp("\b(?:fdisk|parted|sfdisk)\b", True))
    arrDangerousRules(8) = Array("LVM 删除卷", CreateRegExp("\b(?:lvremove|vgremove|pvremove)\b", True))
    arrDangerousRules(9) = Array("关机或重启", CreateRegExp("\b(?:reboot|shutdown|halt|poweroff)\b", True))
    arrDangerousRules(10) = Array("systemctl 关机或重启", CreateRegExp("\bsystemctl\b[^\r\n]*\b(?:reboot|poweroff|halt)\b", True))
    arrDangerousRules(11) = Array("init 切换运行级别", CreateRegExp("\binit\s+[06]\b", True))
    arrDangerousRules(12) = Array("kill 终止进程", CreateRegExp("\bkill\b", True))
    arrDangerousRules(13) = Array("pkill/killall 终止进程", CreateRegExp("\b(?:pkill|killall)\b", True))
    arrDangerousRules(14) = Array("sudo 提权执行", CreateRegExp("\bsudo\b", True))
    arrDangerousRules(15) = Array("su 切换用户", CreateRegExp("(?:^|[;&|`$\(\)]\s*)\bsu\b(?:\s|$)", True))
    arrDangerousRules(16) = Array("useradd 新建用户", CreateRegExp("\buseradd\b", True))
    arrDangerousRules(17) = Array("userdel 删除用户", CreateRegExp("\buserdel\b", True))
    arrDangerousRules(18) = Array("usermod 修改用户", CreateRegExp("\busermod\b", True))
    arrDangerousRules(19) = Array("visudo 修改 sudoers", CreateRegExp("\bvisudo\b", True))
    arrDangerousRules(20) = Array("passwd 修改密码", CreateRegExp("\bpasswd\b", True))
    arrDangerousRules(21) = Array("chpasswd 批量修改密码", CreateRegExp("\bchpasswd\b", True))
    arrDangerousRules(22) = Array("iptables 清空规则", CreateRegExp("\biptables\b[^\r\n]*-[FX]\b", True))
    arrDangerousRules(23) = Array("iptables 默认放行", CreateRegExp("\biptables\b[^\r\n]*-P\s+(?:INPUT|FORWARD|OUTPUT)\s+ACCEPT\b", True))
    arrDangerousRules(24) = Array("ufw 关闭防火墙", CreateRegExp("\bufw\b[^\r\n]*\b(?:disable|reset)\b", True))
    arrDangerousRules(25) = Array("nft 清空规则集", CreateRegExp("\bnft\b[^\r\n]*\bflush\s+ruleset\b", True))
    arrDangerousRules(26) = Array("vi/vim 编辑系统日志", CreateRegExp("\b(?:vi|vim)\b[^\r\n]*/var/log/", True))
    arrDangerousRules(27) = Array("重定向修改系统日志", CreateRegExp("(?:>|>>)\s*[""']?/var/log/", True))
    arrDangerousRules(28) = Array("dd 覆写日志文件", CreateRegExp("\bdd\b[^\r\n]*\bof\s*=\s*[""']?(?:/var/log/|[^\s;]*\.log\b)", True))
    arrDangerousRules(29) = Array("vi/vim 编辑日志文件", CreateRegExp("\b(?:vi|vim)\b[^\r\n]*\.log\b", True))
    arrDangerousRules(30) = Array("重定向修改日志文件", CreateRegExp("(?:>|>>)\s*[""']?[^\s;]*\.log\b", True))
    arrDangerousRules(31) = Array("sed 修改日志文件", CreateRegExp("\bsed\b[^\r\n]*-i\b[^\r\n]*\.log\b", True))
    arrDangerousRules(32) = Array("history 清除历史记录", CreateRegExp("\bhistory\b[^\r\n]*-[^\r\n]*[cd]\b", True))
    arrDangerousRules(33) = Array("禁用历史记录", CreateRegExp("(?:unset\s+HIST(?:FILE|SIZE|FILESIZE)|HIST(?:FILE|SIZE|FILESIZE)\s*=)", False))
    arrDangerousRules(34) = Array("auditctl 清除审计规则", CreateRegExp("\bauditctl\b[^\r\n]*(?:-D\b|-e\s*0\b)", True))
    arrDangerousRules(35) = Array("停止 auditd 审计服务", CreateRegExp("\bsystemctl\b[^\r\n]*\b(?:stop|disable|mask)\b[^\r\n]*\bauditd\b", True))
    arrDangerousRules(36) = Array("停止 rsyslog 日志服务", CreateRegExp("\bsystemctl\b[^\r\n]*\b(?:stop|disable|mask)\b[^\r\n]*\brsyslog\b", True))
    arrDangerousRules(37) = Array("journalctl 清理日志", CreateRegExp("\bjournalctl\b[^\r\n]*--vacuum", True))
    arrDangerousRules(38) = Array("关闭 SELinux", CreateRegExp("\bsetenforce\s+0\b", True))
    arrDangerousRules(39) = Array("insmod 加载内核模块", CreateRegExp("\binsmod\b", True))
    arrDangerousRules(40) = Array("LD_PRELOAD 动态库劫持", CreateRegExp("\bLD_PRELOAD\s*=", False))
    arrDangerousRules(41) = Array("SQL 删除数据或表", CreateRegExp("\b(?:(?:drop|truncate)\s+(?:table|database)|delete\s+from)\b", True))
    arrDangerousRules(42) = Array("SQL 修改数据或结构", CreateRegExp("\b(?:update\s+\S+\s+set|alter\s+(?:table|database))\b", True))
    arrDangerousRules(43) = Array("SQL 新增数据或表", CreateRegExp("\b(?:insert\s+into|create\s+(?:table|database))\b", True))
    arrDangerousRules(44) = Array("curl 下载或请求", CreateRegExp("\bcurl\b", True))
    arrDangerousRules(45) = Array("wget 下载文件", CreateRegExp("\bwget\b", True))
    arrDangerousRules(46) = Array("tcpdump 抓取网络流量", CreateRegExp("\btcpdump\b", True))
    arrDangerousRules(47) = Array("ssh 远程连接", CreateRegExp("(?:^|[;&|`$\(\)]\s*|(?:sudo|nohup|exec|time|eval|command)\s+)(?:[^\s;|/\\]+/)*\\?\bssh\b(?:\s|$)", True))
    arrDangerousRules(48) = Array("scp 远程传输文件", CreateRegExp("(?:^|[;&|`$\(\)]\s*|(?:sudo|nohup|exec|time|eval|command)\s+)(?:[^\s;|/\\]+/)*\\?\bscp\b(?:\s|$)", True))
    arrDangerousRules(49) = Array("sftp 远程传输文件", CreateRegExp("(?:^|[;&|`$\(\)]\s*|(?:sudo|nohup|exec|time|eval|command)\s+)(?:[^\s;|/\\]+/)*\\?\bsftp\b(?:\s|$)", True))
    arrDangerousRules(50) = Array("telnet 远程连接", CreateRegExp("(?:^|[;&|`$\(\)]\s*|(?:sudo|nohup|exec|time|eval|command)\s+)(?:[^\s;|/\\]+/)*\\?\btelnet\b(?:\s|$)", True))
    arrDangerousRules(51) = Array("ftp 远程传输文件", CreateRegExp("(?:^|[;&|`$\(\)]\s*|(?:sudo|nohup|exec|time|eval|command)\s+)(?:[^\s;|/\\]+/)*\\?\bftp\b(?:\s|$)", True))
End Sub

Sub SendEnter()
    crt.Screen.Send vbCr
End Sub

Sub CancelCurrentInput()
    crt.Screen.Send Chr(3)
End Sub

Function GetScreenLines()
    Dim currentRow, cols, firstRow, row, lineText, arr(), idx
    currentRow = crt.Screen.CurrentRow
    cols = crt.Screen.Columns
    If currentRow < 1 Or cols < 1 Then Err.Raise vbObjectError + 100, "GetScreenLines", "Invalid screen dimensions"
    firstRow = currentRow - MAX_LOOKBACK_ROWS + 1
    If firstRow < 1 Then firstRow = 1
    ReDim arr(currentRow - firstRow)
    idx = 0
    For row = firstRow To currentRow
        lineText = crt.Screen.Get(row, 1, row, cols)
        arr(idx) = Array(row, RTrim(lineText))
        idx = idx + 1
    Next
    GetScreenLines = arr
End Function

Function MatchPrompt(line)
    Dim i, matches
    MatchPrompt = Null
    For i = 0 To UBound(arrPromptPatterns)
        Set matches = arrPromptPatterns(i).Execute(line)
        If matches.Count > 0 Then
            MatchPrompt = matches(0).SubMatches(0)
            Exit Function
        End If
    Next
End Function

Function GetCurrentCommand(ByRef outLines)
    Dim lines, i, j, firstPart, cmd, cols
    lines = GetScreenLines()
    outLines = lines
    GetCurrentCommand = Null
    cols = crt.Screen.Columns
    For i = UBound(lines) To 0 Step -1
        firstPart = MatchPrompt(lines(i)(1))
        If Not IsNull(firstPart) Then
            ' An earlier prompt only belongs to this input when every
            ' preceding line reaches the right screen edge (soft wrap).
            For j = i To UBound(lines) - 1
                If Len(lines(j)(1)) < cols - 1 Then Exit Function
            Next
            cmd = firstPart
            For j = i + 1 To UBound(lines)
                cmd = cmd & lines(j)(1)
            Next
            GetCurrentCommand = Trim(cmd)
            Exit Function
        End If
    Next
End Function

Function DetectDanger(command)
    Dim i, reg
    DetectDanger = Null
    If IsNull(command) Then Exit Function
    If command = "" Then Exit Function
    For i = 0 To UBound(arrDangerousRules)
        Set reg = arrDangerousRules(i)(1)
        If reg.Test(command) Then
            DetectDanger = arrDangerousRules(i)(0)
            Exit Function
        End If
    Next
End Function

Sub ShowDebug(command, lines, reason)
    Dim txt, i
    txt = "Screen:" & vbCrLf
    For i = 0 To UBound(lines)
        txt = txt & lines(i)(0) & ": [" & lines(i)(1) & "]" & vbCrLf
    Next
    If IsNull(command) Then
        txt = txt & "No prompt detected" & vbCrLf
    Else
        txt = txt & "Command: [" & command & "]" & vbCrLf
    End If
    If Not IsNull(reason) Then txt = txt & "Rule: " & reason
    crt.Dialog.MessageBox txt, "DEBUG", MB_OK Or MB_ICONINFORMATION
End Sub

Sub GuardWork()
    Dim command, lines, reason, msg, result
    InitPromptPatterns
    InitDangerousRules
    command = GetCurrentCommand(lines)
    If IsNull(command) Then
        If DEBUG_MODE Then ShowDebug command, lines, Null
        SendEnter
        Exit Sub
    End If
    reason = DetectDanger(command)
    If DEBUG_MODE Then ShowDebug command, lines, reason
    If IsNull(reason) Then
        SendEnter
        Exit Sub
    End If
    msg = "检测到可能的高危命令：" & vbCrLf & vbCrLf
    msg = msg & "    " & command & vbCrLf & vbCrLf
    msg = msg & "命中规则：" & reason & vbCrLf & vbCrLf
    msg = msg & "是否确认执行？"
    result = crt.Dialog.MessageBox(msg, "危险命令拦截 - SecureCRT", MB_YESNO Or MB_ICONWARNING Or MB_DEFBUTTON2)
    If result = IDYES Then
        SendEnter
        Exit Sub
    End If
    CancelCurrentInput
    If SHOW_CANCEL_NOTICE Then crt.Dialog.MessageBox "危险命令已取消。", "SecureCRT", MB_OK Or MB_ICONINFORMATION
End Sub

' SecureCRT calls Main automatically. Never add a top-level Call Main.
Sub Main()
    Dim errDesc
    On Error Resume Next
    GuardWork
    If Err.Number <> 0 Then
        errDesc = "保护脚本发生异常；未主动发送 Enter。" & vbCrLf
        errDesc = errDesc & "Error " & Err.Number & ": " & Err.Description
        Err.Clear
        crt.Dialog.MessageBox errDesc, "SecureCRT Dangerous Command Guard Error", MB_OK Or MB_ICONERROR
    End If
End Sub
