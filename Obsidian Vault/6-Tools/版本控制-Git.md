---
tags:
  - reference
  - git
---
# 小技巧

> [!hint] 更好看的git log
> 在终端输入:
> ```shell
> git config --global alias.lg "log --color --graph --pretty=format:'%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset' --abbrev-commit"
> ```

> [!hint] 生成rsa公钥
> 执行命令:
> ```shell
> ssh-keygen -t rsa -C "your_email@youremail.com" 
> ```
> 后面的提示按默认即可 。

> [!hint] 配置完RSA公钥后还是无法建立ssh连接
> 可能是默认端口22被屏蔽导致的。可以将其设置为443。在id_rsa.pub所在目录创建*config*文件，内部内容为：
> ```text
> Host github.com
> 	Hostname ssh.github.com
> 	Port 443
>```

> [!warning] 重置后如何找回丢失的数据！
> 使用`git reflog`命令可以看到你所有的提交，重置记录。通过这个指令配合`git reset HEAD@{n]`可以轻松还原。