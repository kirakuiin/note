---
tags:
  - reference
  - python
---
# 编译

从源代码到真实机器上的运行情况如下图所示：

![[Python 虚拟机和对象 2024-09-29 15.26.11.excalidraw]]

## 解释器

解释器负责将源码编译为字节码，整个过程如图：

![[Python 编译过程和对象 2024-09-29 15.34.51.excalidraw]]

最终生成的字节码一般会生成一个pyc缓存文件，它的主要作用是加速执行，当源代码没有变化时可以直接使用pyc，跳过了整个编译过程。

pyc文件头会有一些数据来表明自身的一些特征：
- py解释器版本（不同版本解释器生成的pyc无法混用）
- 使用最近修改时间还是hash值来判断文件是否变化
- 修改时间或者哈希值

> [!hint]
> 可以设置环境变量：`PYTHONDONTWRITEBYTECODE=1`来禁用字节码生成。

### 字节码的结构

字节码一般来说是串16进制代码，不过可以通过**Complier Explorer**等工具翻译成可读的形式：

```
RESUME 0

LOAD_FAST 0
LOAD_CONST 1
BINARY_OP 0
STORE_FAST 1
```

可以发现实际上这就是一套python自定义的指令集代码，指令集运行在py的虚拟机上。

> [!hint]
> 如果你查看字节码发现结尾是一大串0，它可能有如下功能：
> - 对齐
> - 预留空间

### AST

AST由Parser生成，Parser目前是采用DSL语言编写语法文件(.gram)来描述，用pegen来进行自动化生成。

编译过程中的抽象语法树实际上有很多应用，通过运行时修改语法树，我们可以在语法树中注入我们想要执行的操作。

比如：
- 去除代码中的print。
	```python
	class PrintRemover(ast.NodeTransformer):
		def visit_Call(self, node):
			if node is print:
				return ast.Pass()
			else:
				return self.generic_visit(node)
	
	tree = ast.parse(src)
	# 此时new_tree即代表移除了print的语法树。
	new_tree = PrintRemover().visit(tree)
	```
- 运行时替换assert，其实现和上个例子类似，会将简单的`assert a > 0`替换为具有更复杂说明信息的代码。

## 虚拟机

虚拟机在python逻辑代码和具体执行环境中新增了一个抽象层，使得编写逻辑不需要在关心代码执行所在的环境，提高了开发阶段编程的效率。

虚拟机主要的作用就是将python解释器产生的的字节码转换为机器码，然后在真实的物理设备上执行。

它的执行逻辑并不复杂，伪代码如下；
```python
def eval(code_obj):
	for i in len(code_obj):
		opcode = next_instruction(code_obj, i)
		if opcode == LOAD_NAME:
			pass
		elif opcode == BINARY_OP:
			pass
		# ...
```

但执行代码时，一定会涉及到多层调用，此时虚拟机会创建python frame来记录调用栈。这个栈是虚拟机独立维护的，和操作系统的调用栈作用类似，但不是一个东西。

![[Python 编译过程和对象 2024-09-29 16.19.19.excalidraw]]

这个栈主要用来实现如下功能：
- Exception
- Coroutine
- Generator

# 对象和内存管理

python的一切皆为对象，所谓对象就是：
- 具有类型和方法，这个统称为行为。
- 具有属性，也就是包含数据。

以下以CPython为基础进行说明。

## 内存模型

所有的对象在内存中都是一个PyObject对象。

```c
typedef struct {
	Py_ssize_t ob_refcnt;  // 引用计数
	PyTypeObject *ob_type; // 对象类型
} PyObject;

typedef struct {
	PyObject ob_base;
	double ob_fval;
} PyFloatObject;

// 类型对象也是一个PyObject
typedef struct {
	PyVarObject ob_base;
	// other data
} PyTypeObject;
```

## 对象类型

python中所有的类型都继承于object，所有的类型对象都是默认都是由type来创建的。所以object是由type创建的，而type也继承于object，它们分别处于继承体系和类型体系的顶点。

```python
class MyClass:
	cls_var = 1

# 等价于
MyClass = type("MyClass", (object, ), {"cls_var": 1})
```

type这里叫做metaclass，意味创建类型的类。可以这样理解。

```python
// A是type的实例，A是根据type来创建的。
A = type("A", (object, ), {})

// a是A的实例，a是根据A来创建的。
a = A()
```

## 属性查找

对于类`MyClass`，有如下的访问途径：
```python

class MyClass:
	"""
	类属性：
		从类变量直接返回：cls_var
		从property获取：x
		根据类型返回：static_method, cls_method, foo, __init__
	实例属性：
		从__dict__获取：ins_var
	"""
	cls_var = 1

	@staticmethod
	def static_method():
		pass

	@classmethod
	def class_method(cls):
		pass

	@property
	def x(self):
		pass

	def func(self):
		pass

	def __init__(self):
		self.ins_var = 1
```

如果类本身处于多继承体系中，还会存在MRO这个概念，也就是方法解析顺序。目前python采用的是C3算法。主要用于解决原来基于深度优先搜索的MRO算法不满足本地优先级，和单调性的问题。棱形继承参考[[C++#棱型继承的问题与解决方案]]。

## 内存管理

内存在：
- 变量定义，函数调用时分配。
- 存放在内存的堆区。
- 通过配置分配器，计算好大小来分配合适的内存空间。

对象分配在内存池中，内存池具有如下层次结构：
![[Python 编译过程和对象 2024-09-29 17.17.52.excalidraw]]

block的大小位于$[8b, 512b]$，同一个pool下block大小一定是一样大的。

> [!hint] 释放对象发现内存占用没有降低
> 只有一个arena下所有的内存都被释放时，整个arena才会被归还给系统。

### 垃圾回收

python采用引用计数+分代标记清除法来管理内存对象。

引用计数是指每个对象创建时带有一个为1的计数，当有新的别名指向它时，给其计数+1，当计数为0时，释放对象。
这种方法开销低，但无法解决循环引用问题，因此python引入了分代清除标记算法来回收循环引用的对象。

标记清除算法的基本思路就是沿着**根节点**[^1]出发，遍历对象构成的有向图，将它们分为可达的和不可达的节点，然后再将不可达的节点标记，然后回收。这个过程中python用双链表来存储所有可以触发垃圾回收的节点。

分代是一种用空间换时间的策略，它基于越老的对象寿命越长的理论，从而将对象分布于不同的世代中，世代越老，扫描频率越低。对象每活过一次扫描，就将对象移动到下一世代。

[^1]: 全局变量，栈中变量，静态变量等等。