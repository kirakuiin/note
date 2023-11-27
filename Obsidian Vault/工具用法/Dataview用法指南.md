---
tags:
  - reference
  - obsidian
source-link: https://blacksmithgu.github.io/obsidian-dataview/
---
# 如何使用

主要的用法就是在各个文档里增加元数据，也叫做**数据索引**。然后再需要生成图表的位置使用**数据查询**语法来构建图表。
## 数据索引

数据索引就是你在文档里留下的各种元数据，一种是位于文档开头使用`---`生成的**文档属性**，另一种就是在文档其他位置书写的**键值对**（[key::value]）
## 数据查询

主要有两种语法进行查询，一种是使用DQL[^1]和內联DQL[^1]；另一种是使用较为灵活但更加复杂的Javascript 查询。

### DQL查询

一个DQL[^1]查询由四部分构成：

- 代码块的`dataview`表明这是一个DQL[^1]查询
- 查询类型来决定你要生成什么样的图表；
- 零或一个*FROM*语句来决定数据来源；
- 零到多个数据命令来帮助你过滤，分组，排序生成的输出。

一个简单的查询可能如下所示：
> [!example]
> ~~~markdown
> ```dataview
> LIST
> ```
> ~~~

# 元数据的基本知识

元数据支持以下类型：

- Text，一般的文本类型
- Number，数字类型，比如3， 3.5
- Boolean，布尔类型，true和false
- Date，日期类型，格式为YYYY-MM[-DDTHH:mm:ss.nnn+ZZ]，查询日期时还可获得以下数据：
	- field.year
	- field.month
	- field.weekyear
	- field.week
	- field.weekday
	- field.day
	- field.hour
	- field.minute
	- field.second
	- field.millisecond
- Duration，持续时间，比如 7 hours，16 days，4min，6hr7min
- Link，链接，比如`[[A page]]`
- List，列表，比如[one, two, three]
- Object, 对象

Dataview同时为每个文件自动生成了若干元数据，如下图：

| Field Name       | Data Type | Description                                          |
| :- | :- | :- |
| file.name        | Text      | 文件名                                               |
| file.folder      | Text      | 文件所属的文件夹                                     |
| file.path        | Text      | 文件的全路径                                         |
| file.ext         | Text      | 文件的扩展名                                         |
| file.link        | Link      | 到文件的链接                                         |
| file.size        | Number    | 文件大小(bytes)                                      |
| file.ctime       | Date      | 文件的创建时间                                       |
| file.cday        | Date      | 文件的创建日期                                       |
| file.mtime       | Date      | 文件的最后修改时间                                   |
| file.mday        | Date      | 文件的最后修改日期                                   |
| file.tags        | List      | 文件的全部标签                                       |
| file.etags       | List      | 文件的全部标签，和上面不同的是子标签不会被拆分为多个 |
| file.inlinks     | List      | 文件入链[^3]                         |
| file.outlinks    | List      | 文件出链[^4]                           |
| file.aliases     | List      | 文件的别名                                           |
| file.tasks       | List      | 文件内所有形如`[ ] some task`的内容                  |
| file.lists       | List      | 文件内所有的列表元素                                 |
| file.frontmatter | List      | 文件内所有形如`key::value` 的内容                    |
| file.day         | Date      | 仅当文件内含有日期属性时生效                         |
| file.starred     | Boolean   | 此文件是否被书签标记                                 |

> [!hint]
> 自定义元数据可以直接通过名字访问。
# 內联DQL用法说明

