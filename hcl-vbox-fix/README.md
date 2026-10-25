# HCL + VirtualBox AutoFix

[中文](#中文) | [English](#english)

## 中文

HCL 5.10.3 在 Windows 11 24H2 上启动设备时，会走 VirtualBox 的 headless 前端。24H2 的 `ntdll.dll` 和 VirtualBox 6.1.x 的 hardening 校验对不上，设备进程会被杀掉，HCL 报“启动设备失败”，日志里是 `-5607`。这个脚本把 HCL 生成的 COM 包装里的 `LaunchVMProcess` 从前端参数 `headless` 改成 `gui`，再设置 HCL 的兼容性。GUI 前端不受这个问题影响，HCL 的设备控制台仍然走串口。

**适用环境**

- Windows 11 24H2，26100 实测
- HCL 5.10.3，安装在 `D:\HCL\HCL`
- VirtualBox 6.1.50r161033，安装在 `D:\HCL\VirtualBox`
- 内存完整性（HVCI）关闭
- WSL2 可以保持开启，不需要关闭

**使用方法**

1. 关闭 HCL 里的实验设备，保存配置。
2. 双击 `HCL-VBox-AutoFix.cmd`，按提示按回车。脚本会自动申请管理员权限。
3. 脚本会设置 HCL 兼容性，找到 `%LOCALAPPDATA%\Temp\gen_py` 下的 VirtualBox COM 包装，把 `LaunchVMProcess` 的 `headless` 改成 `gui`，并删除旧 pyc。
4. 看到“完成”后打开 HCL，拖设备启动。每台设备会弹出一个 VirtualBox 窗口，最小化即可，不要关闭，关闭窗口等于给设备断电。

如果脚本提示没有找到 COM 包装，先在 HCL 里拖一台设备启动一次，失败后完全关闭 HCL，再重新运行脚本。

**说明**

- 脚本不会安装或卸载 HCL/VirtualBox，只修复已经装好的环境。
- VirtualBox 7.x 不兼容 HCL 5.10.3 的 COM 接口，脚本会拒绝执行；请使用 6.1.50。
- 补丁在 Temp 里，HCL 重新生成包装或系统清理 Temp 后会丢失；再出现 `-5607` 就重新运行脚本。
- 日志：`D:\HCL\HCL\Log\SimwareWrapperLog\<用户名>-SimwareWrapper.log` 和 `%USERPROFILE%\HCL VMs\topo1\device1\Logs\VBox.log`。
- 文件：`HCL-VBox-AutoFix.cmd`（入口）、`HCL-VBox-AutoFix.ps1`（实际逻辑）。

## English

HCL 5.10.3 starts devices with VirtualBox's headless frontend. On Windows 11 24H2, VirtualBox 6.1.x fails its `ntdll.dll` hardening check in that path, kills the VM process, and HCL reports a device start failure with error `-5607` in the log. This script changes the `LaunchVMProcess` frontend argument in HCL's generated COM wrapper from `headless` to `gui`, then applies HCL's compatibility flags. The GUI frontend does not hit the bug, and HCL still controls the device over the serial port.

**Requirements**

- Windows 11 24H2, build 26100 tested
- HCL 5.10.3 in `D:\HCL\HCL`
- VirtualBox 6.1.50r161033 in `D:\HCL\VirtualBox`
- Memory Integrity (HVCI) disabled
- WSL2 can stay enabled

**Usage**

1. Close any running HCL devices and save your work.
2. Double-click `HCL-VBox-AutoFix.cmd` and press Enter at the prompt. The script requests administrator rights itself.
3. The script sets HCL's compatibility flags, finds the VirtualBox COM wrapper under `%LOCALAPPDATA%\Temp\gen_py`, changes `headless` to `gui` in `LaunchVMProcess`, and removes the stale pyc.
4. When it finishes, open HCL and start a device. Each device opens a VirtualBox window. Minimize it; closing the window powers off the device.

If the script says it cannot find the COM wrapper, start one device in HCL, let it fail, close HCL completely, and run the script again.

**Notes**

- The script does not install or uninstall HCL or VirtualBox. It only repairs an existing installation.
- VirtualBox 7.x is not compatible with HCL 5.10.3's COM interface; the script refuses to run with 7.x. Use 6.1.50.
- The patch lives in the Temp folder. HCL can regenerate the wrapper, and Windows can clean Temp; if `-5607` comes back, run the script again.
- Logs: `D:\HCL\HCL\Log\SimwareWrapperLog\<username>-SimwareWrapper.log` and `%USERPROFILE%\HCL VMs\topo1\device1\Logs\VBox.log`.
- Files: `HCL-VBox-AutoFix.cmd` (entry point), `HCL-VBox-AutoFix.ps1` (logic).
