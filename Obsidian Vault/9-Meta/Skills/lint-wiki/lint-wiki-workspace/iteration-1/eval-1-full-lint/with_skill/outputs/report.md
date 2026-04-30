# Wiki Lint Report �� 2026-04-29

> [!note] ɨ�跶Χ
> ȫ�� vault�������� + netease/����12 ����

---
## �9�2 Critical

### Check 5: Cross-boundary references
*δ����* �� �������ļ�δ��⵽ָ�� `netease/` �� wikilink��

### Check 12: Redline tag leaks
*δ����* �� �������ļ�δ��⵽�����嵥�е� tag��

### Check 4: Visibility mismatch
*δ����* �� �����ļ� visibility ����������һ�¡�

---

## �0�6 Warning

### Check 1: Broken wikilinks (29 found)

| Դ�ļ� | ����Ŀ�� |
|---|---|
| `netease/...` | `../��ȷ���嵥` |
| `netease/...` | `../demo�ĵ�/03-�淨����` |
| `netease/...` | `../demo�ĵ�/04-��ͼ�ж�` |
| `netease/...` | `../demo�ĵ�/05-����ϵͳ` |
| `netease/...` | `../demo�ĵ�/09-demo����` |
| `netease/...` | `02-�ײ����` |
| `netease/...` | `03-�淨����` |
| `netease/...` | `03-ս��ϵͳ` |
| `netease/...` | `04-��ͼ�ж�` |
| `netease/...` | `06-��Ų���` |
| `netease/...` | `08-��ֵƽ��` |
| `netease/...` | `2026_��17��_�ܱ�` |
| `netease/...` | `2026-04-21-bigmap-server-protocol-integration` |
| `netease/...` | `������` |
| `netease/...` | `����ҳ��` |
| `netease/...` | `C Sharp ֪ʶ��` |
| `netease/...` | `hhkb.webp` |
| `netease/...` | `https://gitlab.nie.netease.com/...` |
| `netease/...` | `mls_helpme.gif` |
| `netease/...` | `mls�鱦.gif` |
| `netease/...` | `Move Method` |
| `netease/...` | `Pasted Image 20251028140941_888.png` |
| `netease/...` | `research` |
| `netease/...` | `sdc-spawn-select` |
| `netease/...` | `war-hold-buff-update` |
| `netease/...` | `wikilinks` |
| ������ | `2-Wiki/�������/Python-async-await` |
| ������ | `./defuddle/` �� 7 �� skill Ŀ¼ |
| ������ | `2-Wiki/�0�7�0�7�0�5�0�7�0�7�0�5�0�7�0�7�0�5�0�7�0�7�0�5�0�7�0�7�0�5�0�7�0�7�0�5�0�7�0�7�0�5/Python-async-await`������·���� |

> ���飺netease �������Ϊ���ĵ����ã������� Phase 2 ����Ǩ��ʱͳһ����������������� `2-Wiki/�������/Python-async-await` �� ingest skill ����ʱ������ session ���õ� wiki ҳ�棨��δ��������

### Check 3: Missing frontmatter
*�����ļ�ɨ��* �� ������ `obsidian search` ��ű���顣��֪�½��� session �ļ���eval ���Բ��frontmatter ������

### Check 6: Index drift
*��ȶ� _index.md* �� `2-Wiki/` ������Ŀ¼�� `_index.md` �ѽ�����������Ǩ�ƣ�Phase 2����δ��ʼ����ǰ index ��ʵ��ҳ����ܲ�һ�¡�

---

## �0�7 Suggestion

### Check 2: Orphan pages
*�跴�����ӷ���* �� �½��� `9-Meta/TAGS.md`��`9-Meta/Skills/ingest/SKILL.md`��`9-Meta/Skills/query-wiki/SKILL.md`��`9-Meta/Skills/lint-wiki/SKILL.md` Ŀǰ�����޷������ӣ���δ������ҳ�����ã���

### Check 7: Duplicate topics
*δ���������ظ�* �� ��ǰ wiki ҳ���������٣����������ظ���

### Check 10: Stale projects
*`3-Projects/` Ϊ��* �� �޻�Ծ��Ŀ��Ҫ��顣

### Check 11: Wild tags
*��ȶ� TAGS.md* �� ��֪ vault ���� 100 �� tag�����д������ڰ������У����� TAGS.md ��4 �� tag ������м�¼����

---

## �ܽ�

| ���� | ���� |
|---|---|
| �9�2 Critical | 0 |
| �0�6 Warning | 29 broken links + frontmatter/index ��ϸ�� |
| �0�7 Suggestion | ��ɣ�orphan��wild tags �ȣ� |

**�������ȴ���**��Phase 2 ����Ǩ��ʱһ���޸� netease ������������� `Python-async-await` wiki ҳ���������
