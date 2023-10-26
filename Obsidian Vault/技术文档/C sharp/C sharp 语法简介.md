---
tags:
  - reference
  - csharp
---
C# 是一门专门为 *CLI[^1]* 设计的，完全面向对象的高级语言。本身作为 *.Net[^2]* 框架的一部分，编写 *.Net[^2]* 应用程序。

一个典型的C#程序如下所示：

```csharp
using System;

// Your program starts here...
Console.WriteLine("Hello world!");  // C# 9之后可以使用顶级语句作为入口

namespace YourNamespace
{
	class YourClass
	{
	}

	struct YourStruct
	{
	}

	interface IYourInterface
	{
	}

	delegate int YourDelegate();

	enum YourEnum
	{
	}

	namespace YourNestedNameSpace
	{
		struct YourAnotherStruct
		{
		}
	}

	class Program
	{
		static void Main(string[] args) // C# 9之前程序的入口，不能同顶级语句同时存在
		{
			// Your program starts here...
			Console.WriteLine("Hello world!");
		}
	}
}
```

下面列出上面这段代码所使用的各种特性：

- [[程序入口]]
- [[类型系统]]


---
[^1]: Common Language Infrastructure，由可执行代码和运行时环境组成，旨在不同的计算机平台和体系结构上使用相同的高级语言。
[^2]: 由一个大型的代码库构成，用于C#，C++等客户端语言，一些常见的组件有：CLR，CLS，CTS等等