---
tags:
  - reference
  - python
---
在工作的场景中，偶尔会遇到这种情况，想要给某些函数加上日志，但是又不想要让这种业务无关的逻辑加入到代码之中，有没有办法两全其美呢？python提供了一种语法结构装饰器，专门用来解决这种类型的问题。
# 装饰器是什么

装饰器是一个可调用对象，实现了[[设计模式#装饰模式|装饰模式]]，作用就像它的名字一样，在定义时对一个对象装饰然后返回一个新的对象。最简单的场景如下所示:

```python
  def doNothing(func):  # 装饰函数，实现一些额外功能并返回一个被装饰对象
      return func
  
  def foo():  # 被装饰的对象，也是我们想要扩展功能的主体
      pass
  
  foo = doNothing(foo)  # 这一步就叫做装饰，我们在装饰函数中实现额外的功能
```

在实践中python提供了一个语法糖用来优化装饰器的写法，可以在定义被装饰函数时替换它：

```python
  @doNothing  # 和foo = doNothing(foo)完全等价
  def foo():
      pass
```

# 装饰器干什么

一般来说有三种用途:

- 对被装饰对象的功能进行补充，比如加入日志，计时等等。
- 对被装饰对象的结果进行调整，比如对某个浮点数结果进行取整。
- 对被装饰对象的功能进行替换，这种情况等价为在不改变原对象的情况下重写了它。

# 装饰器怎么写

我们回到最开始的问题，以给函数加上日志作为例子进行说明，在写法上有两个维度：

- 装饰器是否带参数?
- 装饰器是什么类型的，函数还是类?

这两个维度的就像两个自变量，总共可以组合出四种情况，下面依次阐释。
## 函数式

最普遍的装饰器实现方式，是大家使用装饰器的首选。

> [!summary] 无参数
>假设我们被装饰的函数叫做foo，我们的装饰器可以这样写:
> ```python
>   import logging
>   # 无参时装饰器定义的参数一定只有一个，那就是被装饰的对象
>   def logIt(func):   
>       # 这个函数就是用来替换被装饰对象的函数，为了支持所有情况所以采用任意参数
>       def wrapper(*args，**kwargs): 
>           print(func.__name__)  # 保存被装饰对象的名字，这一步属于额外功能
>           return func(*args，**kwargs)  # 执行被装饰对象原本的功能
>       # 还记得没有语法糖的装饰器定义吗? 我们需要返回新的函数来替换旧对象
>       return wrapper  
>   
>   @logIt  # 此时foo=logIt(foo)=wrapper，此时foo的函数签名已经是wrapper了
>   def foo():
>       pass
> ```
> 这个时候我们在调用 `foo()`，实际上调用的就是 `wrapper()` 了，`wrapper`是包含了日志功能的。

> [!summary] 有参数
> 有参数对比无参数要稍微复杂一些，但原理是一模一样的。假设我们被装饰的函数叫做foo，我们的装饰器可以这样写：
> ```python
>   # 我们给日志装饰器增加一个长度限制功能，长度超过30会被截断
>   def logItWithArgument(maxInfoLen=30):
>       # 这里对应的是无参装饰器，对比你会发现，有参的仅比无参的外边多了一层函数
>       def deco(func):
>           def wrapper(*args，**kwargs):
>               # 这里我们根据参数限制长度，然后输出日志
>               print(func.__name__[:maxInfoLen])
>               return func(*args，**kwargs)
>           return wrapper
>       # 这里要返回无参装饰器，deco才是真正的装饰器
>       return deco
>   
>   # 等价于foo=logItWithArgument(5)(foo)=deco(foo)=wrapper
>   @logItWithArgument(maxInfoLen=5)
>   def foo():
>       pass
> ```
> 此时调用 `foo()` 等价于调用 `wrapper()`，这个函数会保存函数名并将其长度限制在5。
## 类式

当一个类实现了 `__call__` 协议时，python解释器会将这个类的实例识别为一个可调用对象，所以我们实现装饰器的关键就是定义 `__call__` 协议，我们依然以`foo`作为被装饰对象。

> [!summary] 无参数
> 无参数的类装饰器以构造函数作为装饰函数，`__call__`作为内部的替换函数，可以这样写：
> ```python
>   class LogIt(object):
>       # 被装饰对象作为实例化的参数
>       def __init__(self，func):
>           self.func = func  # 被装饰对象
>   
>       # 调用协议实现了日志记录的装饰逻辑
>       def __call__(self，*args，**kwargs):
>           print(self.func.__name__)
>           return self.func(*args，**kwargs)
>   
>   @LogIt  # foo=LogIt(foo)，此时foo是LogIt的实例
>   def foo():
>       pass
> ```
> 相比于函数式实现方式，不需要函数嵌套，看起逻辑更加清晰。

> [!summary] 有参数
> 有参数类装饰器和函数式的实现方式类似，不同的点在于不以最外层函数作为参数接受者，而是以构造函数承担这个职责，可以这样写：
> ```python
>   class LogIt(object):
>       # 构造函数传入参数
>       def __init__(self，maxInfoLen):
>           self.maxInfoLen = maxInfoLen
>   
>       # 这里的实现方式和无参数的函数式装饰器一致
>       def __call__(self，func):
>           def wrapper(*args，**kwargs):
>               print(func.__name__[:self.maxInfoLen])
>               return func(*args，**kwargs)
>           return wrapper
>   
>   @LogIt(5)  # foo=LogIt(5)(foo)=wrapper
>   def foo():
>       pass
> ```
# 最佳实践

> [!faq]
> 1. 使用了装饰器之后，被装饰的函数签名变了，应该怎么办?
>
> 	答： 无论是类式的还是函数式的，本质上我们都用了一个新的东西替换了被装饰对象，尽管名字没有改变，但内在已经是新的对象了，所以签名自然也跟着变了。 python的标准库里也提供了解决方案，那就是使用`functools`里的 `wraps` 装饰器： 
> 	```python
> 	  import functools
> 	  def doNothing(func):
> 	      # 这个装饰器的作用是将func的签名信息赋予给wrapper，这样wrapper的签名也就和func保持一致了
> 	      @functools.wraps(func)
> 	      def wrapper(*args，**kwargs):
> 	          return func(*args，**kwargs)
> 	      return wrapper
> 	```
> 	用这个装饰器来修饰wrapper函数即可保证签名不变，但是类式无参数的装饰器因为结构的原因，`__call__` 就是 wrapper，所以是无法使用这个装饰器的。
>
> ---
> 
> 2. 装饰器只能用来装饰函数吗?
>
>	答：当然不是，只要你明白了两个原则，你就可以装饰任何你想装饰的对象：
>	- 原则1：装饰器的本质是定义时的一次调用，foo = deco(foo)
>	- 原则2：装饰器装饰过的对象应该和原对象的接口保持一致
>
>	所以我们也可以用装饰器来装饰类，比如给类加一个类变量：
> 	```python
> 	  def addVar(cls):
> 	      cls.IS_DECO = True
> 	      return cls
> 	  
> 	  @addVar  # foo=addVar(foo)=foo
> 	  class foo(object):
> 	      pass
> 	```
