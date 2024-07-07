---
tags:
  - reference
---

# 常用结构标记

## 多行结构

```latex
\begin{align}
a &= 1 \\
b &= 2 \\
\end{align}
```

$$
\begin{align}
a &= 1 \\
b &= 2 \\
\end{align}
$$

\\\\: 换行符

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

> [!hint]
> 当符号为`.`时，代表省略某一边的符号。

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

\begin{pmatrix}
x &y \\
z &q
\end{pmatrix}

\begin{bmatrix}
x &y \\
z &q
\end{bmatrix}

\begin{Bmatrix}
x &y \\
z &q
\end{Bmatrix}

\begin{vmatrix}
x &y \\
z &q
\end{vmatrix}

\begin{Vmatrix}
x &y \\
z &q
\end{Vmatrix}
```

$$
\begin{matrix}
x &y \\
z &q
\end{matrix}

\begin{pmatrix}
x &y \\
z &q
\end{pmatrix}

\begin{bmatrix}
x &y \\
z &q
\end{bmatrix}

\begin{Bmatrix}
x &y \\
z &q
\end{Bmatrix}

\begin{vmatrix}
x &y \\
z &q
\end{vmatrix}

\begin{Vmatrix}
x &y \\
z &q
\end{Vmatrix}
$$

&: 元素分隔符
\\\\: 换行符

# 字体

## 变色

```latex
\textcolor{[color]}{[text]}
```

$$
\textcolor{green} {text}
$$

color：字体颜色
text：文本内容

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

# 运算符

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

## 二项式

```latex
\binom{1}{2}
```

$$
\binom{1}{2}
$$
## 开方

```latex
\sqrt{3}
```

$$
\sqrt{3}
$$

## 分式

```latex
\frac{1}{2}
```

$$
\frac{1}{2}
$$
## 积分

```latex
\int \iint \iiint \oint
```

$$
\int \iint \iiint \oint
$$
## 加减

```latex
\pm
```

$$
\pm
$$

# 记号

## 空格

```latex
1 \, 2 \ 3 \quad 4 \qquad 5
```

$$
1 \, 2 \ 3 \quad 4 \qquad 5
$$

每个\后的结构都代表着不同大小的空格

## 撇

```latex
\prime
```

$$
\prime
$$


## 省略号

```latex
\cdots
\vdots
```

$$
\cdots \
\vdots
$$


## 垂直，平行

```latex
\perp
\parallel
```

$$
\perp \
\parallel
$$

## 上下标

```latex
a^{5}
a_{5}
```

$$
a^{5} \
a_{5}
$$

## 帽，点

```latex
\hat{a}
\dot{a}
```

$$
\hat{a} \
\dot{a}
$$

## 属于，不属于


```latex
{b}\in{a} {a}\notin{b}
```

$$
{b}\in{a} \ {a}\notin{b}
$$

## 子集


```latex
{a} \subset {b}
```

$$
{a} \subset {b}
$$
## 恒等于，不等，渐进等于，约等


```latex
{a} \equiv {b}
{a} \neq {b}
{a} \simeq {b}
{a} \approx {b}
```

$$
{a} \equiv {b} \
{a} \neq {b} \
{a} \simeq {b} \
{a} \approx {b}
$$

## 交，并


```latex
{a} \cap {b}
{a} \cup {b}
```

$$
{a} \cap {b} \
{a} \cup{b}
$$

## 比较

```latex
{a} \le {b}
{a} \ge {b}
```

$$
{a} \le {b} \
{a} \ge {b}
$$
## 箭头

```latex
{a} \leftarrow {b}
{a} \Leftarrow {b}
{a} \LeftRightarrow {b}
```

$$
{a} \leftarrow {b} \
{a} \Leftarrow {b} \
{a} \Updownarrow {b}
$$

不同方向使用不同单词即可。

## 无穷大

```latex
\infty
```

$$
\infty
$$

## 常用函数

一般用\\+对应函数名即可表达，比如：

```latex
\cos
\lim
\sin
```

$$
\cos \
\lim \
\sin \
$$

# 希腊字母

| 名称      | 语法       |
| ------- | -------- |
| alpha   | \alpha   |
| beta    | \beta    |
| gamma   | \gamma   |
| delta   | \delta   |
| epsilon | \epsilon |
| theta   | \theta   |
| lambda  | \lambda  |
| mu      | \mu      |
| pi      | \pi      |
| sigma   | \sigma   |
| phi     | \phi     |
| omega   | \omega   |

$$
\begin{align}
&\alpha A \quad \beta B \quad \gamma\Gamma \quad \delta\Delta \\
&\epsilon E \quad \theta \Theta \quad \lambda \Lambda \quad \mu M \\
&\pi \Pi \quad \sigma\Sigma \quad \phi\Phi \quad \omega\Omega
\end{align}
$$