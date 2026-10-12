# 反转7 Flip 7 规则与代码实现规格

采集截止日期：2026 年 10 月 12 日，北京时间。文档版本：1.0。

本文将《Flip 7》及《Flip 7: With A Vengeance》的规则整理为不依赖美术或 UI 资源的游戏逻辑规格。覆盖 BGG 元数据、配件和完整牌表、准备、玩家决策、行动结算、计分、结束条件、官方可选规则及可复现的验收案例。正文采用中文重新表述，不是官方规则书的逐字译本。

“反转7”按用户给出的名称对应 Flip 7；中文销售资料还使用“7连翻”“七翻天”“七来运转”等名称。代码与存档应以英文名、BGG ID 和规则版本识别游戏，避免中文名称差异。[S01][S19]

**范围说明：With A Vengeance 是可以独立游玩的续作，BGG 将其标记为 Reimplements Flip 7，不是必须加入基础版才能玩的扩展。** 本文为基础版、复仇版标准模式和复仇版 Brutal Mode 分别定义规则配置；其他正式系列版本见第 8 节。未发现官方基础版与复仇版混合牌组的统一规则，不能将网络上的混牌玩法自动视为官方扩展。[S02][S07][S08]

## 1 来源和规则版本

规则依据按以下顺序使用：出版方最新 FAQ 或具名开发者裁定、出版方当前提供的规则书、由出版方维护的 Dized 规则、引用出版方答复的社区 FAQ。零售说明、攻略和现有计分器仅作交叉核对。

基础版采用官网现行文件 `25_FLIP_7_TB_RULES_C_Rev_9_2_25_ND.pdf`，内部注明 **Ruleset Edition 3.1**，版权年份 2025。复仇版采用 `26_FLIP_7_VENGEANCE_RULES_C.pdf`，内部注明 **Ruleset Edition 1**，版权年份 2026。[S03][S07]

基础版规则书 PDF 有 2 个物理页面，每个页面排列多个折页，页内印有逻辑页码 1 至 12。复仇版 PDF 有 14 个物理页面，封面后规则印刷页码为 1 至 12，最后一页是版权页。以下引用“规则书第几页”时使用印刷页码。

本文中“官方”表示规则书或出版方答复直接支持；“推导”表示为代码实现明确化的逻辑；“实现约定”表示公开材料未完全裁定，采用可配置默认值。第 10 节集中列出这些区别。BGG 动态统计是搜索索引快照，不能视为采集瞬间实时 API 数值。

## 2 BGG 元数据

### 2.1 游戏身份和游玩参数

| 字段 | Flip 7 基础版 | Flip 7 With A Vengeance |
| --- | --- | --- |
| BGG ID | 420087 | 463441 |
| 年份 | 2024 | 2026 |
| 条目关系 | 原始游戏 | Reimplements Flip 7 |
| 设计者 | Eric Olsen | Eric Olsen、Alyssa Swatek |
| 美术 | O'Neil Mabile | O'Neil Mabile |
| 原始出版方 | The Op Games／USAopoly | The Op Games／USAopoly |
| BGG 人数 | 3–18 人 | 3–28 人 |
| BGG 社区建议人数 | 3–9 人 | 3–8 人 |
| BGG 社区最佳人数 | 5–6 人 | 4 人 |
| BGG 时长 | 20 分钟 | 20 分钟 |
| 标注年龄 | 8 岁以上 | 8 岁以上 |
| 社区建议年龄 | 6 岁以上 | 6 岁以上 |
| 复杂度 Weight | 约 1.04／5 | 约 1.04／5 |
| 搜索快照平均评分 | 7.203／10 | 7.136／10 |
| 搜索快照评分人数 | 26,580 | 2,391 |
| 搜索快照综合排名 | 514 | 约 1,941–1,942 |
| 搜索快照派对排名 | 41 | 97 |
| 搜索快照家庭排名 | 131 | 此次未确认 |
| 配件核心 | 94 张游戏牌 | 108 张游戏牌 |

来源：[S01][S02][S12][S13]。搜索抓取时间不同会造成排名或票数差异，应把评分、排名和社区建议作为带日期的元数据，不能写入胜负判定。

**人数存在来源差异。** 两份官方规则书都写 3+ 人，并建议超过 18 人使用第二副牌；复仇版 BGG 页面写 3–28 人。程序可以支持任意座位数，但默认用一副牌时建议配置 3–18 人，不把 BGG 的 28 人当作官网确认的一副牌上限。[S03][S07]

### 2.2 BGG 分类与标签

| BGG 字段 | 基础版 | 复仇版 |
| --- | --- | --- |
| Type | Family、Party；部分较旧索引仅显示 Party | Party |
| Category | Card Game、Novel-based、Number、Party Game | Card Game、Number、Party Game |
| Mechanism | Interrupts、Push Your Luck、Score-and-Reset Game、Take That | Interrupts、Push Your Luck、Score-and-Reset Game、Take That |
| Family | Authors: Dr. Seuss；Books: How the Grinch Stole Christmas；Components: External Score Sheet Required；Digital Implementations: Board Game Arena；Holidays: Christmas；Misc: DIZED Tutorial | Components: External Score Sheet Required；Digital Implementations: Board Game Arena |

来源：[S01][S02]。基础版条目收录了 Grinch 等主题版本，所以出现 Novel-based、Dr. Seuss 和 Christmas 标签；这些不是原始数字卡牌玩法必须包含的主题或机制。BGG 可能合并版本信息，检索到相关标签时不要据此生成新的规则。

机制中文含义：Interrupts 为行动打断正常发牌；Push Your Luck 为继续拿牌承担爆牌风险；Score-and-Reset Game 为每轮累计分数并清空本轮牌面；Take That 为使用效果影响其他玩家。

BGG 的 **Community Tags** 是另一组用户自由标签，不等同于 Type、Category、Mechanism 或 Family。此次没有取得可完整核验的自由标签集合，因此该字段应保存为 `null`，而不是空数组或编造标签。可另设本项目检索标签：`卡牌、派对、家庭、押运气、数字收集、多人互相影响`，并注明这是文档整理标签。

### 2.3 建议元数据结构

```json
{
  "bgg_id": 420087,
  "title": "Flip 7",
  "year": 2024,
  "ruleset": "base_3_1",
  "players_bgg": {"min": 3, "max": 18},
  "players_official": {"min": 3, "max": null},
  "recommended_extra_deck_above": 18,
  "playing_minutes": {"min": 20, "max": 20},
  "minimum_age": 8,
  "designers": ["Eric Olsen"],
  "artists": ["O'Neil Mabile"],
  "publishers_primary": ["The Op Games"],
  "categories": ["Card Game", "Novel-based", "Number", "Party Game"],
  "mechanisms": ["Interrupts", "Push Your Luck", "Score-and-Reset Game", "Take That"],
  "community_tags": null,
  "metadata_retrieved_at": "2026-10-12",
  "dynamic_statistics_source": "BGG search-index snapshot"
}
```

## 3 基本配件和完整牌表

### 3.1 基础版 94 张

盒内为 94 张游戏牌和规则书。计分用纸笔由玩家另备；官网提供计分纸和网页计分器。没有棋盘、骰子、棋子、个人手牌或需要的图像资源。[S03][S04]

| 卡牌类型 | 牌面 | 数量 | 数字值 | 计入 Flip 7 张数 |
| --- | --- | ---: | ---: | --- |
| NUMBER | 0 | 1 | 0 | 是 |
| NUMBER | 1 | 1 | 1 | 是 |
| NUMBER | 2 | 2 | 2 | 是 |
| NUMBER | 3 | 3 | 3 | 是 |
| NUMBER | 4 | 4 | 4 | 是 |
| NUMBER | 5 | 5 | 5 | 是 |
| NUMBER | 6 | 6 | 6 | 是 |
| NUMBER | 7 | 7 | 7 | 是 |
| NUMBER | 8 | 8 | 8 | 是 |
| NUMBER | 9 | 9 | 9 | 是 |
| NUMBER | 10 | 10 | 10 | 是 |
| NUMBER | 11 | 11 | 11 | 是 |
| NUMBER | 12 | 12 | 12 | 是 |
| ADD | +2、+4、+6、+8、+10 | 各 1 | 不适用 | 否 |
| MULTIPLY | ×2 | 1 | 不适用 | 否 |
| FREEZE | Freeze | 3 | 不适用 | 否 |
| FLIP_THREE | Flip Three | 3 | 不适用 | 否 |
| SECOND_CHANCE | Second Chance | 3 | 不适用 | 否 |

核对：数字牌 `1 + (1+2+…+12) = 79`；分数修正牌 6；行动牌 9；合计 `79+6+9=94`。

