# FeeFlow（飞流）— 项目设计文档

> **版本**: 0.1.0  
> **最后更新**: 2026-05-15

---

## 一、概述

### 1.1 项目定位

FeeFlow（飞流）是一个**实体匹配与自动化工作流平台**，专注于解决多源异构数据间的实体信息关联问题。它能够将不同系统中表示同一主体的记录（客户单位、用户名称、联系方式、地址地区等）自动关联起来，并通过可扩展的适配器体系实现输出和自动化操作。

### 1.2 设计背景

在跨系统数据整合的常见场景中，同一实体在不同系统中的名称、编码、联系方式等信息往往存在差异。例如：

- A 系统录入了"××科技有限公司"，B 系统记录了"××科技(张经理)"
- 一条客户记录在 CRM 中叫"李明"，在售后系统中叫"李明（188****1234）"
- 一条地址在订单系统中是"成都市高新区天府大道"，在物流系统中是"成都高新天府大道"

传统方案完全依赖人工逐条比对和关联，效率低、易出错、难以扩展。

FeeFlow 的目标是提供一个通用框架，通过**可配置的匹配管道** + **多策略引擎** + **插件化适配器**，让跨系统实体关联过程完全自动化。

### 1.3 设计目标

| 目标 | 说明 |
|------|------|
| **通用化** | 匹配引擎与业务解耦，通过 YAML 配置适应任意领域的实体关联 |
| **可扩展** | 所有适配器（数据源、平台、输出、策略、规则）均可通过插件机制扩展 |
| **配置驱动** | 工作流行为完全由 YAML 定义，零代码定制领域逻辑 |
| **可观测** | 管道执行过程有日志、有摘要、有验证 |
| **可闭环** | 支持从数据读取 → 实体匹配 → 报表输出 → 平台操作的端到端自动化 |

---

## 二、系统架构

### 2.1 分层架构

```
┌──────────────────────────────────────────────────────────────┐
│                      CLI (feeflow)                           │
│             run / validate / plugins / init                  │
├──────────────────────────────────────────────────────────────┤
│                       PipelineRunner                         │
│             工作流编排引擎 — 9 阶段管道执行                     │
├───────────────────┬───────────────────┬──────────────────────┤
│    匹配引擎         │    数据源适配       │    平台/输出适配     │
│  matching/        │  sources/         │  platforms/         │
│                   │                   │  outputs/           │
│  Normalizer       │  FileSource       │  WeChatPlatform     │
│  Strategies×4     │  SQLSource        │  ExcelOutput        │
│  Engine           │  (Record→dict)    │  WebhookOutput      │
│  Registry         │                   │  PlatformAction     │
│  AliasStore       │                   │                     │
├───────────────────┴───────────────────┴──────────────────────┤
│                     PluginManager                            │
│              Entry Points + 目录扫描                          │
├──────────────────────────────────────────────────────────────┤
│                     YAML 配置层                               │
│             workflow.yaml + ${env:VAR} 变量替换               │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 核心模块职责

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `workflow/` | 工作流编排 | `PipelineRunner`, `WorkflowContext`, `load_workflow` |
| `matching/` | 实体匹配引擎 | `PipelineNormalizer`, `EntityMatchingEngine`, `EntityRegistry` |
| `sources/` | 数据源读取 | `DataSource(ABC)`, `FileSource`, `SQLDatabaseSource` |
| `platforms/` | 平台交互 | `PlatformAdapter(ABC)`, `WeChatPlatform` |
| `outputs/` | 输出生成 | `OutputAdapter(ABC)`, `ExcelOutputAdapter`, `WebhookOutputAdapter` |
| `plugins/` | 插件发现 | `PluginManager` |
| `cli/` | 命令行入口 | `cli` (Click group) |

### 2.3 插件体系

通过 Python `entry_points` 机制 + 目录扫描实现三方扩展：

| 入口点组 | 注册项 | 扩展点 |
|----------|--------|--------|
| `feeflow.sources` | `file`, `sql` | 新增数据源（如 `http`, `kafka`） |
| `feeflow.platforms` | `wechat` | 新增平台（如 `dingtalk`, `feishu`） |
| `feeflow.outputs` | `excel`, `webhook`, `platform_action` | 新增输出格式（如 `pdf`, `csv`） |
| `feeflow.strategies` | `exact`, `token`, `fuzzy`, `phonetic` | 新增匹配策略 |
| `feeflow.normalizer_rules` | `strip_prefix`, `strip_suffix` 等 6 规则 | 新增归一化规则 |

---

## 三、管道执行流程

### 3.1 PipelineRunner.run() 九阶段

```
feeflow run workflow.yaml
  │
  ├─ 1. 构建 PipelineNormalizer（从 YAML normalizer.rules）
  ├─ 2. 构建 MatchingConfig → EntityMatchingEngine
  ├─ 3. 创建 EntityRegistry(engine)
  ├─ 4. 创建 WorkflowContext（共享状态）
  │
  ├─ 5. Phase 1：加载规范数据源（register_only=True）
  │     → registry.get_or_create(name, attributes)
  │
  ├─ 6. 重建关键词索引（n-gram → entity_id）
  │
  ├─ 7. Phase 2：加载待匹配数据源（register_only=False）
  │     → registry.resolve_with_score(name)
  │     → 找到则 enrich + add_alias，未找到则 get_or_create
  │
  ├─ 8. Enrichment：加载外部映射文件
  │     → registry.resolve(name) → 追加属性
  │
  └─ 9. Outputs：执行每个输出适配器
        → adapter.write(data, schema, config)
        → 或 adapter.execute_action(action, context)
