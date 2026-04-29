---
tags:
  - reference
unity_type:
  - 编辑器
  - 开发
---
`ScriptableObject`是Unity提供的一个保存大量数据的数据容器，我们可以将其实例保存为自定义的资源文件。

其主要作用为：

- 编辑器模式下的数据持久化。
- 配置文件。
- 多个对象的数据复用。

# 如何创建

## 1. 定义数据模板

1. 创建一个脚本继承自`ScriptableObject`。
2. 在类中声明成员，决定存储哪些类型的数据，需要暴露的要设置为公有（里面也可以定义方法）。

```csharp
public class BulletData : ScriptableObject
{
	public float Speed;
	public float Damage;
}
```

## 2. 根据模板实例化资源文件

有两种方案：

1. 为类添加`CreateAssetMenu`特性，可以在编辑器的菜单中创建资源文件。

```csharp
[CreateAssetMenu(fileName="BulletData", menuName="数据文件/子弹数据", order=0)]
public class BulletData : ScriptableObject
{
	public float Speed;
	public float Damage;
}
```

- `fileName`: 实例化的文件名。
- `menuName`: 创建选项在菜单中的路径。（使用`/`来划分路径）
- `order`: 菜单中的显示顺序。

> [!hint]
> 在编辑器正上方的*Assets->Create*选单或者在项目目录里右键后的*Create*选单里都可以看到创建选项。

2. 新建一个脚本，引入`UnityEditor`空间，代码如下：
```csharp
using UnityEditor;
using UnityEngine;
public class Tool
{
	[MenuItem("数据文件/CreateMyData")]
	public static void CreateMyData()
	{
		var asset = ScriptableObject.CreateInstance<BulletData>();
		AssetDatabase.CreateAsset(asset, "path/to/save/file");
		AssertDatabase.SaveAssets();
		AssetDatabase.Refresh();
	}
}
```

保存代码后，会在编辑器上方边栏看到*数据文件*选项，里面会有*CreateMyData*。此为创建入口。

# 基本用法

- 在对象的*Inspector*面板中将数据文件拖拽进去（不是脚本文件）。在代码里可以用`GetComponent<BulletData>()来访问`。
- 用`Resources, AddressBundle, Addressables`来直接加载数据文件。
- 用单例来读取数据。
