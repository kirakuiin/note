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

> [!hint]
> [[C Sharp 知识点#格式化字符串|内插字符串基本格式化方法]]

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

```csharp
class A
{
	// 声明初始化
	private int v = 0;
}
```

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

	public void Dispose()
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
	protected virtual void Dispose(bool isDisposing)
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

约束条件不能太严格也不能没有。太严格的话会为用户带来巨大的限制，导致用户很难使用。而太宽松的话会导致实现的代码有太多的类型判断，执行更多的类型转换。

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
> - 协变是指：父类->子类，修饰符用`out`，一般用在返回值。
> - 逆变是指：子类->父类，修饰符用`in`，一般用在参数。
> 
> ```csharp
> class Mammals {}
> class Human : Mammals {}
> 
> delegate Mammals Handler(Human hum);
>
> public static Human CoHandler(Human hum)
> {
> }
> public static Mammals ContraHandler(Mammals animal)
> {
> }
> 
> // 返回人类也是一种哺乳动物，这是协变，正确
> Handler handler = CoHandler;
> // 传入的人类也是一种哺乳动物，这是逆变，正确
> handler += ContraHandler;
> ```
> 本质上都是[[什么是面向对象#里氏替换原则|里氏替换原则]]的表现。

## 23. 用委托要求类型参数必须支持某种方法

C# 提供的泛型约束是比较有限的，只提供了一些比较公共的约束，因此，如果你的要求是比较少见的，最好用委托的方式来描述你的约束，使得类型来支持你的方法。

```csharp
public static T Add<T>(T left, T right, Func<T, T, T> AddFunc) => AddFunc(left, right);
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

如果想对旧版接口进行支持，需要在类里添加签名正确的方法，同时要明确加以限定(*方法声明前加上接口名称*)，使得一般的调用都调用到新版的方法上面。

常见的需要实现的方法：

- `public override bool Equals(object obj)`
- `public overrdie int GetHashCode()`
- `public static bool operator ==()`
- `public static bool operator >()`
- `public int IComparable.CompareTo(object obj)`
- ...

## 27. 只把必备的契约定义在接口中，把其他功能留给扩展方法去实现

如果很多类都必须实现你定义的接口，那么接口要尽可能精简。稍后可以采用扩展方法的形式来编写一些针对该接口的方法。这样让实现接口的负担变小，并且还能享受到使用扩展方法的好处。

> [!summary] 扩展方法
> 定义一个静态类，其中的接口全部都是静态的，并且第一个参数以关键字`this`开头，后面接想要扩展的类型。
> ```csharp
> // 一个扩展string的扩展方法
> public static class StringExtension
> {
> 	public static void PrintSelf(this string str)
> 	{
> 		Console.WriteLine(str);
> 	}
> }
> ```
> > [!warning]
> > 如果子类里有和扩展方法重名的函数，一定要确保他们功能一致。因为调用哪个方法是在编译期决定的。根据写法的不同调用的方法也是不同的。

## 28. 考虑通过扩展方法增强已构造类型的功能

通过扩展方法为特定泛型增加方法，则可以极大的丰富这个特定泛型的功能，而且还可以将数据存储方式和使用方式解耦。

那C#里官方的例子来说明：

```csharp
public static int Average(this <IENumerable<int> sequence);
```

这段代码使得所有的整形序列都支持了平均数的操作。

# 合理地运用LINQ

本章主要描述了如何利用LINQ查询各种数据源的数据，此外还要演示除了查询数据之外的运用方式。
## 29. 优先考虑提供迭代器方法，而不要返回集合

提供函数返回值的时候，永远不要猜测调用方会怎么使用。是缓存起来还是按需读取是由调用方来考虑的。所以应该提供一个迭代器方法，既可以按需读取，也可以通过`ToList()`等方法转为序列。

迭代器方法使用语句`yield return`

```csharp
public static IEnumerable<char> GenerateAlphabet()
{
	var letter = 'a';
	while (letter <= 'z')
	{
		yield return letter;  // 运行到这里时控制权会返还给调用方
		letter++;
	}
}
```

> [!hint] 提前检查异常
> 由于生成器的这种按需读取的特性，异常不太容易被发现。因此如果可以的话先对输入的参数检查，然后在调用真正实现迭代器的方法。

## 30. 优先考虑通过查询语句来编写代码，而不要使用循环语句

几乎每一种命令式的循环代码都可以用查询式的写法来代替，查询式语句对比循环语句的优点有：

- 清晰的表达了编写者的意图，而循环语句代表的是实现细节
- 更容易在语句上直接扩展新功能，而循环语句很可能要另起语句来实现

以生成(0, 0) -> (99, 99)内的点举例，并且x，y之和要小于100，以到原点的距离降序排列：
```csharp
// 查询语句
from x in Enumerable.Range(0, 100)
from y in Enumerable.Range(0, 100)
where x + y < 100
orderby (x*x + y*y) descending
select Tuple.Create(x, y);

// 循环语句
var storage = new List<Tuple<int, int>>();
for (int x = 0; x < 100; ++x) {
	for (int y = 0; y < 100; ++y) {
		if (x + y < 100) {
			storage.Add(Tuple.Create(x, y));
		}
	}
}

storage.Sort((p1, p2) =>
			 (p2.Item1*p2.Item1 + p2.Item2*p2.Item2).CompareTo(
			 (p1.Item1*p1.Item1 + p1.Item2*p1.Item2)));
```

很明显查询语句要清晰的多，简洁的多。

## 31. 把针对序列的API设计的更加易于拼接

尽量将处理序列的方法都改成返回迭代器的方法。这样在效率和代码复用能力上都会得到极大的提升。

```csharp
public IEnumerable<T> SequenceMethod(IEnumerable<T> param) {
	foreach (var v in param) {
		yield return v;
	}
}

foreach (var v in OtherSeqMethod(SequenceMethod(array))) {
	//...
}
```

像例子里的这个接口很容易和其他的迭代器接口拼装到一起，并且无论拼装多少次，每个元素都只被提取出来一次。

## 32. 将迭代逻辑与操作，谓词及函数解耦

为了让你的迭代器方法更有通用型，不要在方法的内部使用某个固定的逻辑对数据源序列进行操作，而是应该通过外部传入的委托来对其进行操作，这样你的方法就会更具有一般性。

C#大部分迭代器都是按照这种方式实现的，它们接受委托的形式一般有3种：

- 操作：`Action<T>`，这种一般是直接序列元素进行操作，没有返回值。
- 谓词：`Predicate<T>`，这种一般用于筛选，返回值类型固定为**bool**。
- 函数：`Func<Tin, Tout>`，这种一般用于生成新的序列，返回值类型为最后一个泛型参数`Tout>

## 33. 等真正用到序列中的元素时再去生成

一次性生成一个序列对象有以下几个问题：

- 想要保存到其他结构里要进行一次拷贝转换。
- 无法提前终止序列元素生成的过程。
- 如果后面还需要继续处理序列里的元素，那这一步可能成为性能的瓶颈。

所以尽量采用迭代器的生成式方法，使用`yield return`按需生成，在效率和清晰性上都会得到很大的提高。

## 34. 考虑通过函数参数来放松耦合关系

设计组件时，首先要考虑能否把本组件和客户端之间的沟通方式约定成接口。如果有一些默认代码需要实现，那么可以考虑抽象类，使得调用方无需重新编写这些代码。如果你采用委托的方式来表达约定，那么用起来会更灵活，但客户端需要实现的东西也会更多。

> [!hint] 不使用委托的一个信号
> 什么情况下应该定义成接口？那就是当实现这个接口的时候意味着你对你自己所写的类型做出了承诺。比如这个类型允许比较大小，允许判断相等。反之就应该使用委托，比如：`RemoveAll()`没有提供任何类型相关的信息，它所需要的只是一个可以用来用于判断是否删除的委托而已。
## 35. 绝对不要重载扩展方法

> [!hint]
> - 扩展方法一般是用来增强接口功能的，对类有更好的方式。
> - 扩展方法扩展的是类本身的功能，不要把不属于类功能的方法放到扩展方法里。

当你针对某个类型编写扩展方法是，你应该把它们整合到一个类中，而不是在不同的命名空间内实现多套相同的方法。一旦你使用`using`指令来切换扩展方法的功能，开发者会非常困惑。

## 36. 理解查询表达式与方法调用之间的映射关系

只要你的类型实现了`IEnumerable<T>`接口，你的类型就支持所有的查询操作。如果你想要重新实现部分查询，一定要理解每一个查询语句的含义，并确保你的实现和默认的实现功能一致。

不同的查询语句的转换形式是不一样的，甚至有可能一句查询转为多句表达式。

```csharp
from n in numbers
where n < 5
select n*n;

// 等价为

numbers.Where(n => n < 5).Select(n => n*n);
```

## 37. 尽量采用惰性求值的方式来查询，而不要及早求值

与及早求值的方式相比，惰性求值基本上都能减少程序的工作量，使用起来也更加灵活。如果需要及早求值，可以用`ToList()`或`ToArray()`来做快照。

> [!hint] 是否在采用惰性求值
> 并不是说使用LINQ查询语句就一定会进行惰性求值，比如：
> ```csharp
> var result = from value in AllNumbers() // 这个方法会返回全部整数
> select value;
>
> var maxValue = result.Max();  // 这句话会导致遍历全部的数字
> ```
> 虽然AllNumbers是惰性求值，但是`Max`必须要浏览全部数据才能得出结果，实际应用时要注意这个场景。

## 38. 考虑用lambda表达式来替代方法

在很多情况下，使用方法来提炼`lambda`表达式，使得代码可以复用。但这会导致一个问题，那就是提炼后的方法返回的都是非`IEnumerable`类型的变量，这会导致其无法和其他LINQ语句协同。

所以尽量把查询操作分成许多个小方法写，小方法都返回`IEnumerable`便于拼接。小方法内部则采用`lambda`表达式来处理序列。

## 39. 不要在Func和Action中抛出异常

如果执行遍历操作，很多传入的`Func`或`Action`会直接修改序列对象本身。如果此时发生异常，则你无法判断执行到了哪一步发生了异常，很难从异常现场恢复。

> [!hint] 处理序列的一般规则
> 1. 如果可以的话就确保`Func`和`Action`不要抛出异常。
> 2. 如果不确定是否会抛出异常，那就不要直接修改源序列，而是生成一个新的序列对象，这样还能和其他操作进行拼接。等到所有操作结束后没有出现异常，再去替换源序列。

## 40. 掌握尽早执行和延迟执行之间的区别

编写C#算法时，要考虑使用结果当参数，还是用函数当参数。这两者之间是有区别的。

```csharp
// 这种是用结果当参数，尽早执行
Dostuff(Method1(), Method2());

// 这种是用函数当参数，延迟执行
DoStuff(() => Method1(), () => Method2());
```

在进行取舍时，考虑以下几点：

- 两种方式的执行结果是否一样？如果不一致则要使用结果正确的那个。
- 如果输入的信息量小，优先使用结果输入，反之应该采用函数，因为信息不一定都会用到。
- 如果时间大于空间，优先使用结果输入，反之应该采用函数。
- 如果不知道该选择哪个？那么优先使用函数，因为使用函数也有办法提前进行计算结果，反过来则不行。

## 41. 不要把开销较大的资源捕获到闭包中

如果算法使用了一些查询表达式，那么编译器会把同一个作用域内的所有表达式合起来纳入一个闭包中，并创建相应的类来实现闭包，并将其返回给调用者。

这会导致里面的被捕获的变量的生存周期可能要比你想象的要长的多。而且如果捕获了实现了`IDisposable`接口的资源还可能导致泄漏或是访问无效对象的问题，因此要**考虑闭包里面包含的对象是否有必要在闭包里，如果没有就在返回前及时进行清理，不要将可能隐含的资源释放管理责任转移给调用者**。

## 42. 注意IEnumerable和IQueryable形式的数据源之间的区别

虽然`IQueryable`是`IEnumerable`的子类型，但两者有很大的区别：

- `IEnumerable`作用于对象，而`IQueryable`作用于数据库。
- `IEnumerable`会将查询视为委托在本地执行，而`IQueryable`则将其合并在表达式树在远程执行。
- `IEnumerable`支持全部的查询表达式，而`IQueryable`支持的表达式是有限制的。

所以如果声明一个变量来保存查询结果，一定要让其类型和数据源匹配，这样才能保证健壮性和最大的效率。

## 43. 用Single()及First()来明确的验证你对查询结果所做的假设

有许多查询操作其实就是为了查找某一个值而写的，如果这是你要做的，你最好直接查出该值而不要返回一个序列。

- 如果你认为里面必然有此值并且只有一个，用`Single()`约束。如果序列的数量不等于1，则会抛出异常。
- 如果你认为里面有一个值或者没有，用`SingleOrDefault()`约束。如果没有值则返回**null**，如果大于1则抛出异常。
- 如果你想要查找某一个具体的元素，最好用`First()`，`Last()`方法。如果它不在开头，那么尽量对序列排序，截断使之位于开头结尾。这样可以让阅读者更好的领会你代码的意图。

## 44. 不要修改绑定变量

把延后执行机制和编译器实现闭包的方式的因素考虑进来，你会发现如果在定义查询表达式的时候用了某个局部变量，而在执行前修改了它的值，有可能会出现奇怪的错误，因此，捕获到闭包里的值最好不要去修改。

比如：
```csharp
int index = 0;
Func<IEnumerable<int>> sequence = () => Utilities.Generate(30, () => index++);

index = 20;
// 输出20-49，而不是0-29
foreach (var v in sequence()) {
	Console.WriteLine(v);
}
```

# 合理地运用异常

程序总是会出错的，异常是无法避免的。本章主要说明如何通过异常来清晰精准地表达程序在运行中发生的错误，以及如何让其更容易恢复。

## 45. 考虑在方法约定遭到违背时抛出异常

如果方法不能履行它和调用者所订立的契约，那么你就应该令它抛出异常。但是你要注意这个并不适合当作控制流程的常规手段，而是应该提供另一套方法在操作之前判断其有效性。

```csharp
public class Example
{
	public void TryDoWork()
	{
		if (IsOK())
		{
			Work();
		}
	}

	public void DoWork()
	{
		Work();
	}

	public bool IsOK()
	{
		// 返回判断
	}

	private void Work()
	{
		// 实际逻辑
		// 注意即便通过了测试，该抛出异常就要抛出异常
	}
}
```

## 46. 利用using与try/finally来清理资源

如果使用了非托管资源，一般都实现了`IDisposable`接口，对于这种资源有两种使用方式：

- 使用`using`语句让编译器替你自动生成`try`/`finally`语句模块。
- 主动使用`try`/`finally`来管理。

两种方式各有优点，`using`的比较简单清晰，但是管理多个非托管资源可能会比较复杂。手动捕获写法稍微复杂，但是管理多个非托管资源时会更加清晰。

> [!hint] using小窍门
> 如果你不确定对象是否实现了`IDisposable`接口，则可以用`as`来测试一下。如果没实现，则`using`语句不会执行。
> ```csharp
> using (resource as IDisposable) {}
> ```
## 47. 专门针对应用程序创建异常

虽然编写的应用不应该平凡的抛出异常，但如果某个错误没有得到立即处理的话，会长期的影响程序的运行，那么就应该抛出异常。

你抛出的异常不应该是.NET原生的异常类型，你应该创建自己的异常来给用户提供能够帮助解决错误的信息。每有一种需要用不同的措施来处理的情况就应该对应一个新的异常，反之则用相同的异常来表示。

> [!summary] 异常实现的原则
> 1. 直接继承`System.Exception`或者它的子类。
> 2. 实现其四种构造函数（可以考虑调用父类来实现）。
> 3. 如果你的异常封装了**InnerException**，也要将其传递出去，让调用方也能得知底层异常。

## 48. 优先考虑做出强异常保证

> [!summary] 异常保证有三种类型           
> - 基本保证：可以确保异常离开了产生该异常的函数后，资源不会泄露，且所有的对象必须处于有效状态。
> - 强保证：在基础保证的基础上增强，要求如果抛出异常则程序的状态不应该发生任何变化。可以理解为这个函数是原子性的，要么完全成功，要么完全失败（等于没执行这个操作）。
> - 不抛出保证：这个函数不会抛出任何异常。


.Net CLR[^1]做出了一些基本的保证，我们为了程序的健壮性应该对我们大部分的代码做出强保证。这种强保证一般是通过防御性编程来实现的。比如：

- 在复制对象上修改成功后在重新设置给原对象。
- 如果被对象是一个列表，则最好用一个类将其包装起来，使其修改可以一次性完成而不是逐步替换。

对于`finalizer`, `Dispose()`, 异常筛选器里的`when`子句和委托目标来说，它们应该实现不抛出保证。

## 49. 考虑用异常筛选器来改写先捕获异常再重新抛出的逻辑

使用了异常筛选器之后，相比于捕获，重新抛出这种方式，首先在速度上更快，其次异常会携带更多的有效信息。因此如果能用异常筛选器就要使用。

```csharp
int a = 10;
try {
	// exception operation
}
// 首先判断是否符合条件表达式，之后才会进入catch语句
catch (AException e) when (a > 5) {
	// some operation
}
catch (BException e) {
	throw; // 这会导致异常抛出的位置发生变化
}
```

## 50. 合理利用异常筛选器的副作用来实现某些效果

异常筛选器是在进入`catch`语句之前执行的，因此我们可以利用这个副作用来实现一些很优雅的方案：

> [!summary] 为所有异常打印日志
> ```csharp
> public bool LogError(Exception e)
> {
> 	// log error
> 	return false;
> }
> 
> try {
> 
> } 
> catch (Exception e) when (LogError(e)) {}
> // 其他catch字句
> ```
> 由于`when`字句会先执行，所以它会把异常记录下来，由于它一定返回`false`，所以它不会捕捉异常。如果把这句`catch`放到最后，功能就是记录所有未捕获的异常。

> [!summary] 调试时不捕获异常
> ```csharp
> try {
> 
> }
> catch (Exception e) when (!System.Diagnostics.Debugger.IsAttached) {}
> ```
> 只要程序被附加到调试器，所有的异常都会直接抛出，可以帮助程序员快速定位问题。

[^1]: Common Language Runtime，公共语言运行时。