0 是普通数字牌，只是分值为 0；不要给基础版的 0 加上复仇版清零或强制继续拿牌的效果。分数修正的 +2 和数字 2 属于不同类型，不能用牌面数字直接判重。

### 3.2 复仇版 108 张

盒内为 108 张游戏牌和规则书，同样另备计分工具。以下数量依据规则书配件图逐项核对；特殊 7、特殊 13 各替代一张相同数字的普通牌。[S07]

| 卡牌类型 | 牌面 | 数量 | 数字值 | 计入 Flip 7 张数 |
| --- | --- | ---: | ---: | --- |
| NUMBER | 1 | 1 | 1 | 是 |
| NUMBER | 2 | 2 | 2 | 是 |
| NUMBER | 3 | 3 | 3 | 是 |
| NUMBER | 4 | 4 | 4 | 是 |
| NUMBER | 5 | 5 | 5 | 是 |
| NUMBER | 6 | 6 | 6 | 是 |
| NUMBER | 普通 7 | 6 | 7 | 是 |
| NUMBER | 8 | 8 | 8 | 是 |
| NUMBER | 9 | 9 | 9 | 是 |
| NUMBER | 10 | 10 | 10 | 是 |
| NUMBER | 11 | 11 | 11 | 是 |
| NUMBER | 12 | 12 | 12 | 是 |
| NUMBER | 普通 13 | 12 | 13 | 是 |
| ZERO | The Zero | 1 | 0 | 是 |
| UNLUCKY_SEVEN | Unlucky 7 | 1 | 7 | 是 |
| LUCKY_THIRTEEN | Lucky 13 | 1 | 13 | 是 |
| SUBTRACT | −2、−4、−6、−8、−10 | 各 1 | 不适用 | 否 |
| DIVIDE | ÷2 | 1 | 不适用 | 否 |
| JUST_ONE_MORE | Just One More | 2 | 不适用 | 否 |
| FLIP_FOUR | Flip Four | 2 | 不适用 | 否 |
| SWAP | Swap | 2 | 不适用 | 否 |
| STEAL | Steal | 2 | 不适用 | 否 |
| DISCARD | Discard | 2 | 不适用 | 否 |

核对：普通数字牌 `1+…+13−1−1 = 89`，特殊数字牌 3，分数修正牌 6，行动牌 10；合计 `89+3+6+10=108`。数字值分布为 0×1，1×1，2×2，…，7×7，…，13×13。

复仇版没有基础版的 +分修正、×2、Freeze、Flip Three 或 Second Chance。若产品内额外附有广告卡，不能混入游戏牌堆。BGG 护套条目曾记录 114 张且明确包含 6 张非游戏广告卡，108 才是游戏逻辑的牌数。[S02][S07]

### 3.3 卡牌数据要求

每一张实体牌都有独立 `card_id`；卡牌模板包含 `kind`、`number_value`、`modifier_value`、`copies`。判重依据 `number_value`，计分与效果依据 `kind`。普通 7 和 Unlucky 7、普通 13 和 Lucky 13 数字相同但效果不同。

```text
Card = { card_id, kind, number_value?, modifier_value? }
Kind = NUMBER | ADD | MULTIPLY | FREEZE | FLIP_THREE | SECOND_CHANCE
     | ZERO | UNLUCKY_SEVEN | LUCKY_THIRTEEN
     | SUBTRACT | DIVIDE | JUST_ONE_MORE | FLIP_FOUR | SWAP | STEAL | DISCARD
```

## 4 共用游戏框架

### 4.1 区域和信息

全桌共用一副抽牌堆。每名玩家有本轮牌列：数字牌一行，修正牌和持有的特殊牌可分列存储。抽出的牌正面公开，没有隐藏手牌，也没有将行动存起来以后主动使用的机制。

区分三个回收区域：已经进入弃牌堆、仍在玩家面前但已失效的本轮牌、尚待处理的行动牌。中途洗牌只能使用真正已经弃掉的牌，不能回收仍在玩家面前的牌。[S03][S07]

### 4.2 状态定义

| 状态 | 正常轮到时询问 Hit／Stay | 基础版可成为行动目标 | 复仇版标准可成为行动目标 |
| --- | --- | --- | --- |
| ACTIVE | 是 | 是 | 是 |
| STAYED | 否 | 否 | 是 |
| FROZEN／FORCED_STAY | 否 | 否 | 是 |
| BUSTED | 否 | 否 | 否 |

基础版 Freeze 可以实现为 `STAYED` 加上 `stay_reason=FREEZE`；复仇版 Just One More 可以实现为 `STAYED` 加上 `stay_reason=JUST_ONE_MORE`。保留原因方便日志和统计，不需要额外牌面资源。

复仇版 Brutal Mode 仅放宽 **Modifier** 的目标到 BUSTED，未放宽普通行动或数字牌的目标。所有玩家在下一轮重新变成 ACTIVE。

### 4.3 准备和座位顺序

1. 根据规则配置构建整副牌，核对数量。
2. 所有玩家累计分数从 0 开始；彻底洗牌。
3. 任意选一位玩家当第一轮发牌者 Dealer，发牌者也参与游戏，没有额外胜利条件。
4. 座位按顺时针固定。复仇版明确从 Dealer 左侧玩家开始；基础版写按顺序发牌，采用相同的 Dealer 左侧起始顺序作为实现默认。[S03][S07]
5. 每轮结束 Dealer 向左移动一位，下一轮起始座位随之移动。剩余抽牌堆保持原顺序。

### 4.4 开局发牌

先沿座位顺序进行开局发牌：通常每名玩家获得一张公开牌，包括 Dealer。抽到需处理的行动时暂停发牌，完整解决其效果后再继续原发牌游标。复仇版抽到修正牌时也立即暂停，选择目标后才继续。

开局结束时，玩家可能有数字牌、只有修正牌、没有牌，或者已经因强制拿牌持有多张牌；也可能在轮到第一次拿牌前已经退出本轮。不能写成“循环发到每人都有一张数字牌”。[S03][S05][S07]

基础版社区 FAQ 引用出版方裁定：若某玩家在自己的开局座位到来前已通过 Flip Three 获得牌且没有爆牌，到该座位时可以选择 Hit 或 Stay，不强制追加所谓的第一张牌。已被冻结或爆牌者直接跳过。其证据和开关见第 10 节；复仇版不自动继承这项基础版补充裁定。[S06]

### 4.5 正常轮转

每次轮到 ACTIVE 玩家，作一次决策：

- **Hit**：接受抽牌堆顶一张牌，公开并处理；本次处理完成后正常游标移到下一座位。
- **Stay**：结束自己本轮的正常拿牌机会，保留本轮计分资格。基础版要求至少有一张牌在自己面前才能选择 Stay；只有修正牌或 Second Chance 也属于有牌。[S03][S05]

“一轮游戏”是从开局到所有人退出或有人达成 Flip 7。“一圈轮转”是游标经过全部座位一次。玩家可以跨多圈累积到 7 张数字牌；并不要求在一次普通 Hit 中连续抽出七张。

任何强制拿牌和行动链完成后，都返回 **最初正常抽到行动牌者之后** 的下一个有效座位，而不是从最后被影响者之后继续。应保存正常游标，不让嵌套行动覆盖它。[S05]

### 4.6 本轮结束和整局结束

两种本轮结束条件：

1. 所有人都不是 ACTIVE，且本轮已产生的必做行动已经处理完。
2. 任一玩家达成有效的 Flip 7；此时立即结束本轮，停止所有尚未进行的翻牌和行动。

本轮结束时给所有玩家结算一次分数。已 Stay 的玩家不应立即修改累计分，否则复仇版后续偷牌、扣分或爆牌会需要错误地撤回分数。

结算后，若至少一人累计分数达到或超过 200，累计最高分者胜出。不是某人暂时达到 200 就立即终止，也不是结束时首先拿到 200 的座位获胜。最高分并列时继续加赛，全体玩家参加，累计分不清零，直至出现唯一最高分；基础版 FAQ 直接确认这一点。复仇版规则书未单列平局条款，本文默认沿用全体加赛，并在第 10 节注明。[S03][S05][S07]

### 4.7 弃牌与洗牌

本轮结算后将本轮剩余牌移入弃牌堆。下一轮直接继续使用剩余抽牌堆，不把弃牌重新混进去。

只有抽牌堆耗尽才洗弃牌堆。中途需要洗牌时，保留所有玩家面前的本轮牌，包括已爆牌玩家的牌；待处理效果持有的牌也不参与洗牌。牌堆与弃牌堆同时空时没有官方完整裁定，处理见第 10 节。

## 5 基础版完整规则

### 5.1 普通数字牌和爆牌

新数字与玩家当前数字牌不同：加入牌列，按其数值贡献分数，并增加 Flip 7 张数。

