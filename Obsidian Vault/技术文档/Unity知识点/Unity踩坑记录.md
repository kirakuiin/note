1. 两个2D碰撞体一切设置都没问题：
	- 层的设置
	- 其中一个含有刚体
	但却无论如何都无法出发碰撞事件和触发器事件。经过一小时的检查才发现事件函数用错了。应该用`OnCollisionEnter2D`而不是`OnCollisionEnter`。

2. UI事件不间断触发，比`OnPointerEnter`。检查之后发现是因为事件创建的对象把射线挡住了，然后触发了`OnPointerExit`，这个事件中把创建的对象给关掉了。射线重新穿透，导致无限重复这个循环。目前用`Canvas Group`组件让创建对象无法阻挡射线来解决的。

3. `AudioSource`未能正确使用`AudioMixer`的配置（仅build版本有此问题）。目前原因是build版本场景中对象和实例化的对象所引用的`AudioMixer`不是同一个对象，所以当你修改`AudioMixer`配置时，只能影响场景中的而无法影响运行时实例化的。目前的解决方案时运行时重新设置一下实例化对象所引用的`AudioMixer`。
4. 