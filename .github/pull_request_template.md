## 改了什么

<!-- 一句话描述。不要 paste git log,讲"为什么改"。 -->

## 关联 Issue

<!-- 可选。Closes #123 -->

## 自检 checklist

参 [CONTRIBUTING.md](../CONTRIBUTING.md):

- [ ] 所有改动都跟"为什么改"这一段直接相关(没有顺手优化无关代码)
- [ ] 更新了 `CHANGELOG.md` 的 `[Unreleased]` 段
- [ ] 改了 `SKILL.md` 的工作流 → 同步更新了 `references/checklist.md`
- [ ] 改了 prompt → 自己跑过真实 podcast/essay 验证,不是只看 diff
- [ ] 没引入硬编码路径(`grep -r '/Users/\|/home/' .` 是干净的)
- [ ] 没引入个人化引用(具体人名 / 项目名)

## 影响输出格式?

- [ ] 否(纯文档 / 内部重构)
- [ ] 是 — 附改前 / 改后对比(截图或 HTML diff)

<!-- 如果是 — 附图或描述差异 -->

## 这是哪种 semver 改动?

- [ ] patch(typo / bug fix / 不影响行为的改进)
- [ ] minor(加新功能,向后兼容)
- [ ] major(破坏性改动 — 改触发命令 / 删功能 / 改输出格式)