新数字与已有数字相同：若没有 Second Chance，立即 BUSTED，本轮得分 0，数字牌和加分修正均不计分。已有累计分数不受影响。若有 Second Chance，按 5.4 处理。

每次数字牌有效进入牌列后立即检查是否达到 7 张不同数字牌。达到即触发本轮结束，该玩家获得 +15 奖励。其他未爆牌玩家按现有牌面正常计分，不获得 +15。

### 5.2 分数修正牌

+2、+4、+6、+8、+10：由抽到者保留，每张在本轮最终计分时增加对应分数。×2：由抽到者保留，仅将数字牌分数总和乘二。

修正牌不是数字牌，不判重，不增加 Flip 7 张数。只有修正牌也能 Stay；例如只有 +4 得 4 分，只有 ×2 得 0 分。[S03][S05]

### 5.3 Freeze 冻结

抽到者选择自己或任意其他 ACTIVE 玩家作为目标。目标立即退出正常轮转，其本轮分数保留。可以冻结尚未拿到开局第一张牌的玩家，此时其分数为 0。仅剩一个 ACTIVE 玩家时必须冻结自己。[S03][S05]

Second Chance 不能抵挡 Freeze。已 Stay、已冻结和已爆牌的玩家不能成为新的基础版行动目标。

### 5.4 Second Chance 再来一次

获得后作为持有牌保留。本轮拥有它时收到重复数字，就将 **新收到的重复数字牌与 Second Chance** 丢弃，保留原有同数字牌，玩家仍 ACTIVE。普通 Hit 不因此再补抽一张；下一个正常回合才能继续选择。[S03][S05]

一名玩家同时最多持有一张。已经有一张又抽到第二张时，必须立即交给其他 ACTIVE 且没有 Second Chance 的玩家；没有合法接收者则丢弃新牌。不能先暂存第二张，等第一张被消耗后再取回。

通用行动条款允许将行动给予任意 ACTIVE 玩家；Second Chance 的具体牌文写“Keep this card”。本文默认允许在首次获得时自留或立即赠予合法 ACTIVE 玩家，依据官网行动目标条款和引用出版方答复的补充说明；若要逐字模拟具体牌文，可配置 `second_chance_initial_assignment=keep_self`。同一次 Flip Three 中没有已有保命牌时，立即取得的新保命牌可保护后续翻出的重复数字。[S03][S05][S15]

未使用的 Second Chance 在本轮结束丢弃，不跨轮继承。使用它不增加本轮分数，不计入 Flip 7，不取消 Flip Three 的剩余必抽张数。

### 5.5 Flip Three 强制翻三张

抽到者选择任意 ACTIVE 玩家，包括自己；只剩自己 ACTIVE 时必须给自己。目标必须依次接受最多三张新牌，不得在中途自主 Stay。

计数按 **实际从牌堆翻出的实体牌**：数字、修正和行动都算一张。最初触发 Flip Three 的那张行动牌不算在追加三张内。

结算流程：

1. 一次翻一张；数字进入牌列后判重或检查 Flip 7。
2. 真正爆牌立即停止，不继续翻足三张；达成 Flip 7 立即结束全桌本轮。
3. 修正牌立即保留。Second Chance 立即分配，能在同一组三张的后续抽牌中使用。
4. 本组翻出的 Freeze 或另一张 Flip Three 暂存，计入三张，但暂时不选目标、不发动。
5. 若本组三张期间爆牌或达成 Flip 7，丢弃本组未分配的暂存行动。
6. 若完整翻完三张且没有爆牌或 Flip 7，将暂存行动按抽到顺序 **全部先分配目标，然后按该顺序执行**。接收者不能把已经分配给自己的强制行动重新转送。[S03][S06]

例如暂存 Freeze 然后 Flip Three，两张都分配给 B：先冻结 B，后来的 Flip Three 因 B 已经无效而丢弃。两张 Flip Three 都给 B：第一张处理完且 B 仍 ACTIVE，才执行第二张；第一张让 B 爆牌时第二张取消。

**嵌套次序的代码约定：使用全局先进先出行动队列。** 某批先分配的其他行动保留原顺位，后来通过 Flip Three 新产生的行动追加到队尾，而不是递归插队。社区补充案例说明：B 的新 Flip Three 可以指向尚未真正执行 Freeze 的 C，但较早已排队的 Freeze 随后先执行，C 的新 Flip Three 因冻结取消。[S06][S16]

### 5.6 基础版计分

对未爆牌者：

```text
number_sum = sum(number_value of all current Number cards)
number_points = number_sum * (2 if owns MULTIPLY else 1)
modifier_points = sum(all ADD modifier values)
round_score = number_points + modifier_points + (15 if Flip7 winner else 0)
```

对 BUSTED 玩家：`round_score=0`。

×2 不翻倍 +分修正和 Flip 7 的 15 分；这是官网 FAQ 明确确认的操作顺序。示例：数字合计 36、×2、+10，得 `36×2+10=82`；若还达成 Flip 7 则 97 分。[S04]

一副牌只有一张 ×2。使用多副牌时可能出现多个 ×2，官方没有完整叠加说明，需显式开启第 10 节的多牌堆约定。

## 6 复仇版标准模式完整规则

### 6.1 与基础版的差异

核心仍为 Hit／Stay、重复数字爆牌、有效 7 张数字结束本轮和累计 200 分。主要变化是：

- Stay 不再保护牌列；牌保持正面，可被行动或扣分修正影响。
- 行动和修正的合法玩家目标是所有 **没有爆牌** 的玩家，包括自主或被强制 Stay 的人。
- 被 Stay 的玩家受到强制抽牌也不恢复 ACTIVE；效果结束后仍 Stay。
- 数字范围扩展到 13，有 The Zero、Unlucky 7 和 Lucky 13 三种特殊数字。
- 加分修正换成扣分和 ÷2；三种基础行动换成五种新行动。

“最后一个 ACTIVE 玩家”与“最后一个未爆牌玩家”必须区分。复仇版仍有已 Stay 的其他人时，可以把行动和扣分给予他们；只有最后一个未爆牌者才必须把行动或修正留给自己。[S07]

### 6.2 普通数字和重复判定

一般数字重复会立刻爆牌。这里的“收到”包括从牌堆抽牌、被偷牌或交换牌带入牌列，不能仅在 `draw()` 判重。出版方在 BGG 明确补充了此裁定。[S09]

例外：收到 Unlucky 7 先执行清牌；拥有 Lucky 13 时允许它与一张普通 13 共存。其他数字不因偷牌或交换免于判重。

### 6.3 The Zero 特殊 0

持有 The Zero 时，如果本轮没有达成 Flip 7，本轮得分为 0；不是只令数字牌合计为 0 后再正常扣修正。该玩家在自己的正常回合必须 Hit，不能主动 Stay。[S07]

它仍是一张值为 0 的数字牌，计入 Flip 7。达成 Flip 7 后解除清零限制，正常合计所有当前数字、÷2、扣分并加 15；不是只获得 15 分。

强制 Stay 仍有效：Just One More 可以让持有 Zero 的玩家再拿一张后结束自己的正常轮转，即使其没有 7 张数字。已经 Stay 的玩家收到 Zero 不恢复 ACTIVE。Zero 被偷走、交换走或丢弃后，其持续效果终止；原持有者若仍 ACTIVE，可以在后续正常回合选择 Stay。[S07]

### 6.4 Unlucky 7 不幸 7

收到它时立即丢弃自己此前的所有数字牌和修正牌，只保留这张 Unlucky 7，计 7 分。若原来已有普通 7，先清掉原牌，**不会因为这次收到特殊 7 爆牌**。以后又收到普通 7 才会爆牌。[S07][S08]

强制 Flip Four 中收到它：立刻清掉此前牌列，然后继续完成本组尚未抽的张数。不能等四张都翻完再清牌。

特殊牌可被偷或交换。进入新持有者时重新触发其清牌效果。原持有者失去它不找回此前被清掉的牌。待处理的行动队列不是玩家已经持有的数字／修正牌，因此不因这项清牌自动取消；这一点作为实现推导标注于第 10 节。

### 6.5 Lucky 13 幸运 13

Lucky 13 本身值 13 分，是一张数字牌。持有它时可再持有一张普通 13；两张都计分，两张都计入 Flip 7 张数，所以 Flip 7 可以只有六种数字值但有七张合法数字牌。

第三张值 13 的牌导致爆牌。没有 Lucky 13 时第二张普通 13 就爆牌。先有普通 13、后来收到 Lucky 13，依其例外规则可以共存。

Lucky 13 离开原持有者后例外立即失效；一副牌下原持有者至多剩一张普通 13，因此不产生“突然剩下两个普通 13”的情况。多副牌的额外例外和叠加规则不在官方单副牌完整裁定范围内。

