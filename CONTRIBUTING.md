# Contributing to bpr-plugin

欢迎 PR。这个项目本质是**一份精心调过的 prompt + 流水线**——所以贡献规则比代码项目宽松一些,但有几条硬规矩。

## Quick start

```bash
git clone git@github.com:kenzhangjie/bpr-plugin.git
cd bpr-plugin

# 链接到本地 Claude 测试
ln -s "$(pwd)/skills/ddr" ~/.claude/skills/ddr

# 在 Claude Code 里跑:
/ddr <某个 podcast url>
# 跑通且效果对 → 提 PR
```

## What kind of changes are welcome

✅ **欢迎**:
- 修翻译三步法的失败案例(在 `references/lessons-learned.md` 加一条 L4/L5...)
- 改进 `references/checklist.md` 的自检条目
- 新增触发词 / 修饰词
- 优化 `templates/base.html` 的视觉
- 加新输入源支持(小宇宙 / Apple Podcasts / Substack 等)
- 修 typo
- 翻译错误纠正

⚠️ **慎重**:
- 改 `references/translation-prompt.md` 的核心三步法 — 这是项目灵魂,必须有充分论证
- 改 `templates/base.html` 的 CSS — 视觉一致性是产品价值,不要无谓改动
- 改触发命令 `/ddr` — 会破坏老用户工作流

❌ **不接受**:
- 改 `references/lessons-learned.md` 的历史条目(只能新增,不能删/改)
- 往 `glossary.txt` 第 3 列加短错法(CJK <3 字 / 拉丁 <4 字)—— 无边界子串替换会误伤常用词
  (`小红→肖弘` 曾把「小红书」改成「肖弘书」);跑 `clean_en.py --check-glossary` 自查
- 引入网络请求外的外部依赖(本插件应保持自包含)

## PR checklist

提 PR 前自查:

- [ ] 所有改动都跟你 PR 描述里的"动机"直接相关(不要顺手"优化"无关代码)
- [ ] 新增功能更新了 `CHANGELOG.md` 的 `[Unreleased]` 段
- [ ] 改了 `SKILL.md` 的工作流 → 同步更新 `references/checklist.md`
- [ ] 改了 prompt → 自己跑一遍真实 podcast/essay 验证,不是只看 diff
- [ ] **如果改动会影响输出格式**:在 PR 描述里附改前 / 改后的 HTML 对比截图
- [ ] 没引入硬编码路径(grep `/Users/`、`/home/`、`~/` 应该是干净的)
- [ ] 没引入个人化引用(grep 应该看不到具体人名 / 项目名)

## Lessons-learned 维护规则

`references/lessons-learned.md` 是项目的"集体记忆"。维护规则:

- **只增不删**:历史教训不删,即使你认为不再相关
- **新条目用 L# 编号**(L1, L2, L3...)递增
- **每条必含**:症状 / 根因 / 修法 / 关联 commit hash
- **不要总结归纳**:每个 lesson 是具体一次失败,不是抽象规则

例:

```markdown
## L9. hero 抬头被截

**症状**:某次输出 hero 段右侧"嘉宾抬头"显示 `Anton...`,被裁了。

**根因**:`.kicker .meta` 的 max-width 设了 600px,Mac 的 PingFang SC 在某些 weight 下字宽超了。

**修法**:`base.html` 里 max-width 改成 `none`,在 mobile 媒体查询里再单独压缩。

**Commit**:`abc123` (2026-05-12)
```

## Local validation

在提 PR 前,本地跑这两条 sanity check:

```bash
# 1. JSON 合法
python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); json.load(open('.claude-plugin/marketplace.json')); print('JSON OK')"

# 2. SKILL.md frontmatter 合法
python3 -c "
import re, yaml
content = open('skills/ddr/SKILL.md').read()
m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
assert m, 'no frontmatter'
fm = yaml.safe_load(m.group(1))
assert 'name' in fm and 'description' in fm
print('SKILL.md frontmatter OK')
"
```

CI 也会自动跑这些。

## Versioning

参 [CHANGELOG.md](./CHANGELOG.md)。语义化版本(semver):

- patch (`1.0.0` → `1.0.1`):改 prompt / 修 typo / fix bug
- minor (`1.0.0` → `1.1.0`):加新触发词 / 新 reference
- major (`1.0.0` → `2.0.0`):破坏性改动(改 `/ddr` 触发、删功能)

## Release flow(仅 maintainer)

```bash
./tools/release.sh 1.0.1 "patch: 修了 X"
```

详细步骤参 [tools/release.sh](./tools/release.sh)。

## Questions

- 用法问题 → 提 [Issue](https://github.com/kenzhangjie/bpr-plugin/issues)(贴 transcript / URL + 期望 vs 实际输出)
- 设计讨论 → [Discussions](https://github.com/kenzhangjie/bpr-plugin/discussions)(如果开了)
