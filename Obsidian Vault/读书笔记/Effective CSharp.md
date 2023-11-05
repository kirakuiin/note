---
tags:
  - reference
  - csharp
---
# 编程习惯

此章节会提醒你将不符合C#的做法改掉，培养C#的编程习惯。

## 1. 优先使用隐式类型的局部变量

除非开发者必须看到变量的声明类型后才能正确理解代码的含义，否则你都可以优先考虑用`var`来声明局部变量。

> [!hint]
> 对于`int double long`等基础数值类型，由于转换可能会损失精度的问题，还是需要声明其类型。

## 2.  考虑使用readonly 代替 const

`const`最好用于声明那些必须在编译期确定的值，比如枚举，`switch`标签等等，偶尔声明那些不会随着版本变化的值。除此之外都应该使用更加灵活的`readonly`

> [!summary] 两者区别
> - `const`声明的是编译器常量，只能为整形或者字符串，编译为中间语言后会直接被替换为字面量。比如：
> 	```csharp
> 	const int FIVE = 5;
> 
> 	if (value == FIVE) {}
> 	// 中间语言替换为if (value == 5) {}
> 	```
>
>- `readonly`声明的是运行时常量，可以为任何类型，编译为中间语言后依然要根据引用去查找其对象，所以性能会低于`const`。
>
> 当另一个程序集引用此程序集时，另一个程序集编译时也会将`FIVE`替换为字面量。当此程序集的定义改变时，另一个程序集的`FIVE`不会跟着一起改变。而用`readonly`修饰则变化可以同步到另一个程序集而无需其重新编译。

## 3. 优先考虑is或者as运算符，尽量少用强制类型转换

面向对象编程时应该尽量避免转型操作，但如果非转不可的话，应该使用`is`和`as`操作符进行转换。一般情况下几乎总是可以写出正确的代码。

> [!example]
> ```csharp
> if (t is AType) {
>	AType a = t as AType;
> } else {
>	// ...
> }
> ```

> [!summary] 两者区别
> - `as`只会考虑运行期是否存在可行的转换，不会考虑用户定义的转换，不会做额外操作。
> - `cast`只会考虑编译期是否存在可行的转换，虽然会考虑用户的定义，但是如果情况是运行期可以转，编译期转不了，那么转换也不会生效。并且`cast`还会通过`long`转`short`这种会丢失信息的操作。

## 4. 使用内插字符串取代string.Format()

字符串内插能以更优雅，更直观，更健壮的方式完成信息的转换，因此只使用字符串内插即可。

> [!summary] 两者区别
> - **字符串内插**通过`$"literal and {variable:format}"`的形式，使得可以直接在字符串内部编写C#表达式。完美的弥补了`String.Format()`的主要缺点，不会出现参数不匹配的问题并且容易阅读。
> - `String.Format()`必须要对生成的字符串进行验证，编译器不会验证参数和格式字符串里的参数是否匹配。并且阅读代码的人很难将参数一一对应到格式字符串里，导致其可读性交较差。

## 5. 使用FormattableString取代专门为特定区域而写的字符串

通过`FormattableString`来承载内插生成的字符串，可以方便的利用其方法将其转换为适用于各个地区的表达形式。

> [!example] 时间的表示
> 在不同国家和地区时间的表示方法不相似，通过`FormattableString`可以按照地区转换为合适的形态。
> ```csharp
> FormattableString str = ${DateTime.Now};
> Console.WriteLine(str.ToString(new CultureInfo("zh-CN")))
> ```

## 6. 不要用表示符号的名称的硬字符串来调用API

通过`nameof`方法，可以运行时动态获取符号的名字，这样在调用其他程序库的时候不会因为错误的名称而导致异常。也可以让静态分析工具能够更好的运行。

> [!example]
>```csharp
> if (func == null):
> 	throw new ArgumentNullException(nameof(func), "can't be null");
>```

## 7. 用委托表示回调

使用委托，首先保证了类型安全，其次客户端可以用最简单的lambda表达式即可实现回调。整个.Net框架的许多机制都是基于委托实现的，为了和系统API保持一致也应该使用委托。

> [!hint] 多播中异常和返回值的处理
> 由于委托是多播的，所以其返回值为最后一个执行方法的返回值。如果中途出现异常，之后全部的方法都会停止调用。为了解决这个问题，可以自己手动控制委托的调用。

 ```csharp
 public bool Foo(Func<bool> pred)
 {
	bool isTrue = true;
	foreach (var pr in pred.GetInvocationList()) {
		isContinue &= pr();
	}
	return isTrue;
 }
 ```

