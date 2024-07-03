# 常用结构标记

## 左右整体标记

```latex
\left[char_a]
\right[char_b]
```

$$
\left[
\right]
$$

char_a：左边的符号，比如`{`就是左大括号。
char_b：右边的符号，比如`]`就是右大方括号。

## 数组

```latex
\begin{array}{[align_format]}
x &a \\
z &q
\end{array}
```

$$
\begin{array}{[rc]}
xaz &yaa \\
z &q
\end{array}
$$

align_format：代表着对齐每一列的对齐模式，可以在l，c，r之中进行选择，比如`{ll}`，`{lcl}`
&: 元素分隔符
\\\\: 换行符

## 矩阵

```latex
\begin{matrix}
x &y \\
z &q
\end{matrix}
```

$$
\begin{matrix}
x &y \\
z &q
\end{matrix}
$$

&: 元素分隔符
\\\\: 换行符

> [!hint]
> 一般会在左右两边加上方括号，所以在两边加上[[Latex用法指南#左右整体标记]]

# 字体

## 加粗

```latex
\textbf{[char]}
```

$$
\textbf{nico}
$$

char: 被加粗字符

## 斜体

```latex
\textit{[char]}
```

$$
\textit{nico}
$$

char: 被加粗字符

# 数学记号

## 求和

```latex
\sum_{i=1}^n
```

$$
\sum_{i=1}^n
$$

## 求积

```latex
\prod{i=1}^n
```

$$
\prod_{i=1}^n
$$

## 点乘

```latex
\cdot
```

$$
\cdot
$$

## 叉乘

```latex
\times
```

$$
\times
$$

## kai fang

# 特殊记号
## 帽

```latex
\hat{a}
```

$$
\hat{a}
$$
## 撇

```latex
\prime
```

$$
\prime
$$

