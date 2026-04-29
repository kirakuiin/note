---
tags:
  - reference
  - python
---

python3相比于python2带来了大量优化和改变，这里记录下个人觉得有趣或者比较重要的点。

# 基本差异

同python2对比，有如下差异：
- print不再是语句，而是一个函数。
- range，map等函数返回的是迭代器，而不是列表。
- 非数值类型的对象不再能够进行比较。
- 去除了long类型，只有int类型。
- metaclass语法调整。
- /为地板除，//为浮点除。
- round采用银行家舍入法。
- super简化，不需要再带上父类类型和self，改为`super().`。
- 字符串默认采用unicode编码。
- 不再支持隐式相对导入。
- 取消了pyo文件，无论是优化还是未优化的都以pyc结尾。

> [!warning]
> 默认除法和round的修改可以会导致py2转3出现一些隐形的bug。

# 新语法

## 字符串内插

类似于C#的字符串内插，python3也引入了这一语法。

```python
val = 123
# f表明这段字符串使用内插规则，{}内则为内插的变量。
print(f"{val:.2f}")
```

## 特殊参数

引入了两个新的函数参数记号，用来区分强制规定那些参数是定位参数，哪些是关键字参数。

```python
# pos1必须定位传入，pos_or_keyword使用定位或关键字均可，key1必须使用关键字传入。
def func(pos1, /, pos_or_keyword, *, key1):
	pass
```

## 海象运算符

python3新增了运算符`:=`，长得很像横过来的海象头，所以叫海象运算符。作用是再给变量赋值的同时还能返回这个值作为表达式来使用。主要用于简化写法。

```python
i = 5
# 执行四次，i在循环前就减1了。
while i := i-1 > 0:
	pass
```

## 枚举类型

支持内建的枚举类型。

```python
from enum import Enum

class Color(Enum):
	Purple = 1
	Pink = 2
	Aqua = 3
```

## match

功能几乎和C#的switch差不多。都是支持模式匹配的分支语句。

```python
def func(val):
	match val:
		case 400: # 常规匹配
			pass
		case list() | set(): # 类型匹配
			pass
		case int() as i if i < 50: # 条件匹配
			pass
		case _:  # default
			pass
```

## 类型注解

python3引入了类型注解这一功能，让python可以享受到静态类型语言的部分优势。主要有两个优点：
- 提前将一些运行期的错误提前暴露在编写代码期，降低了低级bug的出现率。
- 对各种linter非常友好，代码补全，跳转功能得到了极大的增强，提高了开发效率。

> [!hint]
> 关于注解的详细内容可参考[typing](https://docs.python.org/3/library/typing.html), 下文使用的很多函数，类型也都在这个模块下。`import typing`。

### 基本语法

- 添加到函数的签名处。
	```python
	def help(s: str, times: int) -> float:
		return 0.1
	```
- 添加到变量初始化后。
	```python
	name: str = "wtf"  # 此时不需要注解，python也能自己推导出来。
	```

### 类型

除了基本类型，这里列出一些其他类型的表达方式：

- list：`list[int]`。
- dict：`dict[int, str]`。
- 任意类型：`Any`。
- 任一类型：`str | int | float`。
- 可调用类型：`Callable[[int, str], bool]`，`[int, str]`参数列表，`bool`是返回类型。
- 为`None`或某一类型：`Optional[int]`。
- 类型别名：`dii: TypeAlias = dict[int, int]`。
- 设置字典的值域类型。
	```python
	class Data(TypedDict):
		a: int
		b: str
		c: float
	
	data: Data = {}
	```
- 限定字符串为指定的字面量之一，可以配合上一条来限制字典的定义域。
	```python
	StrOption = Literal["a", "b", "c"]
	s: StrOption = "a"
	```
- 前向声明，比如在定义类型时参数为自身类型。此时需要`from __future__ import annotations`。
- 协议，在类型注解里的作用类似于java和c#的接口。
	```python
	class Shootable(Protocol):
		def shoot(self):
			pass
	
	def Shoot(entity: Shootable):
		pass
	```
- 泛型，在类型注解里的作用类似于java和c#里的泛型。
	```python
	T = TypeVar("T") # 定义泛型类型
	
	def first(l: list[T]) -> T:
		return l[0]
	```
- 重载，实现一种类似于静态语言里重载的效果，类型检查会检查合适的重载形式并给出提示。
	```python
	# overload必须位于实际函数之前.
	@overload
	def over_load(a: int) -> int:
		...
	
	@overload
	def over_load(a: str) -> str:
		...
	
	# 实际逻辑
	def over_load(a: any) -> any:
		return a
	```

### pyi文件

一般位于py文件同级目录或者一个单独的stub目录中。它内部的内容类似于c里的头文件，全部都是对应python源文件中对象的类型声明。

主要作用有：
- 类型注解可能需要导入其他模块，当import耗时较长的模块时，python会优先加载pyi文件，不会真实加载真正的py文件。
- 为没有类型的第三方库添加标注。
- 为C/C++扩展添加标注。

> [!hint]
> py和pyi只能有一个生效，不能同时生效。

# 实用库

## dataclasses

用来实现简单的数据类。

```python
from dataclasses import dataclass, field

@dataclass
class Item:
	name: str
	desc: str
	price: int
	count: int
	tags: list[int] = field(default_factory=list)

	def total_price(self) -> float:
		return self.price * self.count

	# init之后自动调用。
	def __post_init__(self):
		self.tags = [3, 4]

item = Item("dog", "a dog", 10, 1)
```

## asyncio

适用于处理密集IO和高层网络代码的异步框架。通过`async`和`await`关键字可以让异步程序的代码和同步的长得差不多。避免了**回调地狱**的困扰。

不过asyncio不能取代线程，当你在主线程执行asycio的事件循环时，主线程是会被阻塞住的。

## pathlib

提供了两套和路径相关的接口：
- `PurePath`: 无需真实访问文件系统，只操作路径字符串。
- `Path`: 需要真实进行文件读写的环境。

# 性能提升

## 自适应特化解析器

原理简单来说就是运行时统计指令的运行情况，来将指令替换为一个速度更快的特化版本。

比如一个简单的`+`运算符，背后可能有着非常复杂的运算：
- 两个操作数是否有加法方法？
- 两个操作数的父类是否能够相加？
- 两个操作数是否可以支持序列拼接操作？

如果确认两个操作数都为`float`，那么直接执行相加就可以了。

两个过程间的耗时差值，就是性能提升的部分。当然替换操作，预测失败都是由成本的，但只要保持一定的命中率，那么性能提升就非常可观。

整个特化的流程可以描述为：

![[Python3 新特性 2024-10-09 19.45.04.excalidraw]]

通过这样一套机制，当miss过多时，会减少特化的频率，当一直命中时，则会维持特化不变。
## Python-Jit

JIT的全称是*Just in Time Compile*，意为运行时生成二进制代码。而python3目前实现的思路也非常简单：
- 离线时根据代码先生成若干二进制模板库。
- 运行时如果指令匹配到模板，则将其替换为二进制代码。

其主要的性能提升点在于二进制代码可以合并，减少了主循环中指令执行的数量。