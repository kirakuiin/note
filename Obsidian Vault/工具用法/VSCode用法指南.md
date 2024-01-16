---
tags:
  - vscode
  - reference
---
# 小技巧

> [!hint] 如何创建并调试一个C#项目
> 1. 下载[.NetCore SDK](https://dotnet.microsoft.com/download "下载地址")
> 2. 在VSCode扩展商店里安装 **C#插件**
> 3. 创建一个C#工程目录，将控制台的当前目录定位到此目录，并输入：
> 	```cmd
> 	dotnet new console
> 	```
>  > [!warning]
> > 输入命令后一定要看到目录里生成了bin目录，不然就删掉所有内容再重新输入指令。
> 4. 选择生成的cs文件，运行调试，在弹出的调试器里选择带有 **.NET Core** 的调试器
> > [!hint]
> > 运行后会在根目录生成.vscode目录，里面会有launch.json和tasks.json。这样的情况就是已经配置完毕了。
> 5. 再次调试即可运行默认代码了，结果会输出到控制台。

> [!hint] 去除调试C#程序时的加载符号日志
> 在launch.json文件中的configurations字段里，加入下面这段话：
> ```json
> "configurations": [
>	{
>		"logging": {
>			"moduleLoad": false,
>		}
>	}
>```

> [!vs]