```

### 3.2 数据源 Phase 设计

- **Phase 1（规范源）**：高置信度的权威名称列表，用于构建实体索引
  - 如：主系统的客户名录、官方注册数据
  - 处理方式：注册实体但不进行匹配

- **Phase 2（匹配源）**：需要与规范源关联的待匹配数据
  - 如：第三方系统导出数据、文件名列表、聊天记录
  - 处理方式：先尝试解析（匹配已有实体），匹配失败则创建新实体

### 3.3 实体解析三层算法

```
EntityRegistry.resolve_with_score(name)
  │
  ├─ Layer 1: 别名索引 O(1)
  │     规范化名 → canonical_id 直接查找
  │     命中即返回 100.0
  │
  ├─ Layer 2: 关键词索引（n-gram 预过滤）
  │     中文字符 bigram 提取 → 候选实体打分
  │     Top 50 候选 → 精确变体名匹配
  │     命中即返回 100.0
  │
  └─ Layer 3: 相似度引擎
        Top 50 候选 → 逐条执行所有匹配策略
        保留最高分 → verify_match() 假阳性验证
        返回引擎评分
```

---

## 四、匹配引擎设计

### 4.1 规范化管线

`PipelineNormalizer` 由多个 `NormalizationRule` 顺序执行：

| 规则类 | 类型名 | 参数 | 行为 |
|--------|--------|------|------|
| `StripPrefixRule` | `strip_prefix` | `patterns: list[str]` | 移除匹配的前缀 |
| `StripSuffixRule` | `strip_suffix` | `words: list[str]` | 移除末尾匹配词（最长优先） |
| `StripRegexRule` | `strip_regex` | `patterns: list[str]` | 移除所有匹配文本 |
| `CollapseWhitespaceRule` | `collapse_whitespace` | — | 移除所有空白 |
| `LowerRule` | `lower` | — | 转小写 |
| `StripRegexMultipleRule` | `strip_regex_multi` | `patterns: list[str]` | 多次迭代移除直到稳定 |

规则通过 YAML 声明式组合：

```yaml
normalizer:
  rules:
    - type: strip_prefix
      patterns: ["^[A-Z]-+\\s*"]
    - type: strip_suffix
      words: ["有限公司", "分公司"]
    - type: collapse_whitespace
```

### 4.2 四层匹配策略

```
Order 1: ExactMatchStrategy (score=100/95)
  ├─ 主路径：规范化后全等匹配
  └─ 附加路径：extra_normalizers 处理（如跨字段匹配）
      score = exact_score - 5

