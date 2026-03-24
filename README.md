## Skills

| Name | Description | Documentation |
|------|-------------|---------------|
| nova-github-repo-mentionable-users | 按地区筛选 GitHub 仓库的可提及用户（贡献者）。批量获取仓库贡献者并按国家/地区进行筛选识别，输出为 CSV 文件。 | [SKILL.md](skills/nova-github-repo-mentionable-users/SKILL.md) |

## Installation

Hugging Face skills are compatible with Claude Code.

### Claude Code

1. Register the repository as a plugin marketplace:

```
/plugin marketplace add hxgdzyuyi/skills
```

2. To install a skill, run:

```
/plugin install <skill-name>@hxgdzyuyi-skills
```

For example:

```
/plugin install nova-github-repo-mentionable-users@hxgdzyuyi-skills
```
