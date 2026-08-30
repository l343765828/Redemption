AUTOMATED RUN（本段为 workflow 非交互执行的覆盖约定，优先于下文提示词中与之冲突的交互指令）：

0. **角色 Skill 边界**：本轮施工 Codex Producer 必须遵循 Controller 注入的
   `CODEX PRODUCER-ONLY SKILL CONTRACT`。Superpowers/Ponytail 只用于 Producer；
   不得要求后续 Opus/Fable 读取、使用或认可这些 Skill。

1. **没有人能回复你。** 本次经 `codex exec` 非交互执行，你的任何提问都不会得到答复。
   下文【开场先做这三件事，然后向我汇报，等我确认再开始改代码】以及一切
   "等我确认 / 请回复 / 等待裁决" 的关卡，一律改为：
   把核验结果与你的判断写进 IMPLEMENTATION_HANDOFF.md，然后**自行继续施工**。

2. **材料不一致时不要停工，按下列既定裁决执行**（这些是已生效的用户裁决，
   下文提示词或其引用文档若与之冲突，以本段为准）：
   - DEC-020 已包含 §14（D12 配置统一）、§15（D13 单期部署）、§16（D14 换期边界）、
     §17（D15–D17 UAT 约定）。主指令前言若仍写"DEC-020 尚无对应条款"，属过时表述，
     以 DEC-020 现行条款为准。
   - 涉及"其余硬编码地址"的数量表述（如 DEC-020 D12-c 写"9 处"）不作为范围依据；
     **范围以主指令 §2.5 的明确文件清单为准**，一律只登记、不修改。
   - `MSG-CONTRACT-v1` 虽标 DRAFT，**已由用户明确指定为 WP-6 生产端的实施基线**
     （AGENTS.md §8/§15.1 第 1 级：用户当前明确决策）。按其内容实现，
     不必等待其状态变更为已批准。
   以上三项无需再确认。你另行发现的、本段未覆盖的实质冲突：写进 handoff 的
   Notes-For-Verifier 并按你判断的最合理解释继续，**同时明确标注你所采取的假设**。

   - **F-201 采用已批准方案 B**：生产准入允许 `00`、`01`、`11`，继续拒绝 `10`；
     正式切换状态为 `11`，新记录写入 `amount_encoding_version=2`，已有记录只能通过
     显式迁移处理。该用户当前决策高于原施工提示词中的文件白名单和“状态 11 未授权”结论。

## AUTHORITATIVE PVAM V2 SCHEME B IMPLEMENTATION CONTRACT

本段是 Cycle 2 后续施工/返工的当前权威输入。完整设计位于主仓库
`docs/superpowers/specs/2026-08-29-pvam-v2-loop-skill-isolation-design.md`；若 Candidate
工作树没有该文件，以本段为准，不得因此停工。

1. `PVAmountConfigProvider.admit_production_run_config` 接受 `00`/`01`/`11`，状态 `10`
   继续返回 `INVALID_STATE`；不得加入环境变量或测试旁路。
2. 复用 `Redishelper/PVAmountConfigBootstrap.py`。`publish_manual_bootstrap` 新增显式
   `enable_v2: bool = False`：默认仍发布 `01`，`enable_v2=True` 发布 `11`；CLI 使用
   `--enable-v2`。两条路径共用现有 Lua CAS、单调版本、immutable snapshot 和
   read-after-write verify。
3. 新增聚焦模块 `Redishelper/PVAmountMigration.py`：必须显式 period 与精确记录标识，
   默认 dry-run，apply 显式选择；UserStats 金额字段排除 bool、要求 Python int/signed
   int64，全部合法才标记版本 2；Elite legacy 非零 `estimated_bonus` 返回
   `RECALC_REQUIRED`，不得自行换算；重复执行必须幂等。
4. 保留 `require_v2_amount_record` fail-closed。不得在 Consumer、Placement 或业务请求
   中隐式补版本。只有失败测试证明必要时才修改三条 service。
5. 按 Controller 注入的 Producer Skill 合同执行 RED→GREEN；handoff 记录真实命令输出。
6. 最大生产文件许可集合为：
   - `Common/AmountModelAdapter.py`
   - `Redishelper/PVAmountConfigProvider.py`
   - `Redishelper/PVAmountConfigBootstrap.py`
   - `Redishelper/PVAmountMigration.py`
   - `User/UserStatsService.py`
   - `User/PlacementIncrementalService.py`
   - `User/EliteBonusService.py`
   - `MessageConsumer/PvEventConsumer.py`
   - 与 amount/config/migration/consumer/三链组合直接对应的测试

这是最大许可集合，不是必须全部修改的清单。不得修改 SQL、Doc4、Kubernetes 拓扑或生产配置。

3. **真正的停工条件只有一个**：不改动原 WORK 范围与上述方案 B 最大许可集合之外的文件就无法完成任务，
   或指令要求的操作在技术上不可能完成。此时才输出 PRODUCER_BLOCKED 并说明卡点。
   材料措辞不一致、编号对不上、状态标记未更新——**都不是停工条件**。

4. **不要执行任何 git 写操作**（`add` / `commit` / `push` / `checkout` / `reset` 一律不要）。
   你运行在独立的沙箱账户下，无权写主仓库的 git 元数据、也读不到 Administrator 的 SSH 私钥——
   尝试必然失败。**提交与推送由 workflow 在你之后以 runner 身份自动完成。**
   你的交付形态就是：**把改动留在候选工作树的工作区里，不提交**。
   （只读的 `git status` / `git diff` / `git log` 可以用，用于自查改动范围。）
   下文提示词中一切要求你建提交、推送、或声明"推送后 HEAD SHA"的内容，一律作废。
   ⚠ 也不要另建 clone / 副本仓库来绕过——那会产生 workflow 无法采纳的孤立提交。

5. 终态输出格式（门禁机械判定，格式错误=整轮失败）：你的**最后一条消息的最后一行**
   必须单独成行、只含状态词本身：`READY_FOR_UAT` 或 `PRODUCER_BLOCKED`。
   正文其他位置可以提及这两个词，但不得让它们单独成行。
   此处 `READY_FOR_UAT` 的含义是"**代码改完、本机可做的验证已通过**"，与推送无关。

6. 断点续工：若开场核验发现部分工作已完成（工作区已有相关改动、交付文件已存在），
   **不要推倒重做**——核对已完成部分与指令一致后从断点继续；发现不一致，修正并写进 handoff。

7. 交付摘要写入 Controller 通过环境变量提供的
   `$env:PRODUCER_OUTDIR\IMPLEMENTATION_HANDOFF.md`（该暂存目录已通过 --add-dir 放行，
   不得直接写入 `MAINREPO\.loop-output`）。其中的 SHA 相关字段填
   `Local-Commit-HEAD-SHA: N/A（按契约由 workflow 提交）`，不要伪造提交号。

以下是本次任务的提示词正文：
-----------------------------------------------------------
