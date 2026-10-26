# 术语包 v1 草案

编码统一 UTF-8；JSON 不允许注释。说明写在 `note` 字段，文件末尾保留换行。不需要安装依赖。

## 文件

- `pack.json`：包标识、版本、语言方向、文件清单、预期数量和匹配原则。
- 可选的 `domain_hint` 是供 Qwen-MT 使用的英文场景短句（不超过 80 词）；只写题材和语气，
  不要把待审的译名或推测事实写进去。LiveTranslate 使用固定热词，不接收此提示。
- `characters.json`：角色实体数组。
- `cast.json`：声优实体数组，`character_id` 引用角色 ID。
- `terms.json`：作品、组织、简称和普通概念。
- `nickname-candidates.json`：待核对爱称；不属于 `data_files`，不可直接用于翻译。
- `sources.json`：事实来源及用户指定偏好的依据；不是翻译提示正文。
- `README.md`：人工验收入口。

## 实体与翻译对

`id` 是稳定标识，中文译名调整时不要改变它。角色和声优使用不同命名空间。
`kind` 区分 character / voice_actor / organization / general_term 等类别。
`source` 是日语表达，`target` 是本包偏好的简体中文表达。
`aliases` 中每条都有自己的 source、target、kind 和 match；绝不默认替换成实体全名。
`evidence` 引用 sources.json 的 id，支持范围以该来源的 supports 为准：日文名单来源不等于全部中文译法均获官方认可。
`note` 供维护与消歧使用，不应整段拼进模型的待翻译原文。

别名类别包括 short_name（名字简称）、surname（姓氏）、nickname（爱称）、orthographic_variant（书写变体）。
target 不使用斜杠列出多个备选，以免一次输出多个名称；备选写在 note 或待审文件中。

## 匹配安全约定

- exact_name：确认是对应专名后使用固定译法，不是无限制字符串替换。
- context_required：必须有足够人物/作品上下文。启用包本身不算消歧证据；例如“愛”“彼方”“秀”“田中”不能直接指认人物。
- 优先较长且完整的匹配；同一片段不重复注入全名及其内含简称。
- 符号和空格只做清单允许的规范化。禁止自动把 ASR 同音字、拼音或模糊相似词变成人名。
- 匹配到谁与如何称呼分开：田中ちえ美 → 田中千惠美；ちぇみー → 切咪；田中 → 田中。
- 运行时敬称规则尚未实现。少量核对过的名字＋敬称可作为具体别名收录；其余规则和构造示例放在 honorific-policy.json，不启用。不要预先删除所有“さん/ちゃん”，也不要一律加“酱”。
- 不使用声优—角色关系改写讲话对象，不补充原文未说的作品、人名或事实。
- 冲突应跳过或提示，不按文件读取顺序静默覆盖。
- 实时 LiveTranslate 只能在会话开始时接收固定热词，因此仅使用 `exact_name` 且译法唯一的词条；
  `context_required` 不会提前注入。标准 ASR＋MT 链路仍按当前片段和最近上下文匹配。
- 本目录只存数据与原则；实时会话加载器读取用户明确选中的包并进行保守本地匹配，无热更新。runtime_enabled=false 的草案必须明确试用；不会默认启用。具体边界见 ../docs/TRANSLATION-GUIDANCE.md。

## 待审项

entity_id 指向已有实体，source 是候选表达，suggested_target 可为 null。
所有候选条目 status=needs_review、enabled=false；确认归属与中文译法后再手动移入对应实体的 aliases，补充依据，并删除候选条目。

已查到人物归属和中文社区用法的映射可先收入 aliases，但 target_status=proposed_for_user_review 表示中文输出仍待用户验收，不是官方定译；整个示例包默认关闭，只有明确选择草案试用才加载。translation_basis 区分社区对应、跨社区爱称对应、保留原文和名字＋敬称。evidence 记录日文归属与中文表达各自的依据，不把搜索到视频标题宣称为已核验视频字幕。
