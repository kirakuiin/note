---
area: session
visibility: public
date: 2026-04-29
topic: "TAGS.md 嵌套 tag 规则修订"
tags:
  - 方法论
  - OpenSpec
wiki_pages_touched:
  - "[[9-Meta/TAGS.md]]"
---

## 背景

TAGS.md 初版将嵌套 tag 规则设为"仅白名单中明确列出的嵌套路径合法"，但白名单实际未列任何嵌套路径，造成事实上的"禁止嵌套 tag"。用户指出这过于严格。

## 关键讨论

- 当前 vault 有大量嵌套 tag（`#dataStructure/graph`、`#algorithm/dp` 等），全部被归入脏 tag 清理表
- 三种方案：A) 完全禁止嵌套 / B) 白名单枚举合法嵌套路径 / C) 顶层约束 + 嵌套自由组合
- 用户选择方案 C：白名单只约束顶层（20 个 tag），嵌套路径自由组合
- 红线清单需同步修订：区分 netease 内部路径（`#工具/打包` 是红线）与公开区合法嵌套（`#工具/Git` 合法）

## 结论

采用"顶层约束 + 嵌套自由组合"规则。TAGS.md 三处修订：§1 嵌套规则、§3.5 红线嵌套说明、§4 脏 tag 清理表目标值。

## 产出物

- 更新 [[9-Meta/TAGS.md]]（§1/§3.5/§4）

## 后续

- `#interview`(7) 和 `#OpenSpec`(8) 标记为待定，Phase 3 处理