### 6.6 行动目标和执行者

普通场景抽到行动牌时立即处理。抽到者可以将行动给予自己或其他未爆牌者，受领人完成该行动；不能仅因效果对自己不利而弃掉它。有可用牌就必须使用；无合法牌可操作时才弃掉。[S07][S08]

应把“选择谁执行 Steal”等行动和“选被偷的牌”分为两个决策：抽到者决定行动的受领人，该受领人再完成偷牌。官网 FAQ 的示例允许 C 把 Steal 给 A，迫使 A 偷 B 的同数牌并爆牌。[S08]

Swap 和 Discard 的具体选牌权在通用“给其他玩家行动”条款下存在措辞歧义。本文为实现采用如下明确规则：Swap／Discard 由最初抽到该牌者直接选卡，Steal 可以给受领人，由受领人选所偷卡；详见第 10 节，代码须保留策略配置，不假称全部获得官方裁定。

行动牌为一次性使用，完成后弃掉。合法牌目标是未爆牌玩家牌列的当前正面数字牌或修正牌，不包括抽牌堆、弃牌堆、尚未发动的行动队列或当前行动牌本身。

### 6.7 Just One More 再来一张

选一位未爆牌玩家，强制接受下一张牌，然后强制 Stay。若翻到行动，先完整处理这个行动；若翻到修正，正常处理并选择合法接收者。翻出数字时依通常规则处理，可能爆牌或达成 Flip 7。

这不是 Freeze，也不是“必须拿到一张数字牌”。新翻出的行动或修正就已经占用这一次抽牌。行动引出的额外抽牌是独立效果。

原本已 Stay 的目标依然可以被要求接受该一张牌，处理后继续 Stay。若嵌套行动让其爆牌，保留 BUSTED 状态，不能在效果末尾覆盖回 STAYED。

### 6.8 Swap 交换

选择两个不同玩家各一张正面牌交换；可以涉及自己，或者交换两名其他玩家的牌。数字和修正都能交换。交换同一个玩家内部两张牌不符合两名玩家交换的文字含义。

交换要作为一个事务同时移动两张牌，然后处理双方收到特殊数字的效果，再检查双方是否爆牌或达成 Flip 7。官方允许一次交换让两人同时爆牌：A 和 B 都有 10、11，交换 A 的 10 与 B 的 11，双方各自得到重复数字。[S08][S09]

交换加入第七张合法数字可以触发 Flip 7。但如果一个交换同时涉及 Unlucky 7 的清牌和另一方的 Flip 7，官方尚未明确顺序；第 10 节给出可配置处理约定。

### 6.9 Steal 偷牌

行动受领人选另一名未爆牌玩家的正面数字牌或修正牌，移入自己的牌列。数字判重和特殊数字效果照常执行；偷到第七张合法数字立即达成 Flip 7。[S09]

不能偷自己的牌，不能偷已爆牌者的牌，不能从弃牌堆“偷牌”。如果只有一张可偷牌且会导致重复，也必须偷并爆牌；不可用“避免爆牌”为理由跳过。无其他玩家的合法牌时丢弃行动。[S08]

### 6.10 Discard 弃置

选一名未爆牌玩家和其一张正面数字／修正牌，强制丢弃所选牌。可用来攻击别人，也可丢弃自己的负修正或 Zero。移除特殊牌后立即终止相应持续效果，不恢复已经 Stay 的玩家。

选择具体哪一张牌的权利在牌文中归“you”，本文按 6.6 的实现约定归原抽到者。无牌可选时直接弃掉行动。[S07]

### 6.11 Flip Four 强制翻四张

选任意未爆牌玩家，强制逐张翻最多四张。数字、行动、修正都算一张；触发行动牌本身不算这四张内。不能中途主动 Stay。

1. 普通和特殊数字立刻进入牌列并处理：Unlucky 7 先清牌；Lucky 13 当即允许第二张 13；Zero 的计分限制存在，但不额外增加本批张数。
2. 爆牌或达成 Flip 7 时立刻停止，不补齐四张。
3. 本组新翻出的所有行动和修正暂存，直到成功翻完四张后才依翻出顺序处理。与基础版的立即持有 Second Chance 不同，复仇版没有同等保命例外。
4. 在翻牌阶段爆牌，取消本组暂存效果；不能用暂存的 Discard／Swap／Steal 先救自己。
5. 成功翻完四张后，按翻出顺序进入效果处理阶段。

**官网 FAQ 的重要例外：** 已成功翻完四张后，如果处理暂存 Just One More 等动作时再次爆牌，仍继续处理原 Flip Four 批次剩下的行动；不能简单写成“执行者一爆牌就清空所有效果”。达成 Flip 7 则仍立即结束全桌本轮。[S08]

对已 Stay 玩家使用 Flip Four：其接受强制抽牌和后续行动，存活后仍 Stay，不再次进入正常回合。[S08]

### 6.12 扣分修正和计分

−2、−4、−6、−8、−10 和 ÷2 可给予任意未爆牌者，包括已 Stay 者。只有一个未爆牌者时，该玩家必须自收。修正牌不能造成数字重复或增加 Flip 7 张数；可被偷、交换或丢弃。[S07]

标准模式未爆牌者的计分：

```text
if owns ZERO and did_not_achieve_Flip7:
    round_score = 0
else:
    number_sum = sum(number_value of all current Number cards)
    divided = floor(number_sum / 2) if owns DIVIDE else number_sum
    after_penalties = max(0, divided - sum(SUBTRACT magnitudes))
    round_score = after_penalties + (15 if Flip7 winner else 0)
```

BUSTED 玩家为 0 分。扣分只影响本轮分数，不直接扣以前各轮累计分；Brutal 奖励转为攻击时另见第 7 节。

顺序是先数字和、再 ÷2 向下取整、再扣分修正、再把结果最低截断到 0、最后加 Flip 7 的 15 分。规则书示例：48 → ÷2 得 24 → −4 得 20 → Flip 7 加 15 得 35。

若数字分 9、÷2、−6，标准分 `max(0,4−6)=0`。若有效 Flip 7 数字合计 21、÷2、−10，分数 `max(0,10−10)+15=15`，不能先加 15 再 ÷2。

## 7 官方可选规则

### 7.1 复仇版 Brutal Mode

沿用复仇版，其官方增补只有三条：[S07，第 7 页]

1. 本轮分数可以小于 0，取消标准计分的最低 0 截断。
2. Modifier 可以给予任何玩家，包括已经爆牌者。普通行动和数字牌仍按原有合法目标规则。
3. 达成 Flip 7 时，由达成者选择：自己的本轮加 15，或令另一名玩家减 15；两者只能选一个。

未爆牌、无 Zero 清零限制时，先设 `number_points = floor(number_sum/2)`（有 ÷2）或 `number_points = number_sum`（没有 ÷2），再算 `round_score = number_points−penalties`。保留奖励时再加 15；选择攻击时自己没有 +15。

程序需要在本轮正式提交分数之前暂停，收集 `KEEP_BONUS` 或 `ATTACK_BONUS(target)` 决策。攻击目标不能是自己。官方写“another player”，没有排除已爆牌者，按所有其他玩家为目标实现。

**尚未完整裁定的 Brutal 情况：** 爆牌前的负修正是否在爆牌后仍保留扣分、Zero 与负分／攻击如何优先，以及攻击是直接作用累计分还是本轮结算项。本文默认把爆牌旧牌移到失效本轮区域，只计爆牌后新收到的负修正；爆牌后收到 ÷2 时只对已清零的数字分 0 做除二，不折半之后的负修正，最终为 `0−post_bust_penalties`。未爆牌者持 Zero 且未 Flip 7 时，牌列计分固定 0；攻击作为本轮独立 −15 项且不受 ÷2 或 Zero 影响。这是实现约定，不是官网已逐一裁定；第 10 节给出替代配置。

### 7.2 一人或两人挑战

现行两套 PDF 的附注是：“一人或两人？达到 200 分要用多少轮？”可以沿用基本流程记录达成目标的轮数。没有完整的官方合作、机器人或两人特殊攻击规则。[S03][S07]

Dized 的较旧条目写“能否在少于五轮达到 200”，应视为旧版挑战目标，严格 `under 5 rounds` 表示最多 4 轮，不等同于现行规则固定要求五轮。[S05]

若程序支持挑战模式，默认 `mode=challenge`、`target_score=200`、`round_limit=null`；另外可选 `legacy_round_limit=4`。单人时所有必做行动按合法目标规则自用，无卡可偷／交换时弃掉。

### 7.3 超过 18 人和多副牌