內联DQL[^1]确切来说仅能显示**一个值**。你可以在任何位置插入[[markdown语法#行内代码|行内代码]]，并以**dv:**[^2]开头，使用看起来就像这样：
> [!example]
> `` `dv: this.file.name` ``
> `` `dv: date(now) - this.file.ctime` ``

这里`this`指代的是当前文件，你也可以用`[[other file]]`来指代其他文件
# DQL用法说明

一般格式为：
```markdown
<QUERY-TYPE> <fields>
<FROM> <source>
<DATA-COMMAND> <expression>
<DATA-COMMAND> <expression>
...
```

## 选择输出格式

对应\<**QUERY-TYPE**\>，只能使用**一次**，关键字有以下几种：
- TABLE：输出一个表格，显示的字段由\<**fields**\>指定
- LIST：默认输出一个由文件链接构成的要点列表，可由\<**fields**\>进行调整
- TASK：输出一个交互式的任务列表
- CALENDAR：根据\<**fields**\>指定的时间字段生成日历

> [!example]
> `CALENDAR file.cday`
> `TABLE due, file.tags AS "标签"`

LIST和TABLE的\<**fields**\>均可以由表达式构成，TABLE还能用**AS**给字段起别名，比如：
 > [!example]
 > `LIST "文件路径：" + file.folder`
 > `TABLE file.ctime - date(now) AS delay, file.folder as path`
 
LIST和TABLE均可以追加WITHOUT ID， 会省略掉部分生成信息：
 > [!example]
 > `LIST WITHOUT ID`


## 选择数据源

对应\<**FROM**\>，只能使用**一次**，如果不加则把根目录当作数据源。
> [!example]
> `FROM #recommand OR ("Books" AND #west)`

数据源可以为以下几种类型：

- 标签：语法为`#tag`
- 文件夹：语法为`"folder"`, 注意包含子目录
- 具体文件：语法为`"a/b/file"
- 链接：所有入链[^3]使用`[[note]]`, 所有出链[^4]使用`outgoing([[note]])`

> [!hint]
> 数据源之间可以通过关键字 **and, or, -** 来进行组合，**-** 代表否定。
## 添加数据指令

对应\<**DATA-COMMAND**\>，这些数据指令都使用多次，并且必须位于\<**QUERY-TYPE**\> 和 \<**FROM**\> 之后，它们之间可以按照任意次序排列组合。

- WHERE：根据元数据对数据源进行过滤
- SORT：按照某个域对数据进行排序
- GROUP BY：将多个结果绑定到每组的结果行中
- LIMIT：限制显示的结果数量
- FLATTEN：将一个字段的结果拆分为多个结果

> [!example]
> ~~~markdown
> ```dataview
> TABLE file.ctime AS 创建时间, file.tags AS 标签
> FROM "test"
> FLATTEN file.lists AS L
> WHERE contains(L.author, "Wang")
> ```
> ~~~
---

### WHERE

对后面的表达式求值，为真方可输出，语法为：
> [!example]
> `WHERE file.mtime >= date(today) - dur(1 day)`

### SORT

通过一个或多个字段进行排序, 语法为：
> [!example]
> `SORT field1 [ASC/DESC][, ..., fieldN [ASC/DESC]]`

### GROUP BY

对结果分组，生成时组名一行，组内成员锁进后紧跟组名，语法为：
> [!example]
> `GROUP BY field [AS alias]`

会把匹配这一组的全部页面存放到变量 **rows** 中，可以通过 **rows.xxx** 来访问每个页面的元素。
### FLATTEN

根据字段对结果拆分，比如一个字段由三个值构成，用了关键字之后每个值都会生成一个单独的结果，一般用于深层嵌套的列表中，语法为：
> [!example]
> `FLATTEN field [AS alias]`

### LIMIT

限制结果输出行数，语法为：
> [!example]
> `LIMIT number`

## 函数

DQL[^1]提供了若干功能函数，让你更加容易的处理数据，输出结果，比如：
> [!example]
> - date()：生成日期对象
> - dur()：生成持续时间对象
> - number()：字符串转数字
> - link()：生成链接对象

详细内容可以参考官方说明文档： [函数列表](https://blacksmithgu.github.io/obsidian-dataview/reference/functions/)

---

[^1]: Dataview Query Language， 数据视图查询语言。
[^2]: dv:这个标识符可以在Dataview插件里面进行配置，默认使用的是=
[^3]: 所有引用此文件的文件的链接
[^4]: 此文件引用的所有文件的链接