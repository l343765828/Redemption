# PVAM V2 安全切换与 Loop Skill 隔离设计

## 1. 状态与权威依据

- 日期：2026-08-29
- 适用任务：WORK-PVAM-02，Loop Cycle 2 后续恢复
- 当前阻断：F-201。生产准入只接受 `00`/`01`，但三条业务链会拒绝 `amount_encoding_version != 2` 的记录。
- 用户当前决策：采用方案 B，正式授权状态 `11`，新记录写入 `amount_encoding_version=2`，并提供已有记录的显式迁移能力。
- 用户当前角色约束：只有 Loop 中负责施工的 Codex Producer 使用 Superpowers 与 Ponytail；Claude Opus 和 Fable 审核时禁止使用二者。

本设计中的用户当前决策高于原 WORK-PVAM-02 文件白名单和历史“生产状态 11 未授权”约束。未被本设计明确覆盖的业务规则继续遵守项目 `AGENTS.md` 与有效正式决策。

## 2. 目标

1. 通过显式、可审计的配置发布动作启用 `read_v2=true, write_v2=true`，即状态 `11`。
2. 状态 `11` 下创建的 UserStats 与 EliteBonusStats 记录统一标记 `amount_encoding_version=2`。
3. 在切换到 `11` 前，对明确指定的已有记录提供 dry-run、校验、幂等迁移和迁移后验证。
4. 保留 v2 读取守卫的 fail-closed 行为，不在 Consumer 或业务阶段静默升级旧记录。
5. 用真实配置准入路径和三条业务链组合测试证明事件可到达 `DISPATCHED`。
6. 在隔离 UAT 中临时启用 `11`，无论验证成功或失败都恢复原配置并精确清理测试数据。
7. 在 Loop 中严格隔离 Producer 与 Reviewer 的 Skill 使用范围。

## 3. 非目标

- 不执行生产数据迁移、生产配置切换或生产部署。
- 不把状态 `11` 设为无条件默认值。
- 不把 legacy 浮点奖金直接乘以 100 后当作可信 cents。
- 不在业务请求处理中隐式修改 `amount_encoding_version`。
- 不放宽状态 `10`、配置 checksum、版本 CAS、运行期冻结或 v2 金额边界。
- 不要求 Claude Opus 或 Fable 使用、模拟或认可 Superpowers/Ponytail 的方法论结论。

## 4. 方案选择

采用“显式配置发布 + 切换前迁移 + fail-closed 读取”的完整方案 B。

不采用以下缩减方案：

- 仅允许 Provider 接受 `11`：当前 Bootstrap 仍只发布 `01`，真实 UAT 不会进入 v2。
- 仅在全新周期切换：无法满足“已有记录显式迁移”。
- 在 Placement/Consumer 中临时打版本补丁：会重新引入隐式升级并掩盖不完整迁移。

## 5. 配置准入与发布

### 5.1 Production admission

`Redishelper/PVAmountConfigProvider.py::admit_production_run_config` 调整为：

- `00`、`01`、`11` 可进入生产 run；
- `10` 继续以 `INVALID_STATE` 拒绝；
- 不增加环境变量、测试旁路或调用方布尔开关；
- `PVAmountRunSession.start` 仍只加载一次并冻结同一个配置。

状态 `11` 的授权证据来自经过现有 checksum、版本和 source 校验的 immutable snapshot，而不是调用方临时参数。

### 5.2 Manual Bootstrap

复用现有 `Redishelper/PVAmountConfigBootstrap.py`，不创建第二套配置发布器：

- 保持现有调用默认发布 `01`，维持向后兼容；
- CLI 只有显式指定 v2 激活参数时才发布 `11`；
- `01` 和 `11` 都继续使用现有 Lua CAS、单调 config version、immutable snapshot 和 read-after-write verify；
- 不允许发布 `10`；
- 输出只包含状态、版本和 checksum，不输出 Redis 地址或凭据。

生产 Bootstrap 不提供版本倒退或 pointer 回滚接口。隔离 UAT 的恢复由
Controller 专用 CAS 完成：只有 active pointer 仍精确等于本次 UAT 发布的
`11` pointer 时，才允许恢复启动前保存的 pointer；检测到任何第三方更新时
必须拒绝覆盖并报告漂移。该恢复能力不得暴露给 Candidate 或生产 CLI。

## 6. 显式迁移合同

