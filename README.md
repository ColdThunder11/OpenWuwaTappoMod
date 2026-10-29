# OpenWuwaTappoMod

《鸣潮》官方桌宠 **Wuwa Tappo** 的补丁工具，提供一些方便使用的小功能  

当前适配主程序版本：1.0.2  

⚠️警告：使用本工具会修改本地程序文件，由此带来的一切后果请自行承担  

## 功能

- 允许直接跨显示器拖动桌宠
- 允许隐藏自己状态栏和联机时候好友昵称
- 允许重新排序联机好友图层
- 屏蔽F键快捷键（默认关闭；开启后屏蔽桌宠的全部 F1–F12 快捷键功能）
- 双击镜像角色（开启设置项后，双击自己或联机成员的桌宠可左右翻转，再次双击恢复）

## 使用

从[Release](https://github.com/ColdThunder11/OpenWuwaTappoMod/releases/latest)页面下载程序，运行后点击进行补丁即可。打开桌宠程序的设置页面可以看到相关功能的开关和说明  

### 从源码运行（uv）

```bash
uv sync
uv run python main.py
```

> 进行原位补丁需要以**管理员身份**运行，并先完全退出 Wuwa Tappo。

### 打包

```bash
uv run pyinstaller --noconfirm wuwa_tappo_mod.spec
```

## 开发

```
wuwa_tappo_mod/
├── core.py   # 补丁变换定义 + PE overlay 引擎 + 注册表定位 (可无 GUI 独立使用)
└── gui.py    # Tkinter 界面
main.py       # 入口
wuwa_tappo_mod.spec  # PyInstaller spec
```
## 许可证

本项目代码以[GPL3](./LICENSE)许可证发布。