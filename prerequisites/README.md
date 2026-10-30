# Windows 7 前置更新

ProcessMind 的 CPython 3.8.10 x64 运行时在 Windows 7 SP1 上要求安装
`KB2533623`，或安装包含该修复的后续更新。缺少该更新时，启动器可能在加载
`_socket.pyd` 时显示“DLL load failed ... 参数错误”。

离线文件 `Windows6.1-KB2533623-x64.msu` 的 SHA-256 为
`58b8b00113fa8b9657d8da5b14bae93f765f29651c81055e3d127d4a22e5c0d6`。

请在启动 ProcessMind 前：

1. 以管理员身份运行 `install-kb2533623.bat`。
2. 安装完成后重启 Windows 7。
3. 重启后再双击包根目录的 `start-win7.bat`。

安装脚本不会自动重启系统，也不会在 ProcessMind 启动时静默修改系统更新。
如果企业镜像已经包含 KB2533623 的后续更新，可以由管理员确认后跳过本步骤。