两份规则书都建议超过 18 人用第二副同版本牌。不能把第二副牌理解为“基础版加复仇版”，应先采用两个相同牌组。[S03][S07]

多副牌会出现重复 0、多个 ×2／÷2、多个 Lucky 13 等单副牌不存在的边界。官网建议没有完整解释这些叠加规则，程序若开放必须使用显式 `multi_deck_profile`，并把约定写进存档和对局说明；默认完整支持单副牌即可。

## 8 系列版本和扩展覆盖

本节按截至采集日期能核验的系列版本登记。正式主题换装版、带新机制的重新实现、民间扩展须分别标记，不能仅凭商品写“新版本”就混牌。

| 项目 | 与基础版关系 | 规则覆盖 |
| --- | --- | --- |
| Flip 7 原版与 2nd Edition | 同一基础游戏及新版印刷 | 按现行 Ruleset 3.1 完整覆盖 |
| Flip 7 With A Vengeance | 独立续作，BGG 463441 | 标准模式和 Brutal Mode 完整整理，歧义见第 10 节 |
| Flip 7 Grinch | 基础条目收录的主题版本／别名 | 94 张；已展示的数字与三种行动对应基础版 |
| Flip 7 The Nightmare Before Christmas | 基础条目收录的主题版本／别名 | 94 张；Zero 有交换效果，见 8.3 |
| Flip 7 National Parks | BGG 标记为重新实现，ID 476921 | 94 张；官网 Zero 牌面新增动物加分，见 8.2 |
| Flip 7 Liquid Death | BGG 标记为重新实现，ID 475144 | 94 张；Kill a Card、特殊数字 1 和修正计数牌，见 8.1 |
| Flip 7 Hello Kitty and Friends | 官方 Sanrio 联名完整游戏 | 94 张；Gift Three 替代 Flip Three，见 8.4 |
| Flip 7 Deluxe | 豪华配件版 | 高品质箔面牌、铅笔、计分板；渠道说明沿用经典规则 |
| Flip 7 Voll Fies | KOSMOS 德文复仇版 | 108 张；地区年龄标为 10+，不作为新的扩展叠加 |
| Flip 7 Event Deck FAN EXPANSION | BGG 文件区的民间事件牌扩展 | 非官方，不并入本文默认牌组 |
| Flip 7 Ultimate／混合基础和复仇牌组 | 网络玩家变体 | 未找到统一官方规则，不宣称官方支持 |

基础版旧印刷中的 Flip Three 有过官方修订：新版要求逐张翻牌，爆牌或 Flip 7 提前停止，未成功完成的批次不再执行其中暂存 Freeze／Flip Three。按本文 5.5 编码，不采用旧印刷或网页中“爆牌后还把那些暂存动作给别人”的过时说明。[S03][S05][S17]

### 8.1 Liquid Death 联名版

BGG ID 475144，2026 年，设计者 Eric Olsen，出版方 The Op Games；BGG 分类 Card Game、Number、Party Game，机制与基础版相同，Type 暂为 Uncategorized。BGG 展示 3–99 人、20 分钟、8+、Weight 约 1.00；官网为 3+、8+、20+ 分钟和 94 张牌。99 人不能视为官方单副牌支持上限。[S20]

**准确牌文来自官网高清配件照片，不能仅按宣传句子猜功能。** 官网称“两种新动作”，但配件图显示其中一张实际有数字 1 和按修正数量计分的文字。[S21]

| 已确认牌 | 官网牌面规则 | 对代码的影响 |
| --- | --- | --- |
| Kill a Card | 本轮任何时候可以使用它来弃掉一张牌 | 需要持有牌和额外响应决策，不是普通即时 Discard |
| Murder the Modifiers，数字 1 | 每收集一张 Modifier 加 1，包含这张本身 | 需要独立卡牌类型，不能实现成清空所有修正 |
| 特殊数字 1，Can Rules All | 再翻一张；若爆牌，扣除你的分数；若没爆，只有你计分 | 引入额外强制抽牌和全桌计分例外 |
| Freeze | 给予任意 ACTIVE 玩家，使其结束本轮 | 对应基础冻结 |
| Flip Three | 给予任意 ACTIVE 玩家，使其立即再翻三张 | 核心对应基础三抽，具体细节需联名规则书 |

照片中没有普通 0 或 Second Chance 的完整牌组清单，不能仅凭 94 总数反推出每种卡数量。存在网页把 Murder the Modifiers 解释成“清掉全部修正”，与官网可读牌文冲突，本文不采用这一解释。

**代码支持边界：** 已收集核心与新增牌面，但尚缺联名完整规则书来裁定 Kill a Card 可否救刚翻出的重复牌、能否取消已发动 Freeze、目标区域、持牌上限，以及两种数字 1 的类别和具体计分顺序。该配置应标 `PARTIAL_RULESET`，而不是直接套用基础版生成“完整忠实 Liquid Death 游戏”。所有已发现差异都登记在这里，新增牌不得默认混进基础牌组。

### 8.2 National Parks 国家公园版

BGG ID 476921，2026 年，设计者 Eric Olsen，出版方 The Op Games。BGG 人数 3–18、20 分钟、8+；Category 为 Card Game、Number，Mechanism 与基础相同，Family 为 Country: USA、Theme: US National Parks；Type 暂为 Uncategorized。BGG Weight 显示 0.00 是没有足够投票的字段，应存 `null`，不是零复杂度。[S22]

官网确认 94 张，数字牌改为国家公园／纪念地。已读取的清晰牌面有普通 1 至 12、基础 Flip 3、Freeze、六张动物修正牌：American Bumblebee +2、Little Brown Bat +4、Gila Monster +6、Gray Wolf +8、Mule Deer +10、Cedar Waxwing ×2。[S23]

**Zero 有新效果：每个 Modifier 上的动物加 1 分。** 官网页面配件图中该 0 仍以数字牌展示，文字为“+1 point per animal on modifier cards”。×2 图案有两只 Cedar Waxwing，其余已展示加分修正各一只动物。因此程序需 `animal_count`，不能直接令每张修正都恒定加 1；也不能按动物名称数量判数字重复。

BGG 描述还称此版加入 Kill a Card、带能力的 Modifier 和特殊 1；这与官网当前图片展示不完全一致。可能涉及早期宣传或原型资料，尚不能据此认定零售牌组同时包含 Liquid Death 的三项变化。保留为版本冲突，不能静默合并。

**代码支持边界：** 核心可按基础逻辑建立，Zero 加动物分可实现为附加计分规则；它是否算入×2的数字计分、是否只数自己的修正、所有行动确切数量仍缺完整官方文字。默认约定为只数自己的当前修正、动物加分在×2后加，×2上的两只鸟算2，并明确标为 `PARTIAL_RULESET`。Zero、+2、×2 在此约定下额外动物分为3，而非2。

### 8.3 The Nightmare Before Christmas 圣诞惊魂夜版

官网确认 94 张，3+、8+、约20分钟，数字用礼物／角色图案表示，仍按数字值判重。六种修正为 +2、+4、+6、+8、+10、×2；行动图中显示 Second Chance、Flip 3、Freeze。其主要新增牌是鬼犬 **Zero**：[S24][S25]

牌文为“你可以将 Zero 与任意其他正面牌交换”。它不是复仇版让整轮清零的 The Zero。官网没有在这张图片中明确限定自己的牌还是全桌牌，也没有给使用时点、可否多次发动或收到换来数字如何爆牌的完整说明。

**代码支持边界：** 基础框架及 Zero 交换牌文已采集；若生成原型，可明示采用“收到 Zero 时一次可选交换、范围为未爆牌玩家正面数字／修正、交换后照常检查数字重复和七张”的实现约定。不能将该约定包装成经过出版社裁定的完整官方玩法。

### 8.4 Hello Kitty and Friends

官网确认 94 张；数字改为 Sanrio 朋友形象，重复同一朋友对应重复其数字值。照片展示普通0–12和 +2、+4、+6、+8、+10、×2、Freeze、Second Chance。[S26]

**Gift Three 替代 Flip Three。** 官网牌面为：收到这张牌的玩家，将接下来的三张牌分配给其想给的任何人。它不是强制一个玩家自己拿三张，代码需要逐张指定接收者的决策 `SELECT_GIFT_RECIPIENT`。

**代码支持边界：** 已取得准确牌文，但尚缺 Gift Three 的完整规则书：能否给已 Stay 者、应在见到下一张牌前还是后选目标、某接收者达成 Flip 7 或爆牌是否继续剩余赠牌，以及赠牌中的嵌套行动顺序。原型默认只给 ACTIVE 玩家、抽出后再选择接收者、Flip 7 全局终止、某一接收者爆牌不影响另两次赠牌，并标 `PARTIAL_RULESET`。动作数量不能仅凭总数猜定。

