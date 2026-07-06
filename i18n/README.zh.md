<p align="center">
  <img src="https://img.shields.io/badge/ClaudeKit-v2.0.0-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License">
</p>

<h1 align="center">ClaudeKit</h1>

<p align="center">
  <strong>一个生产级的多智能体编排系统，适用于 <a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a>。</strong><br>
  结构化规划。审查门控。安全执行。质量验证。支持任何语言。
</p>

<p align="center">
  <a href="#快速开始">快速开始</a> &middot;
  <a href="#工作原理">工作原理</a> &middot;
  <a href="#命令">命令</a> &middot;
  <a href="#智能体">智能体</a> &middot;
  <a href="#贡献">贡献</a>
</p>

---

### 选择语言 | Select Language

[English](../README.md) | [العربية](README.ar.md) | **中文** | [Espanol](README.es.md) | [Francais](README.fr.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

---

## 为什么选择 ClaudeKit？

Claude Code 本身功能强大。ClaudeKit 使其变得**结构化、安全且可审计**。

没有 ClaudeKit，AI 助手会直接进行更改——没有计划、没有审查、没有回滚。有了 ClaudeKit，每个更改都遵循流水线：规划、审查、安全执行、验证结果。

### 核心组件

| 组件 | 数量 | 描述 |
|------|------|------|
| 智能体 | 13 | 每个任务都有专门的智能体 |
| 命令 | 20+ | 开箱即用的命令 |
| 技能 | 55+ | 可复用的技能模块 |
| 模式 | 7 | 不同的行为模式 |
| 安全守卫 | 29 | 验证每个配置的守卫 |
| 语言模板 | 11 | 支持 Python、TypeScript、Java、Go 等 |
| MCP 服务器 | 5 | 模型上下文协议集成 |

---

## 快速开始

### 安装

```bash
git clone https://github.com/omarmokhtar/claudekit.git
./claudekit/install.sh /path/to/your-project --full
```

安装程序会自动检测项目语言，将 `.claude/` 目录复制到项目中，生成 `CLAUDE.md` 和 `CONSTITUTION.md`，并使用您的构建/测试/检查命令配置钩子。

### 安装选项

```bash
# 完整安装（智能体 + 命令 + 技能 + 钩子 + 操作）
./install.sh ./my-project --full

# 最小安装（智能体 + 命令 + 操作）
./install.sh ./my-project --minimal

# 预配置语言
./install.sh ./my-project --full --language typescript

# 覆盖现有安装
./install.sh ./my-project --full --force
```

### 使用

在 Claude Code 中打开项目并运行：

```
/plan 添加使用 JWT 令牌的用户认证
```

ClaudeKit 接管流程——规划器探索代码库，编写带有 ops.json 配置的计划，审查器验证计划，实现器通过自动备份执行，验证器检查结果。

---

## 命令

| 命令 | 描述 | 示例 |
|------|------|------|
| `/plan` | 创建带有 ops.json 的实施计划 | `/plan 为 API 添加速率限制` |
| `/review` | 验证计划（90/100 阈值） | `/review` |
| `/implement` | 执行已批准的计划 | `/implement` |
| `/verify` | 运行质量检查（80/100 阈值） | `/verify` |
| `/debug` | 诊断错误（只读） | `/debug 为什么登录返回 500？` |
| `/docs` | 生成文档 | `/docs 认证模块的 API 参考` |
| `/git` | Git 操作 | `/git commit "feat: 添加认证"` |
| `/coordinator` | 多智能体编排 | `/coordinator 迁移数据库架构` |
| `/explore` | 探索代码库架构 | `/explore 认证模块如何工作？` |
| `/security` | 安全分析 | `/security 扫描认证模块漏洞` |
| `/test` | 生成并运行测试 | `/test src/services/auth.ts --generate` |
| `/deploy` | 发布准备和部署 | `/deploy release` |

---

## 智能体

| 智能体 | 职责 | 模型 |
|--------|------|------|
| **协调器** | 分类任务、编排工作流、管理智能体交接 | Sonnet |
| **规划器** | 探索代码库，编写实施计划 + ops.json 配置 | Sonnet |
| **审查器** | 多维度计划验证——计划质量(40%)、架构(30%)、安全(30%) | Opus |
| **实现器** | 通过操作脚本执行已批准的计划，自动备份 | Sonnet |
| **验证器** | 质量验证——静态分析(30%)、测试(40%)、覆盖率(30%) | Haiku |
| **调试器** | 只读根因分析，使用4阶段系统化调试 | Opus |
| **文档器** | 创建和维护技术文档 | Haiku |
| **GitOps** | 分支、提交、PR 创建、发布管理 | Haiku |
| **探索器** | 快速代码库探索、模式发现、架构映射 | Sonnet |
| **测试器** | 专门的测试编写——单元、集成、E2E、覆盖率差距分析 | Sonnet |
| **安全扫描器** | OWASP Top 10 扫描、密钥检测、依赖 CVE 分析 | Opus |
| **DevOps** | CI/CD 流水线、容器化、部署、基础设施即代码 | Sonnet |
| **数据库架构师** | 模式设计、迁移、查询优化、数据建模 | Sonnet |

---

## 行为模式

| 模式 | 描述 |
|------|------|
| **默认** | 正常运行，完整的解释和输出格式 |
| **头脑风暴** | 自由创意生成，无实现约束 |
| **令牌高效** | 压缩输出，目标节省 40-70% 令牌 |

---

## 基于规范的工作流

1. 在 `specs/` 中编写规范
2. 运行 `/plan` 根据规范进行规划
3. 审查器根据规范进行验证
4. 验证器确保符合规范

---

## 贡献

欢迎贡献！详情请参阅[贡献指南](../CONTRIBUTING.md)。

---

## 许可证

MIT -- 详情请参阅 [LICENSE](../LICENSE)。
