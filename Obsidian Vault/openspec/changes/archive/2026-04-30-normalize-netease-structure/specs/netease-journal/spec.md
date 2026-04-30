## ADDED Requirements

### Requirement: 0-Daily directory structure

`Netease/0-Daily/` SHALL serve as the journal area for private work daily/weekly/monthly reports, organized by `YYYY/MM/` subdirectories.

#### Scenario: Directory exists with index

- **WHEN** the `Netease/` directory is inspected
- **THEN** `0-Daily/` SHALL exist as a top-level subdirectory
- **AND** `0-Daily/_index.md` SHALL exist with `area: journal` and `visibility: private` in frontmatter

#### Scenario: Year-month subdirectory organization

- **WHEN** a daily report for 2026-04-30 is created
- **THEN** it SHALL be placed at `Netease/0-Daily/2026/04/2026-04-30_日报.md`

### Requirement: Daily report file naming

Daily report files SHALL follow the naming convention `YYYY-MM-DD_日报.md`.

#### Scenario: Correct file name format

- **WHEN** a daily report for March 26, 2026 is saved
- **THEN** the file name SHALL be `2026-03-26_日报.md`

### Requirement: Daily report frontmatter

All files under `0-Daily/` SHALL have frontmatter with `area: journal` and `visibility: private`.

#### Scenario: Frontmatter fields present

- **WHEN** any `.md` file under `0-Daily/` is read
- **THEN** its frontmatter SHALL contain `area: journal`
- **AND** its frontmatter SHALL contain `visibility: private`
- **AND** its frontmatter SHALL contain a `date` field

### Requirement: 4-Reference secondary index

`Netease/4-Reference/_index.md` SHALL serve as a secondary index, linking to the INDEX.md files of each mirrored source subdirectory rather than enumerating individual documents.

#### Scenario: Index lists mirror sources

- **WHEN** `4-Reference/_index.md` is read
- **THEN** it SHALL list links to `arcolab_docs/INDEX.md`, `popo_card_docs/INDEX.md`, and `popo_robot_docs/INDEX.md`
- **AND** it SHALL NOT enumerate individual documents from those sources

### Requirement: Path references use correct case

All internal path references within `Netease/` SHALL use `Netease/` (capital N) rather than `netease/` (lowercase n).

#### Scenario: AGENTS.md uses correct case

- **WHEN** `Netease/AGENTS.md` is read
- **THEN** all path references to the private area SHALL use `Netease/` prefix
- **AND** no occurrence of `netease/` (lowercase) SHALL remain

#### Scenario: Base file uses correct folder path

- **WHEN** `工作报告总览.base` is read
- **THEN** `file.inFolder` SHALL reference `Netease/0-Daily` (not `netease/daily`)
