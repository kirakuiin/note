---
area: meta
visibility: public
---
## Context

`Netease/` ˽������ `restructure-vault-as-llm-wiki` change �н���������ǰ׺�Ǽܣ�`1-Sessions/`��`2-Wiki/`��`3-Projects/`��`4-Reference/`������ `0-Daily/` δ��������ʷ�ձ����� `daily/` �¡�ͬʱĿ¼���� `netease` ��Ϊ `Netease` ��`AGENTS.md` ��Լ 36 ��·��������ΪСд��`4-Reference/_index.md` ���ݹ�ʱ��˵"������Ŀ"��ʵ���� 3 ������Դ��150+ ƪ�ĵ�����

�����Ǵ��ṹ���� + ·��ͬ�������漰���ݱ����

## Goals / Non-Goals

**Goals:**
- ���� `0-Daily/` Ŀ¼��ʹ˽�����Ǽ��� AGENTS.md �滮һ��
- �� `daily/` �������ձ�/�ܱ�/�±�Ǩ���� `0-Daily/`������ `YYYY/MM/` ��Ŀ¼�ṹ
- �޸�Ǩ���ļ��� frontmatter��`area: unknown` �� `area: journal`��
- ���� `4-Reference/_index.md` Ϊ��������
- ͬ������ `netease/` �� `Netease/` ·������
- ���� `.base` �ļ��� folder ����·��

**Non-Goals:**
- ���޸��ձ�/�ܱ�/�±�����������
- ��Ǩ�� `Assets/` Ŀ¼
- ���޸� `4-Reference/` ����Ŀ¼���������� snake_case��
- ���޸Ĺ������κ��ļ�
- ���޸� `.gitignore`

## Decisions

### 1. Ǩ�Ʒ�ʽ���ƶ��ļ����Ǹ���

**����**��ʹ���ļ��ƶ���rename/move���� `daily/2026/` �� `0-Daily/2026/`��

**����**�������ظ��ļ������� vault �� wikilink һ���ԡ�Obsidian ���Զ����� wikilink ���á�

**��ѡ����**�����ƺ�ɾ��ԭ�ļ���Ч����ͬ����һ����

### 2. `4-Reference/_index.md`��������������ȫ���б�

**����**��`_index.md` ֻ�г�������Ŀ¼���� INDEX.md �����ӣ���ö�پ����ĵ���

**����**���û���ȷҪ��"������ index ��������������"��ÿ����Ŀ¼�����Լ��� INDEX.md���� `arcolab_docs/INDEX.md` �г� 37 ƪ�ĵ������ظ��г������ά��������

### 3. ·���滻��Χ���� `Netease/` �ڲ�

**����**��`netease/` �� `Netease/` �滻���� `Netease/` Ŀ¼���ļ���

**����**���������ļ���Ӧ���� `Netease/` ·�������߹��򣩣���˹�������Ӧ������Ҫ�滻�����á�������ֹ����������ã����Ǻ���Υ�棬�赥��������

### 4. `.base` �ļ�·������

**����**��`������������.base` �� `file.inFolder("netease/daily")` ��Ϊ `file.inFolder("Netease/0-Daily")`��

**����**��Obsidian Bases �� folder ���˻��� vault ���·����Ŀ¼��������Ǩ�ƺ����ͬ�����£�������ͼΪ�ա�

### 5. `_fix_daily.py` ֱ��ɾ��

**����**��ɾ�� `daily/2026/03/_fix_daily.py`����Ǩ�ơ�

**����**���û�ȷ�ϸýű��Ѳ���Ҫ��

## Risks / Trade-offs

- **[�ͷ���] wikilink ����**���ձ��ļ�֮����� wikilink ���ã����±����ø��ձ������ƶ��ļ�ʱ Obsidian ���Զ����� wikilink��������֤���� Ǩ�ƺ����� `obsidian unresolved` ��顣
- **[�ͷ���] `.base` ��ͼ��ʱʧЧ**��`.base` �ļ�����ǰ�����ھ�·������ͼ����ʾ�ա��� ��Ǩ����ɺ��������� `.base` �ļ���
- **[�޷���] ����������**�������Ϲ�������Ӧ���� `Netease/`���������滻ǰȷ�ϡ��� �� grep ������ȷ���� `netease/` ���á�
