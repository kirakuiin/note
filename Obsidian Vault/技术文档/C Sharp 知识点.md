---
tags:
  - reference
  - csharp
---
# 可访问性定义

- **public**：访问不受限制
- **private**：访问仅限于此类
- **protected**：访问仅限于此类和其派生类
- **internal**：访问仅限于当前程序集
- **protected internal**：等价于**protected**或**internal**，满足任一条件即可访问
- **private protected**：等价于**protected**和**internal**，必须同时满足两个条件才能访问

![[C Sharp 知识点 2023-10-30 14.38.46.excalidraw]]