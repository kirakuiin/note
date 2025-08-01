---
tags:
  - lan
  - zerotier
  - win32
---
利用带有公网ip的云服务器+zerotier实现高速的局域网互联功能。

# 主要步骤

## 租用云服务器

可以在腾讯云，阿里云等云服务器提供商里面找一个。购买结束后设置一下：
- 操作系统为：win server 2012
- 防火墙的规则，开放ipv4的如下端口：
	- tcp:9993
	- udp:9993
	- tcp:3180

## 在云服务器上配置zerotier


1. 远程连接云服务器，登录，后续操作都在服务器上进行。
2. 下载1.6.x版本的zerotier，最新版无法在win server 2012上运行，下载地址为：[Index of /RELEASES/](https://download.zerotier.com/RELEASES/)
3. 安装后以管理员打开控制台，执行：
```bat
cd "C:\Program Files (x86)\ZeroTier\One"
zerotier-idtool generate
zerotier-idtool generate identity.secret identity.public
zerotier-idtool initmoon identity.public > moon.json
```
以上执行后会在当前目录生成公钥私钥，并且会有一个moon.json的配置文件。
4. 编辑**moon.json**。将其中如下字段配置为服务器ip和9993端口：
```json
"stableEndpoints": ["x.x.x.x/9993"]  #配置服务器和端口，双引号是必须的
```
5. 激活moon，以管理员打开控制台，执行：
```bat
cd "C:\Program Files (x86)\ZeroTier\One"
zerotier-idtool genmoon moon.json
```
此操作会生成一个*.moon的文件（去除前导的0即为moon的id），将这个文件拷贝到`C:\ProgramData\ZeroTier\One\moons.d`目录下（如果没有就自己创建一个）。
6. 重启zerotier服务，在任务管理器->服务里面可以重启之。

## 客户端加入

1. 下载最新版zerotier，安装。
2. 将云服务器里的moons.d目录分发给客户端，然后放置`C:\ProgramData\ZeroTier\One`目录下。此时假设moons.d目录下的文件名为`000000xxxxxxxxxx.moon`，后面的10位x即为moon_id。
3. 以管理员身份打开控制台，输入：
```bat
cd "C:\Program Files (x86)\ZeroTier\One"
zerotier-cli orbit moon_id moon_id  # 入轨
zerotier-cli listpeers # 查看结果
```
如果发现列出的结果中，公网的id下面那一列最后写着MOON，就证明成功了

