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

python提供了一个叫做`sys.settrace`的函数，当进入，推出函数时，解释器会调用这个函数里注册的handler，从而实现了对函数调用过程的监控。

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
	# setattr 替换 __code__, __doc__, __dict__, __defaults__ 属性
	# 处理闭包__closure__，对闭包中的函数递归调用。
	pass

def update_cls(old_c, new_c):
	# 分别处理普通函数，类和静态函数，以及嵌套类的替换。
	for name, n_attr in new_class.__dict__.items():
		pass

def update_mod(old_m, new_m):
	# 分别更新类，函数
	for name, attr in inspect.getmembers(new_m):
		pass
	# 非类和全局函数的变量保持不变
	new_m.__dict__.update(old_m)
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