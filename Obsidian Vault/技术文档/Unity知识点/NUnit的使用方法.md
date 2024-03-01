---
tags:
  - reference
  - csharp
unity_type:
  - 开发
---

# 常用属性

- \[TestFixture] : 将一个类标记为测试类。
	- 必须能够以无参数的形式构造。
	- 必须为`public`。
	- 构造函数不能有副作用，NUnit可能会多次构造。
	```csharp
	[TestFixture]
	public class Tests
	{
	}
	```
- \[Test] : 标记测试函数。
	- 必须是`public`。
	- 没有参数。
	- 没有返回值。
	```csharp
	[Test]
	public void AddOneNum()
	{
	}
	```
- \[OneTimeSetup] : 在所有用例开始前运行。
	```csharp
	[OneTimeSetup]
	public void InitBeforeAllCases()
	{
	}
	```
- \[OneTimeTearDown] : 在所有用例结束后运行。
	```csharp
	[OneTimeTearDown]
	public void DestroyAfterAllCases()
	{
	}
	```
- \[Setup] : 该函数在每个用例前都要执行。
	```csharp
	[Setup]
	public void Init()
	{
	}
	```
- \[TearDown] : 该函数在每个用例后都要执行。
	```csharp
	[TearDown]
	public void Destroy()
	{
	}
	```
- \[Ignore] : 运行时忽略此项测试用例。
	```csharp
	[Test]
	[Ignore("Method is ignored")]
	public void TestCase()
	{
	}
	```
- \[Category] : 给测试用例分类，以便按类别运行。
	```csharp
	[Test]
	[Category("ClassOne")]
	public void TestCase()
	{
	}
	```
- \[TestCase] : 用来标记带有参数的测试方法。运行时会注入参数值。
	```csharp
	[TestCase(1, 2)]
	public void TestCase(int a, int b)
	{
	}
	```
- \[Timeout] : 标记用例的超时时间(ms)，超时则中断。
	```csharp
	[Timeout(100)]
	public void TestCase(i)
	{
	}
	```
- \[Maxtime] : 标记用例的最大执行时间(ms)，超时报错但不取消测试。
	```csharp
	[Maxtime(300)]
	public void TestCase()
	{
	}
	```
- \[Repeat] : 标记测试方法的重复执行次数。
	```csharp
	[Repeat(5)]
	public void TestCase()
	{
	}
	```

# 常用断言

以下断言均支持字符串参数，在断言失败时使用字符串作为提示。

- `Assert.Are[Not]Equal` : 判断是否相等。
- `Assert.Are[Not]Same` : 判断是否为一个对象。
- `Assert.Contains`: 判断集合对象中是否包含某个元素。
- `Assert.Greater`, `Assert.Less` : 比较大小。
- `Assert.Is[Not]InstanceOfType` : 判断类型。
- `Assert.IsTrue`, `Assert.IsFalse` : 表达式真假判断。
- `Assert.Fail` : 主动让测试失败。
- `Assert.Ignore` : 运行时忽略一个测试。

# Unity中的用法

- 分为 