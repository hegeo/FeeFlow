# FeeFlow（飞流）

> **实体匹配与自动化工作流平台**
> 将散落在不同系统中的实体信息自动关联到同一主体，并基于关联结果执行输出和自动化操作。

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 概览

FeeFlow 解决一个核心问题：**不同来源的实体信息如何自动关联到同一主体？**

例如客户单位 A 系统叫"××科技有限公司"，B 系统叫"××科技公司"，C 系统备注"××科技(张经理)"——同一主体在不同系统中的名称、联系方式、地址等信息往往不一致，传统方案依赖人工逐条核对。

FeeFlow 通过**可配置的匹配管道** + **多策略引擎** + **插件化适配器**，让这一过程完全自动化。

### 核心流程

```
数据源 → 归一化 → 实体匹配 → 富化 → 输出/操作

        可配置 YAML 工作流定义
```

### 适用场景

- 客户单位信息跨系统关联（CRM / 合同 / 售后系统）
- 用户名称与联系方式的跨平台匹配
- 地址、地区信息的标准化与关联
- 聊天群组中的客户识别与自动化管理

---

## 快速开始

### 安装

```bash
pip install feeflow
```

或从源码安装：

```bash
cd project
pip install -e .
```

### 验证安装

```bash
feeflow --version
feeflow plugins
```

### 创建第一个工作流

```bash
feeflow init my-workflow
```

这会生成一个 `my-workflow.yaml` 模板文件。

### 执行工作流

```bash
feeflow run my-workflow.yaml
```

---

## 工作流定义

FeeFlow 完全由 YAML 配置驱动。以下是一个最小工作流：

```yaml
workflow:
  name: "customer-matching"

  # 归一化规则
  normalizer:
    rules:
      - type: strip_suffix
        words: ["有限公司", "分公司"]
      - type: collapse_whitespace

  # 匹配配置
  matching:
    generic_words: ["公司", "科技", "集团"]
    strategies:
      - type: exact
      - type: token
        containment_score: 90.0
      - type: fuzzy
        threshold: 85.0

  # 数据源
  sources:
    - id: "crm_export"
      adapter: "file"
      phase: 1
      config:
        path: "data/crm_customers.xlsx"
        column_mapping:
          name: "客户名称"
          id: "客户ID"
    - id: "contract_data"
      adapter: "file"
      phase: 2
      config:
        path: "data/contracts.xlsx"
        column_mapping:
          name: "签约方|甲方名称"

  # 输出
  outputs:
    - id: "report"
      adapter: "excel"
      config:
        file: "output/matched_result.xlsx"
        columns:
          - key: "canonical_name"
            header: "标准名称"
            width: 35
          - key: "attributes.region"
            header: "地区"
            width: 15
          - key: "attributes.contact"
            header: "联系方式"
            width: 20
```

---

## CLI 命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `run` | 执行工作流 | `feeflow run workflow.yaml --verbose` |
| `validate` | 验证配置 | `feeflow validate workflow.yaml` |
| `plugins` | 列出插件 | `feeflow plugins` |
| `init` | 生成模板 | `feeflow init my-flow` |

`run` 命令支持 `--env KEY=VALUE` 覆盖环境变量：

```bash
feeflow run workflow.yaml -e data_root=D:/data -e output_dir=D:/out
```

---

## 匹配策略

FeeFlow 内置 4 层匹配策略，按序执行、短路退出：

| 策略 | 方法 | 置信度 |
|------|------|--------|
| **精确匹配** | 归一化后全等比较 | 100 |
| **Token 匹配** | 子串包含 / Token 重叠率 | 80–95 |
| **模糊匹配** | rapidfuzz 加权评分 | ≥85 |
| **拼音匹配** | pypinyin → 拼音相似度 | ≥90 |

> 拼音匹配适合中文名称匹配，需要安装可选依赖：`pip install feeflow[phonetic]`

---

## 数据源

| 格式 | 适配器 | 说明 |
|------|--------|------|
| Excel (.xlsx) | `file` | 支持列映射、多 sheet |
| CSV | `file` | 自定义编码 |
| TXT | `file` | 正则解析 |
| YAML | `file` | 字段映射 + 过滤器 |
| 目录扫描 | `file` | 文件名提取 + 递归 |
| SQL 数据库 | `sql` | SQLAlchemy 连接 |

列映射支持 pipe 分隔的备选名，自动适配不同来源的列命名差异：

```yaml
column_mapping:
  name: "客户名称|单位名称|甲方名称"
  attributes:
    region: "地区|区域|省份"
    contact: "联系人|负责人|电话"
```

---

## 输出

| 输出 | 适配器 | 说明 |
|------|--------|------|
| Excel 报表 | `excel` | 多 sheet、列定制、行过滤、样式 |
| Webhook | `webhook` | JSON 推送、模板渲染 |
| 平台操作 | `platform_action` | 发消息、退群 |

---

## 平台集成

| 平台 | 适配器 | 状态 | 能力 |
|------|--------|------|------|
| 微信（桌面版） | `WeChatPlatform` | 可用 | 发消息、退群、获取联系人 |
| 企业微信 | — | 预留 | — |
| 飞书 | — | 预留 | — |
| 钉钉 | — | 预留 | — |

WeChat 适配器通过 `pywechat` (pywinauto RPA) 实现。未安装时自动进入 DRY-RUN 模式。

---

## 插件扩展

### 通过 Entry Points（推荐）

在插件的 `pyproject.toml` 中注册：

```toml
[project.entry-points."feeflow.sources"]
my_source = "my_package:MySource"
```

### 通过目录扫描

将 Python 文件放在 `feeflow-plugins/` 目录下：

```python
# feeflow-plugins/my_plugin.py
ADAPTERS = [
    ("source", "my_source", MySource),
    ("output", "my_output", MyOutput),
]
```

---

## 项目结构

```
feeflow/
├── cli/             # 命令行入口
├── matching/        # 匹配引擎
│   ├── engine.py    # EntityMatchingEngine
│   ├── strategies.py # 4层策略
│   ├── normalizer.py # 归一化管道
│   ├── registry.py  # 实体注册表
│   └── alias_store.py # 别名库
├── sources/         # 数据源适配
├── platforms/       # 平台适配
├── outputs/         # 输出适配
├── workflow/        # 工作流编排
│   ├── pipeline.py  # PipelineRunner
│   ├── loader.py    # YAML加载
│   └── context.py   # 执行上下文
└── plugins/         # 插件发现
```

---

## 依赖

```bash
# 核心
pip install feeflow

# 可选
pip install feeflow[phonetic]    # 拼音匹配
pip install feeflow[sql]         # 数据库源
pip install feeflow[excel]       # Excel 增强
pip install feeflow[all]         # 全部
```

核心依赖：`pyyaml`, `rapidfuzz`, `click`, `rich`, `openpyxl`

---

## 开发

```bash
cd project
pip install -e .
pytest tests/ -v
```

---

## License

MIT