## 8. 用null条件运算符调用事件处理程序

使用`event?.Invoke()`来触发事件，有如下优点：
- 不会因为没有绑定处理方法导致触发异常。
- 不会因为多线程的修改导致调用那一刻触发`NullReferenceException`异常。

> [!summary] null条件运算符
> `?.`即是null条件运算符，运行时它先会判断左侧是否为空，如果为空就不再继续执行右侧操作。

## 9. 尽量避免装箱和取消装箱这两种操作

> [!summary] 装箱和取消装箱
> 装箱：值类型->引用类型
> 取消装箱：引用类型->值类型

要注意那些会把值类型转换为`System.Object`类型或接口类型的地方，例如把值类型放入集合，用值类型的值做参数来调用参数类型为`System.Object`的方法以及将这些值转换为`System.Object`等。这些做法都应该避免。

装箱和取消装箱的主要问题有：

- 可能导致潜在的性能问题。
- 可能会导致不是很明显的bug，比如：
```csharp
struct Person
{
	public string Name {set; get;}
}
List<Person> array = new() {new Person{ Name = "haha" }};
Person p = array[0];  // 这里取出来的实际上是集合里对象的拷贝，因为struct是值类型
p.Name = "xixi";  // 改名不会生效
```

## 10. 只有在应对新版基类和现有子类之间的冲突时才应该使用new修饰符

只有在一种情况下可以使用`new`修饰符修饰方法，那就是基类里引入的成员和子类里现有的重名导致冲突（这种情况一般发生在基类不受你控制的情况，比如第三方发布的基类）。这种情况下`new`运算符可以使此方法覆盖父类的实现。

即便在这情况下也要慎重考虑，这会使得其他人困惑，为何非虚方法也表现出了类似多态的性质。

> [!example]
> ```csharp
> public class Child: Parent
> {
> 	public new void Method() {} // 覆盖了父类实现
> }
> ```

# .NET 的资源管理

.NET程序运行在托管环境里，所以开发者必须从CLR[^1]的角度来考虑问题才能完全发挥这套环境的优势。这意味着你要对垃圾回收，对象生命周期以及非托管资源有一定的了解。

## 11. 理解并善用.NET的资源管理机制

由于C#程序运行在托管环境里，所以你无需担心任何内存泄露问题（无论是循环引用，迷途指针等各种情况）。但是非托管资源必须由开发者自己进行管理，比如说文件句柄，数据库链接等。

C#为非托管资源提供了两种释放机制，一个是类的**finalizer**，一个是**IDisposable**接口。任何情况下都不推荐使用**finalizer**，因为：

- 无法确定**finalizer**的释放时机，你唯一能确定的是环境一定会替你释放掉。
- 会增加垃圾回收的负担，降低系统工作效率。

> [!summary] GC回收机制
> 带有**finalizer**的对象不会立即被清理掉，而是在下一个周期根据其**finalizer**是否执行完毕来进行清理。而GC采用的世代算法会导致每多停留一个周期。在内存的驻留时间就会翻10倍。

## 12. 声明字段时，尽量直接为其设定初始值

要想保证成员变量总能得到初始化，最简单的方式就是在声明时直接为其设置初始值。这样无论通过哪个构造函数来创建对象都会正确的初始化它们，而且其时机还比所有的构造函数要早。

不过有三种情况不应该进行初始化：

1. **你想要将对象设置为0或者null**。这种环境在给声明字段分配内存时已经做过了，不需要再进行一次。
2. **不同的构造函数需要按照各自的方式来设定某个字段的初始值**。此时每种不同的方式都会重新创建一个新对象覆盖初始值对象，也会造成性能浪费。
3. **初始化对象可能会抛出异常**。这种要放到构造函数里进行捕捉。

## 13. 用适当的方式初始化类中的静态成员

类的静态成员应当在所有的实例生成之前构造完毕。要想为类静态成员设置初始值，最清晰的办法就是使用静态初始值设定和静态构造函数。

如果没有复杂逻辑，没有异常等问题直接用静态初始值设定，否则使用静态构造函数。

> [!hint] 单例模式
> C#中的静态初始化是实现[[读书笔记/设计模式/单例模式|单例模式]]最自然的形式：
> ```csharp
> class Singleton
> {
> 	private static readonly Singleton s_theOneAndOnly;
>
> 	static Singleton()
> 	{
> 		s_theOneAndOnly = new Singleton();
> 	}
>
> 	private Singleton () {}
>
> 	public Singleton GetInstance() => s_theOneAndOnly;
> }
> ```

