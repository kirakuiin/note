---
tags:
  - reference
  - emacs
---
> [!question] c-c++ layer clangd后端无法识别标准库
> 这个问题是由于**cmake**生成的**compile_commands.json**中是不包含标准库的路径的，即不包含`-I/.../include/c++/v1`，因此需要在**CmakeLists.txt**中使用`INCLUDE_DIRECTORIES`命令手动将标准库路径包含在其中。
> 另外有时候包含这个标准库可能会导致编译错误，这个时候就只能换一个不出错的标准库。
   
> [!question] 更新时出现大量包找不到的错误
> 很大可能是源的问题，导致包不完整，最后导致启动出现奇奇怪怪的错误。
   
> [!question] py lsp 无法正常启动，显示`name 'platform_system' is not defined`
> 更新**pip**和**setuptools**，通过指令`pip install --upgrade`来更新。
   
> [!question] Windows下**emacs**无法找到**spacemacs**
> 请设置环境变量`$HOME`为`.emacs.d`所在的目录，这样**emacs**才能找到配置文件。

> [!summary] org-mode中**timestamp**的`+1x`，`++1x`和`.+1x`
>- `+1x`：每次完成向后推迟一个间隔，即便当前时间已经超过deadline。
> > [!example]
> > 如果状态为: `TODO <2020-4-3 21:30 +1h>`
> > 而今天的时间为2021-4-3 9:20，`<C-c><C-t>`将任务变为**DONE**，状态将变为 `TODO <2020-4-3 22:30 +1h>`
> - `++1x`：和`+1x`的区别在于，如果当前时间已经超过deadline，则会一次性将时间同步到当前时间之后的最近时间间隔(10min)。
> > [!example]
> > 如果状态为: `TODO <2020-4-3 21:30 ++1h>`
> > 而今天的时间为2021-4-3 9:20，`<C-c><C-t>`将任务变为**DONE**，状态将变为`TODO <2021-4-3 9:30 ++1h>`
> - `.+1x`：和`++1x`的区别在于，同步到以当前时间为基础的下个间隔。
> > [!example]
> > 如果状态为: `TODO <2020-4-3 21:30 .+1h>`
> > 而今天的时间为2021-4-3 9:20，`<C-c><C-t>`将任务变为**DONE**，状态将变为 `TODO <2021-4-3 10:20 .+1h>`

> [!summary] 新建窗口在屏幕中的位置
> 这个是由变量 `split-height-threshold` 和 `split-width-threshold` 来决定的，比如如果将 `split-width-threshold` 设置为80，那么当你创建新窗口时如果他的宽度能超过80列，那么就会水平创建窗口，否则创建竖直窗口。

> [!summary] **emacs**默认配置读取路径
> **Linux/Unix**系统默认在`~`目录，**Windows**下如果想要在`~`目录，必须设置环境变量`$HOME=~`。

> [!question] **org-mode**缩进失效问题。
> 可能是在**org-mode**里面由未闭合的双引号("")，这会导致后面的全部缩进失效。

> [!note]  **org-babel python**语法记号
> 参考 [Python Source Code Blocks in Org Mode](https://orgmode.org/worg/org-contrib/babel/languages/ob-doc-python.html)