Order 2: TokenMatchStrategy (score=80~95)
  ├─ 子串包含：短名(≥3字)在长名中 → containment_score=90
  └─ Token 重叠：中文 token 集合重叠率 ≥ min_ratio
      score = min_score + 10×ratio, capped at max_score

Order 3: FuzzyMatchStrategy (score=85~100)
  └─ rapidfuzz 加权评分
      token_sort_ratio × 0.6 + partial_ratio × 0.4

Order 4: PhoneticMatchStrategy (score=90~100)
  └─ pypinyin → pinyin 字符串 → rapidfuzz token_sort_ratio
```

引擎短路过 early exit：任一策略命中 100 分即返回。

### 4.3 通用词过滤

Token 匹配策略支持 `generic_token_predicate`，用于过滤领域通用词（如"公司"、"集团"、"有限"等常见后缀词）。只有非通用词 token 才参与匹配判定，防止纯通用词查询误匹配。

### 4.4 假阳性防御

通过 `EntityMatchingEngine.meaningful_match_fn` 可选回调：

```python
def meaningful_match(entity_name: str, query_name: str, score: float) -> bool:
    # 可在此实现领域特定的验证逻辑
    # 如：检查差异字符是否均为通用字
    # 如：LCS 比例检查
    # 如：共同前缀长度检查
    ...
```

默认无验证函数（接受所有匹配结果）。

---

## 五、数据源适配器

### 5.1 接口定义

```python
class DataSource(ABC):
    name: str
    def read(self, config: dict) -> list[Record]: ...
    def validate_config(self, config: dict) -> list[str]: ...
    def resolve_columns(self, row, column_mapping, row_index) -> Optional[Record]: ...
```

### 5.2 内置实现

| 适配器 | 格式 | 配置参数 |
|--------|------|----------|
| `FileSource` | `xlsx` | `path`, `sheet`, `column_mapping` |
| | `csv` | `path`, `encoding`, `column_mapping` |
| | `txt` | `path`, `txt_regex`, `name_keywords` |
| | `yaml` | `path`, `record_path`, `field_mapping`, `filters` |
| | `directory` | `path`, `file_patterns`, `recursive` |
| `SQLDatabaseSource` | 任意 SQL | `connection`, `query`, `column_mapping` |

### 5.3 列映射

支持 pipe 分隔的备选列名，自动适配不同来源的列命名差异：

```yaml
column_mapping:
  name: "客户名称|单位名称|甲方名称|姓名"  # 按序尝试
  id: "ID|客户编码|编号"
  attributes:
    region: "地区|区域|省份|地址"
    contact: "联系人|负责人|电话|手机"
```

---

## 六、输出适配器

### 6.1 接口定义

```python
class OutputAdapter(ABC):
    name: str
    def write(self, data: list[dict], schema: dict, config: dict) -> str: ...
    def execute_action(self, action: dict, context: dict) -> dict: ...
    @staticmethod
    def resolve_column(row: dict, key: str) -> Any: ...  # 支持点号嵌套访问
```

### 6.2 内置实现

| 适配器 | 用途 | 核心功能 |
|--------|------|----------|
| `ExcelOutputAdapter` | 报表生成 | 多 sheet、列定义、行过滤、样式配置 |
| `WebhookOutputAdapter` | HTTP 推送 | JSON 模板渲染、占位符替换 |
| `PlatformActionOutputAdapter` | 平台操作 | 发消息、退群、confidence 阈值过滤 |

### 6.3 列值解析

支持点号分隔的嵌套路径访问：

```
canonical_name           → row["canonical_name"]
attributes.region        → row["attributes"]["region"]
attributes.contact       → row["attributes"]["contact"]
sources.0.platform_name  → row["sources"][0]["platform_name"]
```

---

## 七、YAML 工作流定义规范

### 7.1 顶层结构

```yaml
workflow:
  name: string                    # 工作流名称
  version: string                 # 版本号

  normalizer:                     # 规范化配置
    rules: [...]                  # 规则列表

  matching:                       # 匹配配置
    generic_words: [...]          # 领域通用词
    generic_chars: string         # 通用字符集
    strategies: [...]             # 策略列表
    thresholds: {...}             # 阈值

  sources: [...]                  # 数据源列表

  enrichment: [...]               # 富化步骤（可选）

  outputs: [...]                  # 输出定义