## 14. 尽量删减重复的初始化逻辑

如果多个构造函数存在相同的初始化逻辑，那么则将共同的逻辑放到一个基础的构造函数里，让其他构造函数来调用它(使用`this`)。编译器可以对这种链式调用进行完备的优化，删除重复赋值和基类初始化。

> [!example]
> ```csharp
> class A
> {
> 	public A() : this(0, 0) {}
> 
> 	public A(int x, int y) {// ...}
> }
> ```

不要复制代码或者是写一个私有函数里面存放公共初始化逻辑，这样做编译器无法对生成代码进行优化。

> [!summary] 首次构建实例时系统的操作
> 1. 将存放静态变量的空间清零
> 2. 执行静态变量初始化语句
> 3. 执行本类静态构造函数
> 4. 将存放类实例变量的空间清零
> 5. 执行实例变量的初始化语句
> 6. 构造基类(流程和上面一致, 如果没有基类则省略此步骤)
> 7. 执行实例构造函数
>
> > [!hint] 静态的步骤只会执行一次。

^initialize-order

## 15. 不要创建无谓的对象

尽管垃圾回收器可以有效的管理内存，但在堆上创建销毁对象仍然需要一定的时间，所以不要重复去创建那些不需要重复构建的对象。有三个建议：

- 频繁创建的局部变量可以考虑变为成员变量
- 很多地方经常用到的变量可以改为类的静态变量
- 如果类型是不可变的，提供一个**builder**来逐步的构建它而不是重复创建。
> [!example]
> ```csharp
> StringBuilder msg = new("hello, ");
> msg.Append("world");
> ```

## 16. 绝对不要再构造函数里调用虚函数

在基类的构造函数里调用虚函数会使得代码效果严重依赖于派生类的实现细节，而这些细节是无法控制的，因此这种做法非常容易出问题。

> [!example]
> ```csharp
> 	var d = new Derived();  // 这里输出的会是abc，而不是hello
> 	public class Base
> 	{
> 		public Base() => VirtualFunc();
> 		public virtual void VirtualFunc() {}
> 	}
> 	public class Derived : Base
> 	{
> 		private string str = "abc";
> 		public Derived() => str = "hello";
> 		public override void VirtualFunc()
> 		{
> 			Console.WriteLine(str);
> 		}
> 	}
> ```

