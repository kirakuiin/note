
#+END_SRC

*** 活动图
:PROPERTIES:
:LINK: [[https://plantuml.com/zh/activity-diagram-beta][活动图]]
:End:
#+BEGIN_SRC plantuml
#+END_SRC
** MVC模式                                                         :design:
MVC 模式(Model–view–controller)是软件工程中的一种软件架构模式，它把软件系统分为
三个基本部分:模型(Model),视图(View)和控制器(Controller).
MVC模式中三个组件的详细介绍如下:
- 模型(<<<Model>>>) :: 用于封装与应用程序的业务逻辑相关的数据以及对数据的处理方法
  "Model"有对数据直接访问的权力，例如对数据库的访问."Model"不依赖"View"和
  "Controller"，也就是说，Model不关心它会被如何显示或是如何被操作.但是
  Model中数据的变化一般会通过一种刷新机制被公布.为了实现这种机制，那些用于监视此
  Model的View 必须事先在此Model上注册，由此，View可以了解在数据Model上发生的
  改变.(比如:观察者模式(软件设计模式)).
- 视图(<<<View>>>) :: 能够实现数据有目的的显示(理论上，这不是必需的).在 View 中一
  般没有程序上的逻辑.为了实现View上的刷新功能，View需要访问它监视的数据模型(Model)
  ，因此应该事先在被它监视的数据那里注册.
- 控制器(<<<Controller>>>) :: 起到不同层面间的组织作用，用于控制应用程序的流程.它
  处理事件并作出响应."事件"包括用户的行为和数据Model上的改变.
  
效果图:
[[file:../res/image/mvc_diagram.png]]
** 游戏CS架构同步模式
*** 帧同步
服务器只负责转发数据，不做任何处理，由客户端根据服务端发来的数据做战斗逻辑运算
- 优点
  1. 流量消耗小
  2. 可以离线游戏
  3. 服务端保存操作可以轻松实现回放|观战
  4. 开发效率相对较高(因为服务器基本不需要变化，可以在多个项目使用)
- 缺点
  1. 安全性差
  2. 断线重连需要追回时间
*** 状态同步
服务器负责战斗逻辑计算，并将计算的结果发给各个服务器，每个客户端实际上相当于一个
表现层
- 优点
  1. 安全性高
  2. 可以很容易的实现断线重连(重新生成场景即可)
- 缺点
  1. 流量消耗大
  2. 不能离线游戏
  3. 服务端需要保存大量数据方能实现回放|观战
  4. 开发效率相对较低(实现功能需要和客户端交流，会耽误时间)
** python相同模组重复导入问题
编写代码时碰到一个问题，在不同文件使用相同的import语句导入一个模块，结果产生了多个模块对象.
首先明确几个概念:
1. import的搜索路径存储在sys.path列表之中，在列表的前边搜索到指定模块之后不会继续搜索
2. 模块对象存储在sys.modules字典中，其中键为模块的__name__，值为模块对象
3. 模块的__name__变量是由模块被import的时候决定的
4. 在没有明确指定包结构的情况下，Python 是根据__name__来决定一个模块在包中的结构. 如果是__main__,
   则它本身是顶层模块，没有包结构. 如果是A.B.C结构，那么顶层模块是A，其内导入基本上遵循这样的原则:
   - 绝对导入 :: 一个模块只能导入自身的子模块或和它的顶层模块同级别的模块及其子模块(import C.D，import A1.B)
   - 相对导入 :: 一个模块必须有包结构且只能导入它的顶层模块内部的模块(import ..B1，from . import C1，import C1)
   - 标准导入 :: 直接导入sys.path内可以找到的模块(无论包内包外) (import xxx)

#+CAPTION: 例子
#+BEGIN_VERSE
假设目录结构为:
zz/
  yy/
    __init__.py
    xxx.py
    main.py
  __init__.py
  test.py
假设zz父目录，zz/，yy/在sys.path之中

以下语句为main.py内的语句:
~import xxx~  # xxx在同一个包下的隐式相对导入，等于from yy import xxx，或from . import xxx
则xxx模块内__name__ == 'yy.xxx'
~import yy.xxx~  # 绝对导入
则xxx模块内__name__ == 'yy.xxx'
~import zz.yy.xxx~ # 绝对导入
则xxx模块内__name__ == 'zz.yy.xxx'

以下语句为test.py内的语句:
~import xxx~ # 标准导入
则xxx模块内__name__ == 'xxx'
#+END_VERSE
此时main和test模块虽然导入了一个模块，随着import语句不同，会在sys.modules里面产生了不同的模块对象，因此可以得出以下结论:
1. 禁止使用隐式相对导入，在python2.7中可以通过 ~from __future__ import absolute_import~ 来禁止隐式相对导入
2. 使用绝对导入的时候使用相同的前缀，即都使用import yy.xxx的形式，要么都是用zz.yy.xxx
3. 更进一步的说，之所以能用不同前缀的绝对导入，是因为yy既是包里的一部分，又在sys.path中，所以父包如果在sys.path，那么子包就不应该在sys.path里面
4. 包外对象导入包内模块时，也使用绝对导入形式，不要使用标准导入

** python from import 问题
你以为from xx import yy导入的量会和原本模块的xx.yy同步变化，实际上并没有，因为:
1. ~from xx import yy~，导入本地的yy对象是xx.yy对象的引用，如果xx.yy变化会导致重新绑定
   并不会影响本地的yy变量. 如果想要共享同一个变量请使用 ~import xx~，~xx.yy~ 这样的使用方法
2. 如果yy是可变类型(list，dict)，使用append这类操作是可以共享变化的，一旦使用=等赋值语句
   则会导致本地yy的id改变，发生重新绑定
** python lambda 的陷阱
当你在类方法里使用lambda函数或者内部函数创建一个闭包的时候，闭包对象内部会持有被
引用对象的引用，如果你没有将lambda闭包对象保存起来，离开作用域lambda自然消失,
此时无事发生; 如果你将其保存了起来并且这个被引用对象是self，那么此时会产生循环引
用.
#+BEGIN_SRC python
  class Test(object):
      def __init__(self):
          # 这里已经产生了循环引用了，即便你用弱引用方法包装对象A
          # 闭包还是会会持有self的引用
          self.B = lambda: self.Print

      def __del__(self):
          print('Test is be deleted')

      def Print(self):
          """输出自身"""
          print('Test')
#+END_SRC

** python __import__的fromlist参数
__import__函数中的fromlist实际上是没有具体含义的，你可以理解为它只是一种标记，当
它不为空的时候，import为我们导入前面所写的字符串中最右边的模块. 当它为空的时候,
import将为我们导入字符串最左边的模块.

** python pyc骗局
在某个时刻，你将你包A里的__init__.py文件删掉了，但是代码里其他地方依然可以使用
A.X这种语法，你很困惑，这是为什么捏?
答: pyc没删掉，把pyc文件删掉就不能用了捏
** 协议设计的若干问题
1. 协议本身要是明确的，没有依赖的，一个协议只做一件事
2. 协议刷新数据层，界面层监听数据层获得数据的变化，不要协议直接修改界面，界面不一
   定一直存在，也不方便别人扩展
3. 信号最好带足够的参数，不要让使用者再额外获取
4. 触发信号刷新页面时，保持足够低的粒度，不要一次性刷新全部内容
5. 模型层要和界面层解耦，即模型层设计的时候先当界面层不存在，不要因为界面的需求而
   设计信号
   
** python reload迷思
有些时候你会发现reload没有生效，有一个可能的原因是:
#+begin_src python
  # file A
  import b
  a = A.Example()
  # file B
  from C import Example
  # file C
  class Example(object):
      pass
#+end_src
这个时候你修改C，reload，发现a创建的还是旧的类型，因为你用的是文件B的复制类型，想
要生效必须直接使用 ~a = C.Example()~
