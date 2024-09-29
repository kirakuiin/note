---
tags:
  - reference
  - python
---
# 常见调试工具

- pdb
- gdb
- VS Code
- VS Natvis

## VS Code

vscode实现调试的原理如下所示：
![[Python调试和性能分析 2024-09-29 20.10.30.excalidraw]]

python提供了一个叫做`sys.settrace`的函数，用来注册