原因可以参考[[Effective CSharp#^initialize-order|初始化顺序]]。

## 17. 实现标准的dispose模式

在类继承树根部的类总是应该实现`IDisposable`接口，如果本身含有非托管资源或者有实现了`IDisposable`接口的成员时，必须要实现`finalizer`。以防客户忘记主动释放。另外释放操作最好由一个虚函数实现，以供子类重载。

一个标准的dispose框架如下所示：

```csharp
class Base : IDisposable
{
	private bool _isDisposed = false;

	public override void Dispose()
	{
		Dispose(true);
		GC.SuppressFinalize(this);
	}

	~Base()
	{
		Dispose(false);
	}

	// 执行实际的释放逻辑，供finalizer和Dispose调用
	// isDisposing代表是在接口中调用还是在finalizer里调用
	protected virtual void Dispose(isDisposing)
	{
		if (_isDisposed) {
			return;
		}
		if (isDisposing) {
			// 释放托管资源
		}
		// 释放非托管资源
		_isDisposed = true;
	}
}
```

> [!hint] 释放资源的注意事项
> 实现时要注意释放方法里不要做任何和释放无关的事情，确保里面的唯一操作就是释放资源。

# 合理地运用泛型

定义泛型类型会增加程序的开销，但有时会令程序代码更加简洁。本章主要讲解泛型的各种用法，并演示怎样编写可以提高工作效率的泛型类型和泛型方法。

## 18. 只定义刚好够用的约束条件

约束条件不能太严格也不能没有。太严格的话会为用户带来巨大的限制，倒置用户很难使用。而太宽松的话会导致实现的代码有太多的类型判断，执行更多的类型转换。

> [!summary] 泛型约束
> 形如public class A\<T\> **where T : \<constraint\>** {}。
> 
> 这里的**where**子句代表的就是对类型T的约束。如果没有约束的话泛型方法里只能用`System.Object`提供的方法，而通过类型约束可以在泛型方法里调用更多方法。

## 19. 通过运行期类型检查实现特定的泛型算法

通过运行期的类型检查，可以在尽可能小的约束的条件下提供更好的实现方式。比如：

```csharp
public IEnumerator<T> GetEnumerator()
{
	if (source is string) {
		// algo for string
	}
	else if (source is ICollection<T>) {
		// algo for ICollection
	}
	else {
		// default algo
	}
}
```

通过检查可以对不同的类型提供更高效的实现方式。

## 20. 通过IComparable\<T\> 及 IComparer\<T\>定义顺序关系

这两个接口是定义排序关系的标准机制。为了给类型支持排序能力，你应该这样做：

```csharp
class YourType : IComparable<YourType>, IComparable
{
	// 实现接口
	public int ComepareTo(Customer other);
	public int IComparable.CompareTo(object obj);
	// 实现关系操作符
	public static bool operator >(YourType left, YourType right);
	public static bool operator >=(YourType left, YourType right);
	public static bool operator <(YourType left, YourType right);
	public static bool operator <=(YourType left, YourType right);
}
```

为了向后兼容，非泛型的`IComparable`也要实现。

## 21. 创建泛型类时，总是应该给实现了IDisposable的类型参数提供支持

如果你在泛型类内部创建了`T`的实例，那么就必须要考虑它包含非托管资源的可能性。有这么几种可能性：

- 直接在方法内部创建了`T`，此时要负责释放其资源。
```csharp
public void Func()
{
	T instance = new T();
	using (instance as IDisposable)
	{
		instance.DoWork();
	}
}
```
- 将创建的T当作类的成员，此时要[[Effective CSharp#17. 实现标准的dispose模式|实现标准的dispose模式]]，泛型类本身也要实现`IDisposable`接口。

当然也可以将创建类的职责从泛型类中分离，由用户将创建好的对象传进来，这样泛型类内部就没这么复杂了。

## 22. 考虑支持泛型协变与逆变

C# 允许开发者在泛型接口和委托中运用`in`与`out`修饰符，以表达它们与类型参数之间的逆变与协变关系。使用这两个修饰符将使得接口和委托接受子类，父类之间类型转换，提高了它们的易用性。

> [!summary] 协变与逆变
> - 协变是指：子类->父类，修饰符用`out`，一般用在返回值。
> - 逆变是指：父类->子类，修饰符用`in`，一般用在参数。

## 23. 用委托要求类型参数必须支持某种方法

C# 提供的泛型约束是比较有限的，只提供了一些比较公共的约束，因此，如果你的要求是比较少见的，最好用委托的方式来描述你的约束，使得类型来支持你的方法。

```csharp
public static T Add<T>(T left, T right, Func<T, T, T> AddFunc) = > AddFunc(left, right);
```

像上面这种就是要求T必须支持相加操作，所以提供了一个委托来让用户提供相加操作。用户可以很方便的使用`lambda`来支持这一功能。

## 24. 如果有泛型方法，就不要再创建针对基类或者接口的重载版本

C#编译器的规则是如果泛型方法和重载版本同时存在的话，会优先调用泛型方法而不是重载方法。这是因为当你传入一个子类对象时，泛型方法可以直接创建子类对象的代码，而重载版本需要进行一次隐式转换。所以一般情况下泛型方法总是**更优的**。

> [!hint] 如果必须要重载该怎么做
为了能克服上面所说的问题，你要为每一个子类版本都单独实现一个方法，这样才会让编译器判定你的重载是更优的。

## 25. 如果不需要把类型参数所表示的对象设为实例字段，那么应该优先考虑泛型方法

当你的类符合这两种情况才应该设置为泛型类：

- 你的类需要将必须用泛型来表达的变量作为其成员。
- 你的类需要实现泛型版本的接口。

> [!hint] 泛型方法的优点
> 1. 调用起来简单，不用指明类型。
> 2. 扩展更加灵活，比如你实现了一个更优版本直接加到类里即可，编译器会自动调用更优版本。如果用泛型类的话因为代码里指明了泛型类型，所以自动调用你的更优版本。

## 26. 实现泛型接口的同时，还应该实现非泛型接口

## 27. 只把必备的契约定义在接口中，把其他功能留给扩展方法去实现

## 28. 考虑通过扩展方法增强以构造类型的功能

# 合理地运用LINQ

本章主要描述了如何利用LINQ查询各种数据源的数据，此外还要演示除了查询数据之外的运用方式。
## 29. 优先考虑提供迭代器方法，而不要返回集合

## 30. 优先考虑通过查询语句来编写代码，而不要使用循环语句

# 合理地运用异常

程序总是会出错的，异常是无法避免的。本章主要说明如何通过异常来清晰精准地表达程序在运行中发生的错误，以及如何让其更容易恢复。

## 45. 考虑在方法约定遭到违背时抛出异常

[^1]: Common Language Runtime，公共语言运行时。