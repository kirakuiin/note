---
tags:
  - reference
unity_type:
  - 编辑器
---
这几个概念在UI中经常出现，它们反应的是子节点如何在父结点中定位自身，下面分别阐述这几个概念。

# anchor

**anchor**是用两个向量`anchor min`和`anchor max`来描述的，取值域是$[0, 1]$，它们各自代表该点位置占父对象大小的比例。

![[anchor，offset和pivot 2024-09-18 19.40.44.excalidraw]]

这里有两种情况：

- 两个**anchor**重合，此时也叫做**绝对布局**，子对象大小不会随着父对象大小变化而改变。
- 两个**anchor**不重合，此时两点可以构成一个矩形框，叫做锚框，UI对象的四条边距离锚框的四个边距离不变，这叫做**相对布局**。由于父节点变化时锚点位置也会变化（因为锚点反应的是相对父对象的比例），所以UI对象大小会随着父对象大小变化而改变。

## 绝对布局

此时有`posx`，`posy`属性，用来描述[[Anchor，Pivot，Offset#Pivot|Pivot]]距离**anchor**的距离。`width`和`height`来描述物体的宽和高。

![[anchor，offset和pivot 2024-09-18 19.47.46.excalidraw]]

## 相对布局

此时有`left`，`right`，`top`，`bottom`属性，分别描述UI对象四条边距离父对象四个边的距离。

![[anchor，offset和pivot 2024-09-18 19.57.40.excalidraw]]
# Pivot

pivot反映了UI元素旋转和缩放的中心，是一个描述自身的属性，和父节点无关。一般来说如果位于左下角那么就是$(0, 0)$，右上角就是$(1, 1)$。

![[anchor，offset和pivot 2024-09-18 20.02.49.excalidraw]]

# Offset

**offset**也是一对向量，叫做`offset min`和`offset max`，它们分别描述了`anchor min`到UI左下角的距离和`anchor max`到UI右上角的距离。

![[Anchor，Pivot，Offset 2024-09-18 20.08.51.excalidraw]]

## sizeDelta

这个属性的计算方式为：
$$
sizeDelta = offset \ max - offset \ min
$$

当两个anchor重合时，它等于UI元素的大小(**size**)，当不重合时，它代表锚框大小和子对象大小的差值(**delta)。