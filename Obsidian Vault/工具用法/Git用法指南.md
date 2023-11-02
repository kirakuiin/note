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