### 8.5 Grinch 豪华版和语言包装版

Grinch 官网照片显示普通0–12及 Freeze、Second Chance、Flip Three，没有看见特殊0或1的功能变化。可作基础玩法主题配置；完整忠实程度仍取决于该版规则书与基础3.1裁定兼容，不凭“主题版”三个字直接推定所有规则永远不变。[S27]

Deluxe 的 Asmodee 渠道产品码 `USAPA172-915`、UPC `700304160577`，说明它与经典 Flip 7 一样，增加箔面牌、铅笔和计分板；没有应并入引擎的新行动。渠道发售日期曾写 Q3 2026，而其他报道有6月／10月等差异，本文只确认它是正式豪华版，不认定唯一全球上市日。[S28]

Voll Fies 是 KOSMOS 的德文复仇版，官网给108张、3–18人、10+、20分钟；地区年龄与美国8+不同。法文 Catch Up Games、德文 KOSMOS、中文等本地化、tuck box／Peggable／Hangsell陈列包装，以及展会整副促销版不应作为额外叠加规则包。[S29]

### 8.6 规则采集完成度

| 可选择规则配置 | 牌组数量与规则状态 | 能否仅凭本文忠实生成 |
| --- | --- | --- |
| BASE_3_1 | 94张，官方书和FAQ已采集 | 可以；第10节的低频歧义使用明示默认 |
| VENGEANCE_1 | 108张，官方书和FAQ已采集 | 可以；行动选择权等使用明示默认 |
| VENGEANCE_BRUTAL_1 | 同一108张，官方三条增补已采集 | 可以生成，但需明确Brutal边界配置 |
| GRINCH／DELUXE | 已确认基础框架与产品关系 | 可用基础配置；不新增未经证实效果 |
| LIQUID_DEATH | 94张，总数与新牌文已确认，完整分配表／细则缺失 | 部分；不可声称官方完整支持 |
| NATIONAL_PARKS | 94张，动物修正与Zero新牌文已确认 | 部分；需要确认版本冲突与计分顺序 |
| NIGHTMARE | 94张，Zero可交换已确认 | 部分；交换窗口和区域未完整裁定 |
| HELLO_KITTY | 94张，GiftThree已确认 | 部分；赠牌细则与完整牌表缺失 |

“全部”以公开可核验材料为边界：已检索到的正式系列版本和差异均登记，没有将缺失的联名规则细节补成虚构事实。基础版与复仇版的主规格足够开始编码；四个差异联名版保留具体缺口。

## 9 不依赖 UI 的实现规格

### 9.1 游戏状态

```text
GameState:
  ruleset: BASE_3_1 | VENGEANCE_1 | VENGEANCE_BRUTAL_1
  rules_options: all explicitly chosen compatibility settings
  players[]:
    id, seat, total_score, status, stay_reason
    number_cards[], modifier_cards[], second_chance_card?
    dead_round_cards[], post_bust_modifiers[]
  draw_pile[], discard_pile[]
  current_round: integer
  dealer_seat, normal_cursor, initial_deal_progress
  effect_queue[]
  active_draw_batch?:
    owner, total_required, drawn_count, deferred_cards[], batch_phase
  flip7_player?: player_id
  pending_decision?: DecisionRequest
  phase: SETUP | INITIAL_DEAL | PLAYER_DECISION | EFFECTS
       | ROUND_SCORING | GAME_OVER | RULES_EXCEPTION
  rng_state_or_seed, event_log[]
```

应把状态和事件分开：累计分数只由一次 `ROUND_SCORED` 事件提交；拿牌、移动、爆牌、停牌等都记录独立事件，便于重放。

### 9.2 输入决策

| 输入 | 谁决定 | 何时出现 |
| --- | --- | --- |
| HIT／STAY | 当前 ACTIVE 玩家 | 正常决策回合；Zero 可能只允许 HIT |
| SELECT_ACTION_RECIPIENT | 抽到行动者 | 正常行动或成功批次的延后行动 |
| SELECT_MODIFIER_RECIPIENT | 抽到修正者 | 复仇版修正处理 |
| SELECT_SECOND_CHANCE_RECIPIENT | 按所选兼容配置 | 基础版分配保命牌 |
| SELECT_STEAL_CARD | Steal 的受领人 | 存在可偷牌时 |
| SELECT_SWAP_CARDS | 按行动选牌权配置 | Swap 处理 |
| SELECT_DISCARD_CARD | 按行动选牌权配置 | Discard 处理 |
| KEEP_BONUS／ATTACK_BONUS | 达成 Flip 7 者 | Brutal Mode 本轮结算前 |

输入必须带 `decision_id` 和 `actor_id`，校验合法选项。过期、错误玩家和不存在的 card_id 应返回错误，不改变对局状态。强制抽牌由引擎推进，不向人类请求 Hit／Stay。

### 9.3 通用数字接收函数

```text
receive_number(player, card, defer_terminal_check=false):
  if card.kind == UNLUCKY_SEVEN:
    discard all previous number_cards and modifier_cards
    add card as sole current number
  else:
    add card
    if not defer_terminal_check and current received number violates duplicate limit:
      if BASE and owns SecondChance:
        discard incoming duplicate and SecondChance
      else:
        bust(player)
        return
  if not defer_terminal_check and player is not BUSTED
     and valid_number_card_count(player) == 7:
    end_round_immediately_with_Flip7(player)
```

复仇版 `duplicate_limit(13)` 在拥有 Lucky 13 时为 2，否则为 1；其他数字默认 1。基础版所有数字默认 1。不能用 `len(set(number_values)) == 7` 实现复仇版 Flip 7，否则会漏掉合法双 13。

Swap 使用事务级接收，传 `defer_terminal_check=true` 暂缓七张结束检查，先完成双向移动和双方特殊数字效果，再统一处理双方爆牌／Flip7结果，不能调用逐张抽牌函数提前结束另一方的交换；双方接收的冲突策略见第 10 节。

### 9.4 效果队列和强制抽牌

`Effect` 至少记录来源 card_id、抽到者、选择权归属、受领人、进入队列序号、所属抽牌批次，以及该批次是否已通过完整翻牌阶段。

基础版成功 Flip Three 批次应先全部选定 Freeze／Flip Three 目标再执行；新产生批次追加到全局队列。复仇版成功 Flip Four 批次按翻出顺序逐项处理，并保留“该批次已经成功”的标记，避免后续爆牌误删其剩余动作。

每次动作处理完再判断是否没有 ACTIVE，必须等待待做效果结束。唯一全局立即停止条件是有效 Flip 7。Flip Three／Four 的爆牌只停止该批翻牌并执行该批对应取消策略，不能粗暴停止整个游戏。

### 9.5 对外接口

```text
create_game(players, ruleset, options, seed) -> GameState
get_public_state(game) -> visible round cards, statuses, totals, deck count
get_legal_decision(game) -> DecisionRequest or none
apply_decision(game, decision_id, actor_id, choice) -> events
advance_until_decision(game) -> events and next DecisionRequest
score_round(game) -> per-player score breakdown
replay(events, ruleset, options) -> reconstructed GameState
```

这些接口可用于命令行、AI 对战、纯自动模拟或以后再接 UI。无需下载牌面图即可实现：卡牌文字名、数字值和效果类型足够。

### 9.6 状态不变量

- 每张 card_id 始终只在一个区域，包括抽牌批次与待处理行动，不得复制或消失。
- 所有区域合计始终等于所选牌组数量。
- 基础版未爆牌者每种数字最多一张，Second Chance 最多一张。
- 复仇版双 13 只在持有 Lucky 13 的允许范围内合法。
- 本轮只有一个 Flip 7 结束事件和一次计分事件。
- 基础版／复仇版标准本轮得分非负；Brutal 才允许负分。
- 中途洗牌不包含玩家当前牌列、失效本轮牌或待处理牌。
- 复仇版已 Stay 者受行动后不会仅因得到新牌变为 ACTIVE。
- 决策不提前揭示抽牌堆下一张；同一个 seed 加同一输入序列可重放。

## 10 未完全裁定的情况和实现默认值

以下项目会影响数字模拟的精确一致性，必须保存在对局配置中。它们不是要求用户现在逐项确认；实现时可采用所列默认，公开标识相应约定。