```

### 7.2 变量替换

支持 `${var}` 和 `${env:VAR}` 语法，运行时从环境变量解析：

```yaml
config:
  path: "${data_root}/input/customers.xlsx"
```

支持默认值：`${env:VAR:default}`。

### 7.3 过滤器语法

YAML 读取支持 `filters`，用于在数据加载阶段过滤记录：

```yaml
filters:
  - field: "type"
    pattern: "^C-"                 # 正则匹配
  - field: "status"
    keywords: ["active", "启用"]    # 关键词包含
```

---

## 八、工作流配置示例

### 8.1 客户信息跨系统匹配

将 CRM 导出的客户名与合同系统中的签约方名称自动关联：

```yaml
workflow:
  name: "customer-cross-matching"
  normalizer:
    rules:
      - type: strip_suffix
        words: ["有限公司", "有限责任公司", "分公司"]
      - type: strip_regex
        patterns: ["\\(.*?\\)", "（.*?）", "\\[.*?\\]"]
      - type: collapse_whitespace

  matching:
    generic_words: ["公司", "集团", "股份", "有限"]
    generic_chars: "省市自治区县"
    strategies:
      - type: exact
      - type: token
      - type: fuzzy
        threshold: 85.0

  sources:
    - id: "crm"
      adapter: "file"
      phase: 1
      config:
        path: "${data_root}/crm_export.xlsx"
        column_mapping:
          name: "客户名称"
          id: "客户编号"
    - id: "contract"
      adapter: "file"
      phase: 2
      config:
        path: "${data_root}/contract_system.xlsx"
        column_mapping:
          name: "签约方|甲方名称"

  outputs:
    - id: "match_report"
      adapter: "excel"
      config:
        file: "${output_dir}/客户关联结果.xlsx"
        columns:
          - key: "canonical_name"
            header: "标准客户名称"
            width: 40
          - key: "attributes.region"
            header: "所属地区"
            width: 15
```

### 8.2 通用工作流模板

使用 `feeflow init my-workflow` 生成骨架：

```yaml
workflow:
  name: "my-workflow"
  normalizer:
    rules:
      - type: collapse_whitespace
  matching:
    strategies:
      - type: exact
      - type: token
      - type: fuzzy
  sources:
    - id: source_1
      adapter: file
      phase: 1
      config:
        path: "data.xlsx"
        column_mapping:
          name: "名称"
  outputs:
    - id: report
      adapter: excel
      config:
        file: "output/report.xlsx"
```

---

## 九、平台集成

### 9.1 当前支持

| 平台 | 适配器 | 能力 |
|------|--------|------|
| 微信（桌面版） | `WeChatPlatform` | 发消息、退群、获取联系人/群列表 |

### 9.2 预留扩展

| 平台 | 适配器 | 状态 |
|------|--------|------|
| 企业微信 | — | 预留 |
| 飞书 | — | 预留 |
| 钉钉 | — | 预留 |
| Agent | — | 预留 |

### 9.3 自动化闭环

`PlatformActionOutputAdapter` 将匹配结果与平台操作串联：

```
匹配结果（高置信度） → PlatformActionOutputAdapter → 自动发送通知
匹配结果（中置信度） → 跟进提醒 → 发消息确认
新数据源触发        → 重新触发匹配管道
```

---

## 十、插件开发指南

### 10.1 通过 Entry Points（推荐）

在插件的 `pyproject.toml` 中注册：

```toml
[project.entry-points."feeflow.sources"]
my_source = "my_package.my_source:MySourceClass"
```

### 10.2 通过目录扫描

在 `feeflow-plugins/` 目录下创建 Python 模块，导出 `ADAPTERS` 列表：

```python
# feeflow-plugins/my_plugin.py
ADAPTERS = [
    ("source", "my_source", MySourceClass),
    ("output", "my_output", MyOutputClass),
]
```

### 10.3 通过显式注册

```python
from feeflow.plugins.discovery import PluginManager