新增一个聚焦的迁移模块 `Redishelper/PVAmountMigration.py`，不引入新框架或通用迁移平台。

### 6.1 输入与运行模式

- 必须显式传入 period 及精确记录标识；默认 dry-run。
- apply 模式必须由调用方显式选择。
- 迁移只处理 UserStats 和 EliteBonusStats 的已确认金额字段。
- 禁止 pattern delete、全库无界扫描和运行中自动发现后直接写入。

### 6.2 UserStats

- 对所有已有金额字段执行 `bool` 排除、Python `int` 和 signed int64 边界校验。
- 校验全部通过后才写入 `amount_encoding_version=2`。
- 已为 v2 且字段合法的记录视为幂等成功，不重复写入。
- 任一字段非法时，该记录不写入并返回明确失败证据。

### 6.3 EliteBonusStats

- 对整数业绩字段执行与 UserStats 相同的 signed int64 校验。
- legacy `estimated_bonus` 为 `None` 或数值零时，可迁移为空白 v2 载体：`estimated_bonus=None`、`estimated_bonus_cents=0`、版本 2。
- legacy `estimated_bonus` 非零时禁止自行换算，返回 `RECALC_REQUIRED`；必须从权威整数输入重新计算后再迁移。
- 已为 v2 的记录只做验证，不降级、不改写已确认 cents。

### 6.4 原子性与幂等

- 每条记录在写入前重新核对读取到的版本和值，避免基于过期快照覆盖并发更新。
- 单条失败不会把该条记录标记为 v2。
- 整批只有在所有目标记录验证成功后才允许进入配置切换步骤。
- 迁移报告记录目标、结果、失败码和迁移前后版本，不记录凭据。

## 7. 切换与恢复顺序

隔离 UAT 固定使用以下顺序：

1. 绑定并暂停受管 Consumer，确认没有继续处理消息。
2. 读取并保存当前 active config pointer、状态、版本和 checksum 的脱敏证据。
3. 对本次 UAT 精确记录执行迁移 dry-run；通过后执行 apply 并重新验证。
4. 通过 Manual Bootstrap 的 CAS 路径发布新的状态 `11` snapshot。
5. 启动绑定当前 period/Candidate 的 Consumer，执行消息与三链 UAT。
6. 在 `finally` 清理精确测试键、停止受管 Consumer，并由 Controller 使用
   “当前 pointer 必须等于本次 `11` pointer”的专用 CAS 恢复步骤 2 的原值。
7. 验证恢复后的状态、版本和 checksum 与步骤 2 完全一致。

如果迁移、配置发布、Consumer 启动或 UAT 任一步失败，后续业务步骤停止，但恢复与清理仍必须执行。生产环境的迁移和切换不在本设计授权范围内。
如果恢复时发现 pointer 漂移，Controller 不得覆盖外部更新，应保留脱敏证据并把
Loop 标记为环境阻断，等待人工确认。

## 8. 业务链处理

- `build_factory_amount_fields("11")` 继续作为新记录 v2 字段的唯一工厂来源。
- UserStats、Placement、Elite 三条业务链继续共享同一次事件冻结的 run config。
- `require_v2_amount_record` 保持严格；不根据异常文本、环境变量或 Consumer 状态绕过。
- 只在证据证明必要时修改 `User/UserStatsService.py`、`User/PlacementIncrementalService.py`、`User/EliteBonusService.py`；扩大白名单是许可，不是强制制造改动。
- F-202 的永久失败日志和 F-203 的组合回归与 F-201 同轮完成；F-204 在三链成功后用逐 stage 注入失败进行确认，再决定是否修改归因实现。

## 9. Loop Agent Skill 隔离

### 9.1 Codex Producer

仅 Loop 的施工/返工 Codex Producer 必须按顺序读取并使用：

1. Superpowers `using-superpowers`；
2. 返工轮使用 `receiving-code-review`，独立复核 Opus/Fable findings；
3. `systematic-debugging`，先确认根因；
4. `test-driven-development` 及 `writing-good-tests.md`，先得到预期失败再写生产代码；
5. Ponytail `full`，优先复用现有 Bootstrap、Provider、Adapter 和测试结构，禁止投机抽象；
6. 项目 `redemption-comment-style`，同步维护中文 region/Step 注释；
7. `verification-before-completion`，以本轮新鲜命令输出决定 `READY_FOR_UAT`。

