---
tags:
  - reference
unity_type:
  - 开发
---
以下方案均在`LateUpdate`中执行，确保物体的位置更新完毕后在进行显示。如果有其他相关位置计算的逻辑也在`LateUpdate`中，请在**Project Settings->Script Execution Order**中安排好执行顺序，确保以下逻辑位于最后执行。
# 方案一

一般用于显示在画面的最上层，不会被其他游戏中物体遮挡。

> [!summary] 实现思路
> 1. 使用`RectTransformUtility`将物体的世界坐标转换为屏幕坐标。
> 2. 将屏幕坐标转换为`Canvas`下某个对象的局部坐标。

```csharp
private void LateUpdate()
{
	var screenPoint = RectTransformUtility.WorldToScreenPoint(mainCamera, target.position);
	if (RectTransformUtility.ScreenPointToLocalPointInRectangle(parentTransform, screenPoint, CanvasCamera, out var pos))
	{
		transform.localPosition = pos;
	}
}
```


> [!hint]
> 如果`Canvas`采用的是**Overlay**模式，则`CanvasCamera`设置为`null`。
# 方案二

参与游戏的近大远小关系，会被其他物体遮住。

> [!summary] 实现思路
> 1. 在物体上新增一个`Canvas`，模式为**World Space**。
> 2. 保持`Canvas`的**z**轴正向和相机的**z**轴正向保持一致，这样UI看起来才不会变形。

```csharp
private void LateUpdate()
{
	transform.rotation = mainCamera.transform.rotation;
}
```
# 方案三

和方案二类似，但大小不会随距离变化。

> [!summary]
> 思路和方案二类似，不同的地方在于需要根据物体和相机的垂直距离来设置物体UI的缩放。

![[跟随物体移动的UI 2024-04-29 13.10.21.excalidraw]]

```csharp
private void LateUpdate()
{
	var posInCamera = mainCamera.transform.InverseTransformPoint(transform.position);
	var scale = posInCamera.z / baseDistance * baseScale;
	transform.localScale = new Vector3(scale.x, scale.y, 1)
}
```