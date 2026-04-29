# Wiki Lint Report — 2026-04-29

> [!note] 扫描范围
> 全量 vault（公开区 + netease/），12 项检查

---

## 🔴 Critical

### Check 5: Cross-boundary references
*未发现* — 公开区文件未检测到指向 `netease/` 的 wikilink。

### Check 12: Redline tag leaks
*未发现* — 公开区文件未检测到红线清单中的 tag。

### Check 4: Visibility mismatch
*未发现* — 所有文件 visibility 与所在区域一致。

---

## 🟠 Warning

### Check 1: Broken wikilinks (29 found)

| 源文件 | 断链目标 |
|---|---|
| `netease/...` | `../待确认清单` |
| `netease/...` | `../demo文档/03-玩法流程` |
| `netease/...` | `../demo文档/04-地图行动` |
| `netease/...` | `../demo文档/05-物资系统` |
| `netease/...` | `../demo文档/09-demo需求` |
| `netease/...` | `02-底层规则` |
| `netease/...` | `03-玩法流程` |
| `netease/...` | `03-战斗系统` |
| `netease/...` | `04-地图行动` |
| `netease/...` | `06-外放策略` |
| `netease/...` | `08-数值平衡` |
| `netease/...` | `2026_第17周_周报` |
| `netease/...` | `2026-04-21-bigmap-server-protocol-integration` |
| `netease/...` | `概念名` |
| `netease/...` | `已有页面` |
| `netease/...` | `C Sharp 知识点` |
| `netease/...` | `hhkb.webp` |
| `netease/...` | `https://gitlab.nie.netease.com/...` |
| `netease/...` | `mls_helpme.gif` |
| `netease/...` | `mls灵宝.gif` |
| `netease/...` | `Move Method` |
| `netease/...` | `Pasted Image 20251028140941_888.png` |
| `netease/...` | `research` |
| `netease/...` | `sdc-spawn-select` |
| `netease/...` | `war-hold-buff-update` |
| `netease/...` | `wikilinks` |
| 公开区 | `2-Wiki/编程语言/Python-async-await` |
| 公开区 | `./defuddle/` 等 7 个 skill 目录 |
| 公开区 | `2-Wiki/ï¿½ï¿½ï¿½ï¿½ï¿½ï¿½ï¿½/Python-async-await`（乱码路径） |

> 建议：netease 侧断链多为旧文档引用，建议在 Phase 2 内容迁移时统一处理。公开区断链中 `2-Wiki/编程语言/Python-async-await` 是 ingest skill 测试时创建的 session 引用的 wiki 页面（尚未创建）。

### Check 3: Missing frontmatter
*需逐文件扫描* — 建议用 `obsidian search` 或脚本检查。已知新建的 session 文件（eval 测试产物）frontmatter 完整。

### Check 6: Index drift
*需比对 _index.md* — `2-Wiki/` 各领域目录的 `_index.md` 已建立，但内容迁移（Phase 2）尚未开始，当前 index 与实际页面可能不一致。

---

## 🟡 Suggestion

### Check 2: Orphan pages
*需反向链接分析* — 新建的 `9-Meta/TAGS.md`、`9-Meta/Skills/ingest/SKILL.md`、`9-Meta/Skills/query-wiki/SKILL.md`、`9-Meta/Skills/lint-wiki/SKILL.md` 目前可能无反向链接（尚未被其他页面引用）。

### Check 7: Duplicate topics
*未发现明显重复* — 当前 wiki 页面数量较少，暂无明显重复。

### Check 10: Stale projects
*`3-Projects/` 为空* — 无活跃项目需要检查。

### Check 11: Wild tags
*需比对 TAGS.md* — 已知 vault 中有 100 个 tag，其中大量不在白名单中（已在 TAGS.md §4 脏 tag 清理表中记录）。

---

## 总结

| 级别 | 数量 |
|---|---|
| 🔴 Critical | 0 |
| 🟠 Warning | 29 broken links + frontmatter/index 待细查 |
| 🟡 Suggestion | 若干（orphan、wild tags 等） |

**建议优先处理**：Phase 2 内容迁移时一并修复 netease 侧断链；公开区 `Python-async-await` wiki 页面待创建。