| 情况 | 已有证据与限制 | 本文默认 |
| --- | --- | --- |
| 基础版 Dealer 左侧先发 | 基础版只写按顺序，复仇版明写左侧 | `first_seat=dealer_left` |
| 基础版首次 Second Chance 是否可赠予 | 通用行动可给任何 ACTIVE；具体牌文写 Keep；社区引用开发者允许赠予 | `second_chance_initial_assignment=choose_active`；可切到 keep_self |
| 基础版未发首牌前已经经 Flip Three 拿到牌 | 社区 FAQ 引用出版方允许选择 Hit／Stay | `base_initial_prior_cards=offer_choice`；牌文兼容可 always_deal |
| 基础版连锁行动的细粒度队列 | 规则书只写延后；社区补充裁定先分配再依顺序执行 | `base_effect_queue=global_fifo` |
| 基础版 Freeze 和 Stay 的面朝方向 | 现行 PDF 写非活跃者翻面；旧 FAQ 说 Freeze 后正面 | 逻辑以 status 区分，牌保留本轮区域；公开状态可显示已知牌值 |
| 基础版使用保命牌是否可拒绝 | 规则用直接“discard”描述，没有完整拒用裁定 | 自动使用；可把拒用列为民间选项 |
| 复仇版空牌列能否主动 Stay | 未发现与基础版一样的明确至少一张要求 | 默认允许 Stay 得 0；不从基础版偷偷继承限制 |
| 复仇版 Swap／Discard 的选牌权 | 通用受领人条款与具体“you decide”有歧义，BGG 有未解讨论 | 原抽到者直接选两张交换牌／弃置牌；Steal 受领人选偷牌 |
| Steal 的合法牌区域 | 官网写 table face up；开发者示例均为玩家牌列 | 只允许他人未爆牌牌列的数字和修正，不允许弃牌／队列 |
| Unlucky 7 清牌是否清未分配修正 | 牌文写“in front of you”；强制四抽新修正延后处理 | 清当前已生效数字／修正，不清本批 deferred queue |
| Swap 同时触发两方特殊数字 | 官方确认双爆牌，未穷尽清牌与 Flip 7 同时出现 | 先完成双向移动，再依受影响者顺时针处理入牌特殊效果，最后统一检查爆牌和 Flip 7 |
| 成功 Flip Four 后爆牌仍有暂存修正 | 官方 FAQ 明确剩余 Actions 要执行，Modifiers 未逐项详述 | 保留原批行动；修正依当前规则重新求合法目标，记录此推导 |
| 复仇版平局 | 基础版明确全体加赛；复仇 PDF 没有单列 | 沿用全体累计加赛，直到 ≥200 的唯一最高分 |
| Brutal 爆牌旧负修正 | 标准爆牌是 0，Brutal 可给已爆牌者修正；没有完整保留顺序裁定 | 旧牌失效，只计爆牌后新负修正，可替换为所有负修正保留 |
| Brutal Zero 与扣分／攻击 | 官网未给组合算例 | 未爆牌且Zero未Flip7时牌列分固定0，独立攻击−15仍生效；爆牌后旧Zero失效，按爆牌后新修正计分 |
| Brutal 爆牌后收到 ÷2 | 官方放宽所有Modifier目标但没有此算例 | 数字部分0÷2仍为0，再扣爆牌后新负修正，不折半惩罚 |
| Brutal −15 攻击的入账位置 | 官网写 subtract 15 from another player | 作为本轮独立结算项，既不除二也不受 Zero 清零；允许累计负分 |
| 多副牌的多个倍率、Lucky 13 | 官方建议第二副牌，未给完整叠加例外 | 默认禁用叠加玩法；开放时须指定 MULTIPLY／DIVIDE 合并策略和特殊13判重策略 |
| 抽牌堆与弃牌堆同时为空 | 普通单副少人数极少遇到，官方未给无可抽牌解决步骤 | 进入 RULES_EXCEPTION 并保留状态；不擅自洗当前桌面或判输 |

基础版当前规则书与旧 Dized 的挑战目标不同：本文使用现行“记录多少轮达到 200”；旧五轮挑战另开选项。现成程序或网页出现冲突时，先核对其规则版本，不能以“计分器算成这样”为规则来源。

## 11 可复现验收案例

下面是未来实现应通过的行为案例。本次仅核对文档规则、牌表数量和计分算例，尚未制作或运行游戏引擎。

### 11.1 基础版

| 编号 | 前置状态与输入 | 期望 |
| --- | --- | --- |
| B01 | 有数字 4、8、9；Hit 得 8；无保命 | 爆牌，本轮 0 分，累计旧分不变 |
| B02 | B01 但持 Second Chance | 新 8 与保命牌立即弃掉，原 4、8、9 保留，仍 ACTIVE；不补抽 |
| B03 | 只有 +4；选择 Stay | 合法，本轮 4 分 |
| B04 | 只有 ×2；选择 Stay | 合法，本轮 0 分 |
| B05 | 数字 0、1、2、3、4、5、6 | 7 张不同数字，总和 21，加 15 得 36，立即结束全桌 |
| B06 | 数字总和 36、×2、+10 | 82 分；不是 92 分 |
| B07 | 数字总和 36、×2、+10，并达成 Flip 7 | 97 分；+15 不翻倍 |
| B08 | A 抽 Freeze，B 尚未拿第一张牌 | 可以冻 B，B 本轮 0，后续跳过 B |
| B09 | A ACTIVE，其他全部 Stay；A 抽 Freeze | 必须给自己，结束本轮 |
| B10 | Flip Three 翻出保命、重复数字、+4 | 保命立即可用救重复，三张都计抽牌张数，完成后保留 +4 |
| B11 | Flip Three 翻 Freeze 后翻重复数字而爆牌 | 停止，不翻第三张；暂存 Freeze 不发动 |
| B12 | 有 6 张不同数字，Flip Three 第一张补齐第 7 张 | 立即 Flip 7，不再翻余两张 |
| B13 | Flip Three 成功，暂存 Freeze、Flip Three 都分配给 B | 先 Freeze，后面的 Flip Three 取消，不重新分配 |
| B14 | A 抽 Flip Three 给 C，全部链结束 | 下一正常决策是 A 后面的有效座位，非 C 后面的座位 |
| B15 | 中途抽牌堆空，爆牌者面前还有牌 | 仅洗弃牌，不回收爆牌者当前轮牌 |
| B16 | 结算 A=210、B=220 | B 胜出；不是先达到 200 的 A |
| B17 | A=220、B=220、C=180 | 全体加赛，C 也能在加赛后成为最高分胜者 |
| B18 | 抽到第二张保命且所有合法玩家均已有一张 | 丢弃新保命，不叠加 |

### 11.2 复仇版

| 编号 | 前置状态与输入 | 期望 |
| --- | --- | --- |
| V01 | 数字和 48、÷2、−4、有效 Flip 7 | 35 分 |
| V02 | 数字和 9、÷2、−6，无 Flip 7 | 标准 0 分；Brutal −2 分 |
| V03 | 已 Stay 的 B 被给 −10 | B 的本轮计分受影响，仍 Stay |
| V04 | 已 Stay 的 B 被给 Flip Four，成功未爆 | B 接受四抽和行动，结束后仍 Stay |
| V05 | A、B 都有 10、11，交换 A 的 10 与 B 的 11 | 两人同时爆牌 |
| V06 | 持普通 13，得到 Lucky 13 | 不爆，双13合计26，两张均计Flip7 |
| V07 | 已有 Lucky13、普通13，又收到普通13 | 爆牌 |
| V08 | 已有普通7、其他数字、修正；收到 Unlucky7 | 先清全部旧数字／修正，只留特殊7，不爆 |
| V09 | V08 之后又收到普通7 | 爆牌 |
| V10 | 有 Zero 且没有Flip7，正常轮到自己 | 只允许 Hit，不允许主动Stay |
| V11 | 有 Zero、共6张数字，JustOneMore补齐第7张 | 有效Flip7，正常计分再加15，非仅15 |
| V12 | 有 Zero，被JustOneMore给到不补齐7的普通牌 | 强制Stay，本轮0；不无限强抽 |
| V13 | A 持6张合法数字，Steal偷到第7张不重复数字 | 立即Flip7，不要求从牌堆亲自翻出 |
| V14 | C 抽 Steal 给 A；B唯一可偷牌与A重复 | A必须偷并爆牌，不能弃掉Steal逃避 |
| V15 | FlipFour 第1张Discard、第2张重复数字 | 爆牌，Discard取消，不能先移走重复牌救命 |
| V16 | FlipFour 第1张Unlucky7，后3张普通数字 | 即时清旧牌，继续剩3抽 |
| V17 | FlipFour 四张成功，随后JustOneMore令执行者爆牌 | 本批剩余Actions仍继续处理，按官方FAQ |
| V18 | A唯一ACTIVE，B和C已Stay；A抽负修正 | 仍可给B或C，不强制自收 |
| V19 | A唯一未爆牌者，抽FlipFour | 必须作用于A；无保命牌例外 |
| V20 | Brutal：Flip7选择攻击B | A不加15，B独立−15；只能选择一种奖励 |
| V21 | Brutal：B已爆牌，再给B一个−4 | 可以分配；默认约定B本轮新惩罚−4 |
| V22 | 标准：B已爆牌，再试图给其−4 | 非法目标，必须重新选择合法目标 |
| V23 | Steal偷走B的Zero，B原为ACTIVE | B后续可以Stay；Zero持续效果转移给接收者 |
| V24 | 已Stay的B收到Zero | 不恢复ACTIVE，计分受Zero限制 |

## 12 来源目录

以下 URL 为采集时定位到的公开来源。官网 PDF 与 FAQ 是游戏编码的主依据；BGG 元数据读取受到站点访问限制，因此动态数值使用搜索索引公开快照。来源编号供正文追溯。

- **S01** BGG 基础游戏和分类：[Flip 7](https://boardgamegeek.com/boardgame/420087/flip-7)。
- **S02** BGG 复仇版身份、分类及作者：[Flip 7 With A Vengeance](https://boardgamegeek.com/boardgame/463441/flip-7-with-a-vengeance)。
- **S03** 官网现行基础规则书，Ruleset 3.1：[25 FLIP 7 TB RULES C Rev 9 2 25 ND](https://cdn.shopify.com/s/files/1/0611/3958/3198/files/25_FLIP_7_TB_RULES_C_Rev_9_2_25_ND.pdf?v=1756935535)。
- **S04** 出版方基础 FAQ：[Flip 7 FAQs](https://theop.games/pages/flip-7-faqs)。
- **S05** 出版方维护的 Dized 规则入口和 FAQ：[规则索引](https://rules.dized.com/game/dPDRM857TU-BFRF7LzGE0g/flip-7)、[FAQ](https://rules.dized.com/game/dPDRM857TU-BFRF7LzGE0g/faq)。
- **S06** 社区整理并链接出版方裁定的 FAQ，版本 1.4：[PDF](https://goblins.net/files/images/flip_7_faq_version_1.4.pdf)、[BGG 文件登记](https://boardgamegeek.com/filepage/292492/flip-7-faq-edge-cases)。
- **S07** 官网复仇版规则书，Ruleset 1：[26 FLIP 7 VENGEANCE RULES C](https://cdn.shopify.com/s/files/1/0611/3958/3198/files/26_FLIP_7_VENGEANCE_RULES_C.pdf?v=1770853609)。
- **S08** 出版方复仇版 FAQ：[Flip 7 With a Vengeance FAQs](https://theop.games/pages/flip-7-wav-faqs)。
- **S09** BGG 出版方开发者 Alyssa S 的答复，2026 年 2 月 19 日；确认收到重复牌爆牌及偷第七张可达成 Flip 7：[Conceptual Rules Questions](https://boardgamegeek.com/thread/3662346/conceptual-rules-questions)。
- **S10** 官网系列规则与 FAQ 下载入口：[Flip 7 系列页面](https://theop.games/pages/flip-7)。
- **S11** 官网基础版配件和时长年龄：[Flip 7 2nd Edition](https://theop.games/products/flip-7)。
- **S12** BGG 基础统计快照对应页面：[Flip 7 Stats](https://boardgamegeek.com/boardgame/420087/flip-7/stats)。
- **S13** BGG 复仇评分统计快照对应页面：[Vengeance Ratings](https://boardgamegeek.com/boardgame/463441/flip-7-with-a-vengeance/ratings)。
- **S14** 复仇规则书文本交叉核对：[RulesPal](https://www.rulespal.com/flip-7-with-a-vengeance/rulebook)。
- **S15** 引用出版方答复的保命牌讨论：[Rulesplainer Flip 7](https://hackingboardgames.com/rulesplainer-flip-7/)、[Two questions about the new Flip Three rule](https://boardgamegeek.com/thread/3477222/two-questions-about-the-new-flip-three-rule)。
- **S16** 连锁动作顺序补充案例：[Action card stacks](https://boardgamegeek.com/thread/3688197/action-card-stacks)、[Rare situation receiving more than one Flip Three or Freeze](https://boardgamegeek.com/thread/3494523/rare-situation-receiving-more-than-one-flip-three)。
- **S17** 引用出版方新版 Flip Three 文字的历史规则讨论：[Bust or no bust on flip 3](https://boardgamegeek.com/thread/3380455/bust-or-no-bust-on-flip-3)。
- **S18** 对 Swap 选牌权的未解讨论，作为歧义记录，非正式裁定：[Who chooses the cards swapped with a Swap Card](https://boardgamegeek.com/thread/3709603/who-chooses-the-cards-swapped-with-a-swap-card)。
- **S19** 中文名称参考：[7连翻中文销售资料](https://tao.hooos.com/search?w=bulygames)、[七翻天 Flip 7](https://www.eslite.com/product/10042149452683078873004)。
- **S20** Liquid Death 官方商品与 BGG 元数据：[官方页面](https://theop.games/products/flip-7-liquid-death)、[BGG 475144](https://boardgamegeek.com/boardgame/475144/flip-7-liquid-death)。
- **S21** Liquid Death 官网高清牌面：[全类型展示及两种数字1](https://theop.games/cdn/shop/files/F7LiquidDeath_Showcase_PTGHQ_7_LegalSq.jpg?v=1782410077)、[Kill a Card牌文](https://theop.games/cdn/shop/files/F7LiquidDeath_Showcase_LM_2_LegalSq.jpg?v=1782410077)。
- **S22** National Parks 元数据与版本差异描述：[BGG 476921](https://boardgamegeek.com/boardgame/476921/flip-7-national-parks)。
- **S23** National Parks 官方配件：[商品页面](https://theop.games/products/flip-7-national-parks)、[数字与Zero动物计分](https://cdn.shopify.com/s/files/1/0611/3958/3198/files/api.Flip7_NatlParks_Showcase_5_LegalSq.jpg?v=1782160207)、[六张动物修正](https://theop.games/cdn/shop/files/Flip7_NatlParks_Showcase_34_LegalSq.jpg?v=1782143680)。
- **S24** Nightmare 官方商品：[Flip 7 Disney Tim Burton The Nightmare Before Christmas](https://theop.games/products/flip-7-disney-tim-burtons-the-nightmare-before-christmas)。
- **S25** Nightmare 官方规则说明图：[Zero与行动](https://theop.games/cdn/shop/files/F7NBX_HTP-03.jpg?v=1790701776)、[六张修正](https://theop.games/cdn/shop/files/F7NBX_HTP-04.jpg?v=1790701776)。
- **S26** Hello Kitty 官方商品和GiftThree牌文：[商品](https://theop.games/products/flip-7-hello-kitty-and-friends)、[完整类型牌面](https://theop.games/cdn/shop/files/2026_F7HKF_CardsAll_Retailer.jpg?v=1787152982)。
- **S27** Grinch 官方商品和配件：[商品](https://theop.games/products/flip-7-grinch-edition)、[三种行动](https://theop.games/cdn/shop/files/Flip7Grinch_Showcase_ActionCards_SqLegal_1.jpg?v=1762209314)、[普通0至12](https://theop.games/cdn/shop/files/Flip7Grinch_Showcase_NumberCards_SqLegal_1.jpg?v=1762209314)。
- **S28** Deluxe 官方渠道商品：[Asmodee Canada USAPA172-915](https://shop.asmodee.ca/en/usapa172-915)。
- **S29** KOSMOS 地区版本：[Voll Fies商品](https://www.kosmos.de/products/flip-7-voll-fies)、[官方德文规则书](https://www.kosmos.de/cdn/shop/files/4002051687595_Flip7_Voll_20fies_Manual_web.pdf?v=17891228077105077972)；系列官方目录：[The Op Playing Cards](https://theop.games/collections/playing-cards)。

## 13 本次验证结果

已逐页读取官网当前基础版和复仇版规则书，读取两套官网 FAQ，核对复仇配件图中普通 7／13 与特殊数字牌数量，并按牌表重新计算 94／108 总数。关键边界用 Dized 和具名出版方 BGG 答复交叉核对。

文档的计分公式和对应算例已作独立算术核对；未运行实际游戏程序。BGG 自由标签、少数行动选择权、多副牌和 Brutal 极端组合尚未获得完整官方裁定，已在相关段落和第 10 节明示。以后生成基础版与复仇版代码时，选择所需规则配置即可将这些不确定性固定为可重放的游戏行为。

四个带规则差异的联名版已核对官网高清牌文，包括 Liquid Death 的两种数字1、可持有弃牌行动，National Parks 的动物计分0，Nightmare 的Zero交换及Hello Kitty的GiftThree。其完整牌张数分配与少数时序尚缺公开规则书，完成度为部分采集，不能称整个系列已完全具备忠实数字实现规格。
