---
tags:
  - reference
  - windows
---
# 小技巧

> [!hint] Windows Terminal设置Powerline
> 1. 在Windows Store中下载Windows终端。
> 2. 参考[在Windows终端中设置Powerline]([https://docs.microsoft.com/zh-cn/windows/terminal/tutorials/powerline-setup)。可能出现以下问题：
> 	- 如果无法执行PowerShell脚本，提示"无法加载文件 ******.ps1，因为在此系统中禁止执行脚本"，请以管理员模式打开powershell并执行以下命令，并在弹出的对话框里选择Y。
> 		```shell
> 		set-executionpolicy remotesigned     
> 		```
> 	- Set-Theme已经过时，采用新的命令(查看主题和设置主题):
> 		```shell
> 		Get-PoshThemes
> 		Set-PoshPrompt paradox
> 		```
> 	- 如果打开python编码错误，可以在配置文件`$PROFILE`内加入`chcp 936` 切换中文页面。

> [!hint] Windows Store无法打开
> 可以检查一下代理设置，有可能是开启代理导致的。

> [!hint] Windows10输入法面板消失，无法切换输入法
> 将英文设置为主语言，然后将中文语言彻底删除后重新安装即可解决。