---
area: meta
visibility: public
---
## Why

`Netease/` ˽������֮ǰ�� `restructure-vault-as-llm-wiki` change �н����˹Ǽܣ�`1-Sessions/`��`2-Wiki/`��`3-Projects/`��`4-Reference/`��������ʷ `daily/` Ŀ¼δ�鵵����Ŀ¼���� `netease` ��Ϊ `Netease` ���ڲ�����·������δͬ����������Ч������������ϣ������滯�����ʱ����

## What Changes

- ���� `0-Daily/` Ŀ¼�� `_index.md`������ AGENTS.md �滮�� journal area
- �� `daily/2026/` �������ձ�/�ܱ�/�±�Ǩ���� `0-Daily/2026/`������ԭ����Ŀ¼�ṹ
- �����޸�Ǩ�ƺ��ļ��� frontmatter��`area: unknown` �� `area: journal`
- ɾ�� `daily/` Ŀ¼�� `_fix_daily.py` �ű�
- ���� `4-Reference/_index.md`����"������Ŀ"��Ϊ����������ָ��������Ŀ¼�� INDEX.md
- ���� `daily/������������.base`��`file.inFolder` ·���� `netease/daily` ��Ϊ `Netease/0-Daily`
- ȫ���滻 `Netease/AGENTS.md` ������ `netease/` �� `Netease/`��Լ 36 ����

## Capabilities

### New Capabilities

- `netease-journal`: `0-Daily/` Ŀ¼��Ϊ˽���������ձ�/�ܱ�/�±��� journal area���� `YYYY/MM/` ��Ŀ¼��֯���ļ����� `YYYY-MM-DD_�ձ�.md`

### Modified Capabilities

���ޡ������β��޸����� spec �����󣬽����ṹ������·��ͬ����

## Impact

- ��Ӱ���ļ���`Netease/AGENTS.md`��·�����ø��£���`Netease/4-Reference/_index.md`�����ݸ��£���`Netease/daily/������������.base`��·�����£�
- ��Ӱ��Ŀ¼��`Netease/daily/`��ɾ������`Netease/0-Daily/`���½���
- Ǩ���ļ�����28 ����24 �ձ� + 3 �ܱ� + 1 �±�����frontmatter �����޸�
- �޹�����Ӱ�죬�� API ��������������
