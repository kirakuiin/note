---
tags:
  - reference
  - godot
---
# GDScript

## 在Inspector中显示提示

要用两个`#`号作为变量注释的开头。

```gds
## 范围
@export var range: int
```

## 让类全局可见

使用`class_name`来导出。

```gdscript
class_name YourClassName
extends Node

...
```