Producer 不使用需要再次等待人工选择的 `brainstorming`、`writing-plans`、`executing-plans` 或多 Agent 类 Skill。当前设计与实施计划已经是它的批准输入，自动 Round 内不得重新发起设计问答。

Producer handoff 必须列出实际读取的 Skill 名称和路径、RED/GREEN 命令与结果、Ponytail 删除/避免的非必要设计；不能只写“已使用”。

### 9.2 Claude Opus 与 Fable

Claude Opus 和 Fable 必须：

- 禁止读取、加载、调用或声称使用 Superpowers/Ponytail；
- 不把 Producer 的 Skill 执行声明当作正确性证据；
- 只依据项目规则、Verifier checkpoint 协议、Candidate diff、测试原始输出、Controller 证据和真实 UAT 结果独立判定；
- 可以要求 Producer 补测试或简化实现，但审核自身不得套用上述 Producer-only Skill。

角色限制同时写入 Producer override 与 Verifier automated override。测试必须通过实际提示构建入口验证两类 prompt 的 Skill 允许/禁止集合，不能只 grep Markdown 文本。

## 10. 文件范围

### 10.1 Candidate 业务实现许可

- `Common/AmountModelAdapter.py`
- `Redishelper/PVAmountConfigProvider.py`
- `Redishelper/PVAmountConfigBootstrap.py`
- 新增 `Redishelper/PVAmountMigration.py`
- `User/UserStatsService.py`
- `User/PlacementIncrementalService.py`
- `User/EliteBonusService.py`
- `MessageConsumer/PvEventConsumer.py`
- 对应 amount/config/migration/consumer/三链组合测试

上述为最大许可集合；Producer 应按 Ponytail 原则只修改通过失败测试证明必要的文件。

### 10.2 Loop Controller 许可

- Producer/Verifier override 与 prompt 组装文件
- `.loop-engine/uat-action-policy.json`
- `.loop-engine/uat-action-proxy.ps1`
- 与配置切换、迁移、恢复和角色 Skill 隔离直接相关的 loop-engine 测试
- 从已存在分支恢复 `.agents/skills/redemption-comment-style/` 到 Controller 可读取位置

不得借此修改无关业务模块、SQL、Doc4、Kubernetes 部署拓扑或生产配置。

## 11. 测试策略

所有行为变更遵守 RED → GREEN → REFACTOR：

1. Provider：状态 `11` 经真实 config 对象可准入；`10` 仍失败。
2. Bootstrap：默认仍发布 `01`；显式 v2 参数发布 `11`；CAS/校验失败不切 pointer。
3. Migration：dry-run 无写入、apply 成功、重复执行幂等、非法 int64 拒绝、非零 legacy bonus 返回 `RECALC_REQUIRED`。
4. Three-chain：使用真实 `PVAmountRunSession.start` 和真实三 service 组合，brand-new user 达到 `DISPATCHED`，三组幂等键齐全。
5. Failure logging：永久失败产生脱敏 ERROR 日志；未分类异常保留 traceback。
6. Stage attribution：分别在三 stage 注入已知失败，断言 failed/completed/pending 与实际幂等状态一致。
7. Controller：未授权配置写入被拒绝；失败路径仍恢复 pointer、清理精确键并停止受管 Consumer。
8. Prompt isolation：运行真实 prompt 构建入口，证明 Producer 包含指定 Skill 合同，Opus/Fable 包含明确禁用合同且不继承 Producer-only 内容。
9. 回归：目标测试、全量 pytest、Loop controller 回归全部通过后才进入隔离 UAT。

## 12. 验收标准

- 状态 `11` 只能通过显式、可审计的 Bootstrap 动作发布。
- 新用户事件在真实 UAT 达到 `DISPATCHED`，三组 idempotency marker 完整，无 exception-topic 记录。
- 新 UserStats/EliteBonusStats 记录的 `amount_encoding_version` 为 2，金额满足 signed int64 约束。
- 存量迁移 dry-run/apply/幂等/拒绝路径均有可复现测试证据。
- UAT 前后 active config 完全恢复，Redis 无本次执行残留，受管 Consumer 已恢复停止状态。
- Candidate 变更不超出本设计许可范围。
- Codex Producer 实际使用指定 Superpowers 子集和 Ponytail；Opus/Fable 的 prompt 与输出均不使用或声称使用二者。
- F-202/F-203 关闭；F-204 得到确认或反证并以证据记录。
