---
tags:
  - knowledge
---
# 基础语法

> [!hint]
> 基础语法是所有支持markdown应用程序都支持的语法
## 标题

> [!example]
> # 这是一个一级标题的例子

```markdown
# 这是一个一级标题的例子
```

其中#号可以替换为1个到6个，分别代表1到6级标题。

> [!hint] 最佳实践
> 在#号和标题内容间加空格，因为有的应用可能无法处理不带空格的标题语法。
## 段落

> [!example]
> 文本1
> 
> 文本2

```markdown
文本1

文本2
```

使用空行来划分段落。
## 换行

> [!example]
> 第一行  
> 第二行

```markdown
第一行  
第二行
```

在一行结尾添加两个或多个空格，然后回车即可换行。
## 强调

> [!example]
> 这是**加粗**
> 这是*斜体*
> 这是***加粗斜体***

```markdown
这是**加粗**
这是*斜体*
这是***加粗斜体***
```
## 引用

> [!example]
> > 这是引用
> > 
> > *部分语法*在引用内也可以**使用**
> > > 引用可以嵌套

```markdown
> 这是引用
> 
> *部分语法*在引用内也可以**使用**
> > 引用可以嵌套
```

引用包含多个段落时需要在空行加`>`。
## 列表

> [!example]
> 1. 第一项
> 2. 第二项
> 	不打断列表并插入其他元素，需要在前方插入4个空格或一个制表符
> 3. 第三项
> 
> - 无序1
> - 无序2
> 	- 子项无序1
> 	- 子项无序2
> - 无序3

```markdown
1. 第一项
2. 第二项
	不打断列表并插入其他元素，需要在前方插入4个空格或一个制表符
3. 第三项

- 无序1
- 无序2
	- 子项无序1
	- 子项无序2
- 无序3
```

无序列表中的`-`可以替换为`*`或`+`，但在使用时最好用同一个符号。

## 代码

> [!example]
> `print("hello world!)"`
> `` `转义情况` ``

```markdown
`print("hello world!)"`
`` `转义情况` ``
```

## 分隔线

> [!example]
> 
> ---
> 

```markdown

---

```

一整行只包含三个`-`, `+` 或者 `_`。

> [!hint] 最佳实践
> 处于兼容性的原因，最好在分隔线的上下都加入空行

## 链接

> [!example]
> 这是一个链接 [Markdown](https://markdown.com.cn "此处内容会在鼠标悬停在链接上时显示")。
> 这是一个网页地址 <https://www.google.com>
> 链接可以格式化 *[`Markdown`](https://markdown.com.cn)*
> 
> 这是引用链接，可以让文本更易阅读，分为两部分：
> - 这是引用部分 [引用][id]
> - 这是存储部分 [id]: https://www.google.com

```markdown
这是一个链接 [Markdown](https://markdown.com.cn "此处内容会在鼠标悬停在链接上时显示")。
这是一个网页地址 <https://www.google.com>
链接可以格式化 *[`Markdown`](https://markdown.com.cn)*

这是引用链接，可以让文本更易阅读，分为两部分：
- 这是引用部分 [引用][id]
- 这是存储部分 [id]: https://www.google.com
```

> [!hint] 最佳实践
> URL中的空格使用%20代替

## 图片

> [!example]
> ![[Andromeda galaxy.jpg]]

```c++
![这是图片](/Assets/Images/Andromeda%20galaxy.jpg "悬停标题")
```

## 转义

> [!example]
> \*是标记语法的一部分，此时被转义。

```markdown
\*是标记语法的一部分，此时被转义。
```

通过对标记语法使用的字符前加反斜杠`\`来进行转义，下列字符都可被转义：
- \\
- \`
- \*
- \_
- \{}
- \[]
- \()
- \#
- \+
- -
- .
- !
- |

# 扩展语法

> [!hint]
> 通过添加额外功能扩展了基本语法，但并非所有的应用都支持。

## 表格

> [!example]
> | 标题11111 | 标题22222 | 标题33333 |
> | :--- | :---: | ---: |
> | *左对齐* | **居中对齐** | ***右对齐*** |
> 
> 

```markdown
| 标题11111 | 标题22222 | 标题33333 |
| :--- | :---: | ---: |
| *左对齐* | **居中对齐** | ***右对齐*** |
```

根据冒号所在位置调整表格项的对齐模式。
## 代码块

> [!example]
> ```python
> def foo():
> 	print("hello world!")
> ```

~~~markdown
```python
def foo():
	print("hello world!")
```
~~~

波浪线 `~` 的作用和反引号`` ` ``等同，一般用于出现嵌套的情况下使用。如果在三个反引号后加上代码所使用的语言名称，则会提供语法高亮的功能

## 脚注

> [!example]
> 这里向你展示脚注[^1][^note]
>
> [^1]: 这是脚注的内容
> [^note]: 脚注可以有很多个

```markdown
这里向你展示脚注[^1][^note]

[^1]: 这是脚注的内容
[^note]: 脚注可以有很多个
```

脚注可以为数字或者单词，不能包含空格或者制表符。
## 定义列表

> [!example]
> 术语A
> : 术语A的定义
> 术语B
> : 术语A的定义

```markdown
术语A
: 术语A的定义
术语B
: 术语A的定义
```
## 删除线

> [!example]
> ~~删除内容～～

```markdown
~~删除内容～～
```

两个波浪线之间的内容将会在水平中心防止一条直线代表被删除。
## 任务列表

> [!example]
> - [x] 任务1
> - [ ] 任务2

```markdown
- [x] 任务1
- [ ] 任务2
```
## emoji

> [!example]
> 真好笑！😂

```markdown
真好笑！:joy:
```

> [!hint]
> 具体表情代码可以参考[表情符号简码列表](https://gist.github.com/rxaviers/7360908)

# 特殊语法

> [!hint] 仅在某个应用里支持的语法，不具有泛用性。
## Callout

> [!warning] 这个语法仅在Obsidian中生效

> [!example]
> 这是一个Callout例子，一种美观的局部高亮提示框。

```markdown
> [!INFO]
> 这是一个Callout例子，一种美观的局部高亮提示框。
```

其中INFO替换为如下的文本：
- note
- abstract, summary, tldr
- info, todo
- tip, hint, important
- success, check, done
- question, help, faq
- warning, caution, attention
- failure, fail, missing
- danger, error
- bug
- example
- quote, cite

# 小技巧

> [!note]
> - `&emsp;`可以表示中文空格，一般用来实现中文段落的首行双空格排版
> - 可以使用`<font color="color-name">content</font>`语法来修改字体颜色