pm = PluginManager()
pm.register_source("custom", CustomSource)
```

---

## 十一、技术选型

| 组件 | 技术 |
|------|------|
| 语言 | Python ≥ 3.10 |
| CLI | Click |
| YAML | PyYAML |
| 模糊匹配 | rapidfuzz |
| 拼音 | pypinyin（可选） |
| Excel | openpyxl |
| 数据库 | SQLAlchemy（可选） |
| 微信 RPA | pywechat/pyweixin（可选） |
| 测试 | pytest |
| 输出美化 | Rich |

### 依赖分组

```bash
pip install feeflow              # 核心依赖
pip install feeflow[phonetic]    # + 拼音匹配
pip install feeflow[sql]         # + 数据库源
pip install feeflow[all]         # + 全部可选
```

---

## 十二、测试

项目包含 48 个单元测试，覆盖：

| 测试文件 | 覆盖模块 | 测试数 |
|----------|----------|--------|
| `test_normalizer.py` | 6 种规则 + PipelineNormalizer | 11 |
| `test_strategies.py` | 4 种策略 + 通用词过滤 | 12 |
| `test_engine.py` | MatchingConfig + EntityMatchingEngine | 7 |
| `test_registry.py` | EntityRecord + EntityRegistry | 10 |
| `test_loader.py` | load_workflow + validate_workflow + 变量替换 | 8 |

```bash
cd project
pytest tests/ -v
```

---

## 十三、项目目录结构

```
project/
├── feeflow/                       # 框架核心包
│   ├── __init__.py               # 版本声明
│   ├── matching/                  # 匹配引擎
│   │   ├── normalizer.py         # 归一化管道 + 6 规则
│   │   ├── strategies.py         # 4 层策略
│   │   ├── engine.py             # 匹配引擎 + 配置
│   │   ├── registry.py           # 实体注册表
│   │   └── alias_store.py        # SQLite 别名持久化
│   ├── sources/                   # 数据源适配
│   │   ├── base.py               # ABC + Record
│   │   ├── file.py               # 5 格式读取
│   │   └── sql.py                # SQLAlchemy 封装
│   ├── platforms/                 # 平台适配
│   │   ├── base.py               # ABC + Contact
│   │   └── wechat.py             # 微信自动化
│   ├── outputs/                   # 输出适配
│   │   ├── base.py               # ABC
│   │   ├── excel.py              # Excel 报表
│   │   ├── webhook.py            # HTTP 推送
│   │   └── platform_action.py    # 平台操作
│   ├── workflow/                  # 工作流编排
│   │   ├── context.py            # 共享上下文
│   │   ├── loader.py             # YAML 加载
│   │   └── pipeline.py           # 管道编排
│   ├── plugins/                   # 插件发现
│   │   └── discovery.py          # PluginManager
│   └── cli/                       # CLI
│       └── main.py               # Click 入口
│
├── domains/                       # 领域配置
├── feeflow-plugins/               # 插件安装目录
├── tests/                         # 48 个单元测试
├── docs/                          # 文档
└── pyproject.toml                 # 包定义
```

---

## 十四、附录

### 14.1 CLI 命令参考

```bash
feeflow run <workflow_file>        # 执行工作流
feeflow validate <workflow_file>   # 验证配置
feeflow plugins                    # 列出所有插件
feeflow init <name>                # 生成模板
```

### 14.2 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `data_root` | 数据根目录 | `D:/data` |
| `output_dir` | 输出目录 | `D:/output` |
| 任意 `${env:VAR}` | 自定义变量 | 按需定义 |

### 14.3 通用词配置建议

通用词应为领域中最常见但缺乏区分度的词汇，如：

- 企业名称常见后缀：`公司`、`集团`、`有限`、`股份`、`分公司`
- 地址/地区常见词：`省`、`市`、`区`、`县`、`镇`、`路`、`号`
- 组织类型常见词：`中心`、`委员会`、`管理处`、`办公室`

通用字符集用于假阳性验证，应为单个汉字：

```
"省市自治区县乡村镇路号院楼栋单元室"
```
