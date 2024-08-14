---
tags:
  - reference
  - shader
---
# 长宽匹配

想让纹理的长宽适应屏幕的长宽，需要用$u$坐标乘以$\frac{Screen_{width}}{Screen_{height}}$，原理如下：

![[Shader知识点 2024-08-14 17.18.19.excalidraw]]

$$
\begin{align}
&\because
\left\{
\begin{matrix}
x = w\times u \\
y = h\times v \\
x = y \\
\end{matrix}
\right. \\
&\therefore v = u \times \frac{w}{h}
\end{align}
$$