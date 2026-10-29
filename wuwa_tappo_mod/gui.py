# -*- coding: utf-8 -*-
# OpenWuwaTappoMod —— 《鸣潮》官方桌宠 Wuwa Tappo 的本地化补丁工具 (精简版)
# Copyright (C) 2026 OpenWuwaTappoMod contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""OpenWuwaTappoMod GUI (Tkinter)"""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext

from .core import (
    BACKUP_EXT, SUPPORTED_VERSION, find_install_dir, is_pristine, run_patch,
)


def _is_admin():
    import ctypes
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _relaunch_elevated():
    """以管理员重新拉起自身(UAC); 返回是否成功发起"""
    import ctypes
    import sys
    import subprocess
    if getattr(sys, "frozen", False):          # PyInstaller 打包后的 exe
        exe, args = sys.executable, list(sys.argv[1:])
    else:                                       # 源码运行: python main.py
        exe, args = sys.executable, [os.path.abspath(sys.argv[0])] + list(sys.argv[1:])
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", exe, subprocess.list2cmdline(args), None, 1)
    return ret > 32


DISCLAIMER_REG_PATH = r"SOFTWARE\OpenWuwaTappoMod"
DISCLAIMER_REG_VALUE = "DisclaimerAccepted"


def _disclaimer_accepted():
    """注册表中是否已记录同意免责声明"""
    import winreg
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, DISCLAIMER_REG_PATH)
        v, _ = winreg.QueryValueEx(k, DISCLAIMER_REG_VALUE)
        return v == 1
    except OSError:
        return False


def _save_disclaimer_accepted():
    import winreg
    winreg.SetValueEx(
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, DISCLAIMER_REG_PATH),
        DISCLAIMER_REG_VALUE, 0, winreg.REG_DWORD, 1)


def _show_disclaimer():
    """启动免责声明 (仅首次, 确认写入注册表); 返回是否同意继续"""
    if _disclaimer_accepted():
        return True
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    ok = messagebox.askyesno(
        "OpenWuwaTappoMod — 免责声明",
        "本软件会修改 WuwaTappo 的代码，作者不对其进行任何保证。" + chr(10) * 2 +
        "继续使用视为同意承担由此可能带来的后果。" + chr(10) * 2 +
        "是否同意并继续？（同意后不再提示）",
        icon="warning")
    root.destroy()
    if ok:
        try:
            _save_disclaimer_accepted()
        except OSError:
            pass
    return ok


def main():
    # 修改安装目录(C:\Program Files)需要管理员: 非管理员自动 UAC 提权重启
    # WTAPMOD_NO_ELEVATE=1 可跳过提权(用于非系统目录/调试)
    if (os.name == "nt" and not _is_admin()
            and not os.environ.get("WTAPMOD_NO_ELEVATE")):
        if _relaunch_elevated():
            return                              # 提权进程已接管, 本进程退出
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "OpenWuwaTappoMod",
            "需要管理员权限才能修改安装目录中的文件。" + chr(10) * 2 +
            "请允许 UAC 提权, 或右键以管理员身份运行。")
        return
    if not _show_disclaimer():
        return                                  # 不同意免责声明则退出
    App().root.mainloop()


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("OpenWuwaTappo MOD")
        self.root.geometry("720x520")
        self.src = tk.StringVar(value="")
        self.out = tk.StringVar(value="")
        self.toolkit = tk.BooleanVar(value=True)
        self.q = queue.Queue()
        self._build()

    def _build(self):
        r = self.root
        frm = ttk.Frame(r, padding=10)
        frm.pack(fill='both', expand=True)
        ttk.Label(frm, text="目标 exe:").grid(row=0, column=0, sticky='w')
        ttk.Entry(frm, textvariable=self.src, width=70).grid(row=0, column=1, padx=4)
        ttk.Button(frm, text="浏览...", command=lambda: self.pick(self.src)).grid(row=0, column=2)
        ttk.Separator(frm).grid(row=1, column=0, columnspan=3, sticky='ew', pady=8)
        ttk.Label(frm, text="功能: "
                  ).grid(row=2, column=0, columnspan=3, sticky='w')
        ttk.Checkbutton(frm, text="实用工具集（各项均可在应用设置页面随时开关）",
                        variable=self.toolkit, state='disabled').grid(row=3, column=0, columnspan=3, sticky='w')
        bar = ttk.Frame(frm)
        bar.grid(row=4, column=0, columnspan=3, pady=8)
        self.btn = ttk.Button(bar, text="开始补丁", command=self.go)
        self.btn.pack(side='left', ipadx=20, ipady=4)
        self.restore_btn = ttk.Button(bar, text="恢复原版", command=self.restore)
        self.restore_btn.pack(side='left', padx=8)
        self.log = scrolledtext.ScrolledText(frm, height=16, state='disabled')
        self.log.grid(row=5, column=0, columnspan=3, sticky='nsew')
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(5, weight=1)
        self.out.trace_add('write', self._refresh_restore)
        self.src.trace_add('write', lambda *args: self.out.set(self.src.get()))
        self._locate()
        r.after(100, self._poll)

    def _locate(self):
        loc = find_install_dir()
        if loc:
            exe = os.path.join(loc, 'WuwaTappo.exe')
            self.src.set(exe)
            self.out.set(exe)
            if os.path.exists(exe + BACKUP_EXT):
                self.q.put("安装位置: %s (发现备份)" % loc)
            else:
                self.q.put("安装位置: %s (将自动备份原版为 .orig)" % loc)
        else:
            self.q.put("注册表未找到 WuwaTappo 安装项, 请手动选择源 exe")

    def restore(self):
        exe = self.out.get()
        bak = exe + BACKUP_EXT
        if not os.path.exists(bak):
            self.q.put("!! 未找到备份: %s" % bak)
            return
        import shutil
        try:
            shutil.copy2(bak, exe)
            self.q.put("已恢复原版 <- %s" % bak)
        except PermissionError:
            self.q.put("!! 恢复被拒绝: 请以管理员运行且关闭 WuwaTappo")

    def _refresh_restore(self, *args):
        bak = self.out.get() + BACKUP_EXT
        self.restore_btn.state(['!disabled'] if os.path.exists(bak) else ['disabled'])

    def pick(self, var, save=False):
        if save:
            p = filedialog.asksaveasfilename(initialfile=os.path.basename(var.get()))
        else:
            p = filedialog.askopenfilename(filetypes=[("exe", "*.exe")])
        if p:
            var.set(p)
            if var is self.src:
                self.out.set(p)

    def go(self):
        src, out = self.src.get().strip(), self.out.get().strip()
        if not os.path.isfile(src):
            self.q.put("!! 请先选择有效的 WuwaTappo.exe")
            return
        if not out:
            self.q.put("!! 目标路径不能为空，请重新选择目标 exe")
            return
        self.btn.state(['disabled'])
        self.restore_btn.state(['disabled'])
        self.q.put("目标版本要求: WuwaTappo %s (其他版本请先恢复官方对应版本)" % SUPPORTED_VERSION)
        threading.Thread(target=self._worker, args=(src, out), daemon=True).start()

    def _worker(self, src, out):
        try:
            run_patch(src, out, lambda m: self.q.put(m))
            self.q.put("__DONE__")
        except Exception as e:
            self.q.put("!! 失败: %r" % e)
            self.q.put("__DONE__")

    def _poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                if m == "__DONE__":
                    self.btn.state(['!disabled'])
                    self._refresh_restore()
                    continue
                self.log.config(state='normal')
                self.log.insert('end', m + "\n")
                self.log.see('end')
                self.log.config(state='disabled')
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

