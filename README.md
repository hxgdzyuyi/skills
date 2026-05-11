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

## Skills

| Name | Description | Documentation |
|------|-------------|---------------|
| nova-github-repo-mentionable-users | 导出 Github 项目上贡献过代码的中国人（或者其他地区的人）。 | [SKILL.md](skills/nova-github-repo-mentionable-users/SKILL.md) |
| nova-dynasty-game | 穿越模拟文字游戏——穿越成为中国历史上的皇帝，在朝堂上颁布诏令、应对危机、推动改革，体验王朝兴衰。 | [SKILL.md](skills/nova-dynasty-game/SKILL.md) |
| nova-yong-ge-restaurant-consulting | 勇哥餐饮咨询顾问——扮演"勇哥"，为用户提供专业的餐饮创业与经营咨询。 | [SKILL.md](skills/nova-yong-ge-restaurant-consulting/SKILL.md) |
| network-resume | 当用户输入 /network-resume 时触发，输出一句固定话术用于在网络中断后继续之前的任务。 | [SKILL.md](skills/network-resume/SKILL.md) |
| refactor-hotspots | 分析 Git 仓库最近频繁被修改的"热点文件"并给出重构建议（DRY、SRP、耦合等视角）。手动调用触发（/refactor-hotspots） | [SKILL.md](skills/refactor-hotspots/SKILL.md) |
| render-plan | 润色和完善 docs/plans/ 下的计划文档，按标准层面结构整理内容。手动调用触发（/render-plan） | [SKILL.md](skills/render-plan/SKILL.md) |
| run-plan | 落地 docs/plans/ 下的计划文档到当前项目。传入计划文件路径作为参数即开始执行；不传参数则列出所有可用计划供用户选择，手动触发。 | [SKILL.md](skills/run-plan/SKILL.md) |

