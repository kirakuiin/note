---
tags:
  - reference
outline: true
---
# Unity开发

```dataview
LIST
FROM "技术文档/Unity知识点"
WHERE !outline and contains(unity_type, "开发")
```

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

> [!summary] **UGUI**下`Canvas`控件的三种渲染模式。
> 所有的UI元素都必须属于一个`Canvas`对象。它有三种渲染模式：
> > [!summary] Screen Space - Overlay
> > 此模式下画布会进行缩放来适应屏幕，直接独立渲染，并不依赖场景里摄像机（也就是说没相机也会渲染）。
> > 应用场景：简单的UI元素显示。
> > > [!warning]
> > > - 该模式下3DUI对象无法被显示。
> ---
> > [!summary] Screen Space - Camera
> > UI元素由你指定的摄像机来控制。
> > 应用场景：显示3D模型。
> ---
> > [!summary] World-Space
> > 画布的行为和场景中的其他对象一致，类似于一张`Plane`。并且可以在**RectTransform**里设置画布的变换属性。
> > 应用场景：需要渲染世界内一部分的UI，也被称为叙事界面。

> [!summary] Input System使用简述
> 1. 新建一个**InputAction**来设置键位映射，这里面支持多套配置方案，可以按需激活。(使用`PlayerInput.SwitchCurrentActionMap()`)
> 2. 在想要控制的对象上附加`Player Input`组件。行为选项里一般选择*C# Event*或*Unity Event*。
> 3. 回调函数接受的参数类型为`CallbackContext`，里面比较重要的数据有：
> 	- `ReadValue()`：获取硬件的输入值。
> 	- `phase`：输入的执行阶段，比如开始，结束等等。
> 	- `action.name`：对应在键位映射里的名字。
> 	- `control.device`：这个回调是由哪个设备触发的。

> [!summary] Unity全局音量控制
> 通过`AudioMixer`来进行控制，里面可以设置若干分组，并带有父子关系（父组的设置会影响子组）。然后把每个分组的音量暴露出来(在**Inspector**里右键点击**Volume**)，就可以实现分别调整各个组的音量了。

> [!summary] 保持UI比例不变
> 在`Canvas Scaler`组件里（一般位于`Canvas`下），将*UI Scale Mode*设置为*Scale With Screen Size*。

> [!summary] `SerializeField`和`Serializable`的作用
> `SerializeField`可以让私有的可序列化字段显示在**Inspector**中。
> `Serializable`可以让自定义的对象支持序列化，简单来说就是让它向那些简单类型一样。有显示在**Inspector**里的能力，支持持久化存储。

> [!note] 如何让UI组件移动时进行对齐？
> 在Gizmo工具那里设置为矩形工具（默认快捷键为T）。

> [!note] 附加Canvas组件导致UI对象无法响应事件
> 需要在对象上附加`Graphic Raycaster`组件。

# Unity编辑器

```dataview
LIST
FROM "技术文档/Unity知识点"
WHERE !outline and contains(unity_type, "编辑器")
```

> [!summary] Unity编辑器打开**VSCode**，代码没有识别成功。
> 检查偏好设置里的外部编辑器是否设置为**VSCode**，如果设置了的话再试试点击**Regenerate project files**按钮。

> [!summary] 输入切换为使用`Input System`
> 1. 安装`Input System`包
> 2. 在**Edit->ProjectSettings->Player->Active Input Handling**里进行设置。

> [!note] 多人游戏开发测试
> 使用[ParrelSync](https://github.com/VeriorPies/ParrelSync)。在**PackageManager**使用里面提供的github链接进行安装，安装完毕后会在顶部菜单里面有*ParrelSync*选单。

> [!summary] MeshPro生成SDF文件方法。
> 1. 打开**Window->TextMeshPro->Font Asset Creator**。
> 2. 在**Character Set**选择*Characters from File*模式，设置你想要用的字集的文本文件。
> 3. 根据文本数量的多少来设置**Altas Resolution**。越多数值必须越大。
> 4. **Generate Font Altas**。

>[!note] 如何使得脚本对编辑器模式生效
>通过[ExecuteInEditMode]，[ExecuteAlways]可以让代码在编辑器模式下执行。

> [!note] TMPro富文本里如何显示图片？
> 需要根据一个包含多个图片的图集来创建一个**Sprite Asset**。可以在`TMP Settings`文件中制定默认图集所在的位置(**必须以/结尾**)。如果不指定的话则图集默认位于:
>
> *TextMesh Pro/Resources/Sprite Assets*。

# 实用插件

## UnityAssetCleaner

用于清理不需要的资源。安装后清理目录位于**Window->Delete Unused Assets**。

> [!hint]
> 注意使用后清理缓存。

## DoTween

一个用于实现程序动画的插件，支持序列动画，混合动画，十分方便。