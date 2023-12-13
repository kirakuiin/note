---
tags:
  - reference
---
> [!summary] Unity延迟调用
> 以下两种方法都只能在继承了`MonoBehaviour`里的类才能使用。
> 	1. 使用`Invoke(string, float)`来延迟调用，缺点是必须要输入方法的字符串名(可以用`nameof()`来优化)。并且即便类所挂载的对象已经消失也会调用。
> 	2. 使用`WaitForSeconds(float)`来创建一个延迟对象，这个必须要配合`StartCoroutine()`来使用。如果挂载的对象消失则不会调用。
> ```csharp
> private void Start()
> {
> 	StartCoroutine(Func());
> }
> private IEnumerator Func()
> {
> 	yield return new WaitForSeconds(3);
> 	// do sth
> }
> ```

> [!summary] Unity暂停时间方式
> 最简单的做法是将`Time.timeScale`设置为0，这个静态变量影响到所有的基于时间的调用，比如`WaitForSeconds()`, `Invoke`, `Time.deltaTime`等等，调整为其他值则可以让优秀加快或者减缓（`1`是正常速度）。
> 
> 如果你想让某部分不受这个值影响，那么可以用一些特殊的方法或者变量来实现这个效果。比如：
> - `WaitForSecondsRealtime()`
> - `Time.unscaledDeltaTime`
> - `AnimatorUpdateMode.UnscaledTime`
>
> 音频播放不受这个影响，但可以通过`AudioListener.pause`来暂停全局的声音播放。

> [!summary] 如何暂停组件
> 使用`GameObject.SetActive`即可暂停对象上的全部组件，包括内部运行的`WaitForSeconds()`，`Invoke`等延时方法；以及`Update(), FixedUpdate()`等方法。
> > [!warning]
> > `GameObject.SetActive(false)`对已经执行中的`Invoke`是无效的。
>
> 如果想暂停某个组件的话，可以设置字段`enabled`为`false`。但这个不会影响`WaitForSeconds()`等方法。
> > [!hint] 单独停止`Coroutine`和`Invoke`的方法
> > - `StopAllCoroutines()`
> > - `CancelInvoke()`