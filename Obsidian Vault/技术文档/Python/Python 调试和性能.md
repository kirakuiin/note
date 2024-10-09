---
tags:
  - reference
  - python
---
# 常见调试工具

- pdb
- gdb
- VS Code
- VS Natvis

## VS Code

vscode实现调试的原理如下所示：
![[Python调试和性能分析 2024-09-29 20.10.30.excalidraw]]

python提供了一个叫做`sys.settrace`的函数，当进入，退出函数时，解释器会调用这个函数里注册的handler，从而实现了对函数调用过程的监控。

逐行调试采用了一个小trick。它是在字节码层面进行的。
- 将下一条指令的opcode替换为do_tracing。
- do_tracing进入一段特殊逻辑，这里在获得正确的opcode，然后触发调试的handler。
- 将opcode还原，然后真正执行指令。
- 然后再将下一条opcode替换为do_tracing

## VS Natvis

本质上是一个配置文件，可以配置调试时不同对象的输出格式，通过设置好的格式可以更清晰的看到对象内部的内容。

# 热更新

python的热更新本质上时运行时的替换过程。

```python
import test
def new_foo():
	pass
test.foo = new_foo
```

一些常见的热更辅助函数为：
```python
def update_func(old_f, new_f):
	# setattr 替换关键属性
	setattr(old_f, "__code__", new_f.__code__)
	setattr(old_f, "__defaults", new_f.__defaults__)
	setattr(old_f, "__doc__", new_f.__doc__)
	setattr(old_f, "__dict__", new_f.__dict__)
	# 处理闭包__closure__，对闭包中的函数递归调用。
	if old_f.__closure__:
		for idx, unit in enumerate(old_f.__closure__):
			if inspect.isfunction(unit.cell_contents):
				new_unit = new_f.__closure__[idx]
				update_func(unit.cell_contents,
							new_unit.cell_contents)

def update_cls(old_c, new_c):
	# 分别处理普通函数，类和静态函数，以及嵌套类的替换。
	for name, n_attr in new_c.__dict__.items():
		o_attr = old_c.__dict__[name]
		if inspect.isfunction(o_attr)
			and inspect.isfunction(n_attr):
			update_func(o_attr, n_attr)
		elif isinstance(n_attr, staticmethod)
			or isinstance(n_attr, classmethod):
			if hasattr(o_attr, "__func__")
				and hasattr(n_attr, "__func__"):
				update_func(o_attr.__func__, n_attr.__func__)
		elif inspect.isclass(n_attr)
			and n_attr.__name__ is o_attr.__name__:
			update_cls(o_attr, n_attr)
```

# 性能分析工具

## CPU

- cProfile
- austin。有vscode可以直接使用，可以profile cpu和内存，可以行级profile。
- tracy。实时高精度可远程profile。

> [!example] 分析步骤
> 1. 首先根据profile定位哪一桢卡顿。
> 2. 进入卡顿帧，分析函数堆栈，查看时间占用情况。
> 3. 定位问题函数，分析代码，找出问题并给出解决方案。

这些性能分析工具，由于可以记录函数栈帧，因此可以辅助理解函数的调用过程。

## 内存

- tracemalloc，分析内存的使用情况。
- objgraph，可以分析对象之间的引用关系，用来排查内存泄漏。

# 性能优化方法

## CPU优化

python运行慢的主要原因是：
- 动态类型导致运行时需要进行类型检查。
- 万物皆对象导致运行时要频繁查字典来查找属性。
	![[Python调试和性能 2024-09-30 14.27.16.excalidraw]]
- GIL导致无法利用多核心优势。
- 由于是解释型语言，在虚拟机执行时，每个循环内重复解释语句，无法把各种查表，类型检查提取到循环外。这是CPU性能差的根本原因。

针对上述原因，有以下优化方案：
1. 对于一些特殊类型的数值运算，尽量采用引擎提供的数学库，库中不会进行多余的检查。
2. 使用更高效的虚拟机，来避免大量的类型检查。
3. 当大量访问属性时（无论是类属性还是全局变量），使用局部变量缓存属性，从访问速度上来说：局部>闭包>全局>内建。
4. 对于导入来说，每次导入还是会有查询`sys.modules`的开销，因此对于广泛使用的基础通用模块还是放到模块头部。对于调用次数少，用途仅限某几个函数的可以放到函数内部。
5. 官方在PEP-684中提出了子解释器的概念，突破了GIL的封锁。甚至在PEP-703中提出了逐步移除GIL的想法。
6. 考虑引入编译型语言的优点，比如PyPy可以利用JIT加速执行；或者将性能热点下沉到C/C++，比如使用PyBind11，NanoBind；或者将Py转为C或C++，比如Cython。

> [!hint]
> 如果代码是大量的逻辑调用，而不是大量的计算，将代码改为C/C++也未必能获得多大的提升。

## 内存优化

由于一切都是对象，无论基本类型还是自定义类型，这导致python为了存储类型信息在存储每个对象是都产生了大量的额外开销。这也是python内存占用需要优化的原因。

1. 部分python类型，比如字典，列表。其空的对象在内存中可能就要占据几十字节，因此最好将其默认值设置为更节省空间的类型。`"", {}, [] => None`
2. 不常用的变量延迟初始化。
3. 用组合替代继承。
4. 使用迭代器而不是列表，迭代器会按需生成元素。
5. 对一些大量使用且属性不变的对象，考虑使用`__slot__`类属性来定义属性。可以大量降低内存占用，提高访问速度。
6. 对于字典格式的导表数据，可以用如下方式优化：
	- 重复的数据抽离为一个新的表，并将其替换为索引来引用新的表。
	- 考虑将字典替换为元组，比如：
		```python
		table = {
			1001 : {"name": "hello", "age": 20},
			1002 : {"name": "world", "age": 3},
		}
		
		# 优化为如下形式
		ID = 0
		NAME = 1
		AGE = 2
		table = (
			(1001, "hello", 20),
			(1002, "world", 3),
		)
		# 但这种优化会降低可读性，也会导致索引时不如字典快速(为了解决这个问题可能要让ID和元组下标一一对应。)
		```
	- 使用自定义的字典，采用更加合理的内存分布。
	- 不用python来存储数据，用嵌入式数据库，C/C++等。
