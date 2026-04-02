---
name: traditional-chinese-support
description: 繁体中文适配方案。当用户提到"繁体"、"简繁转换"、"多语言"、"台湾繁体"、"OpenCC"、"LangConverter"、"文本匹配"、"OCR匹配"时自动调用。提供简繁转换、双语匹配、游戏文本适配等实现参考。
---

# 繁体中文适配方案

本项目支持简体中文和繁体中文（台湾繁体）的自动适配，确保 OCR 文本匹配在两种语言环境下都能正常工作。

## 核心组件

### LangConverter 工具类

**文件**: `src/utils/LangConverter.py`

```python
from src.utils.LangConverter import LangConverter

# 简体转台湾繁体
traditional = LangConverter.simplify_to_traditional("进入游戏")
# 结果: "進入遊戲"

# 创建双语匹配模式
bilingual = LangConverter.create_bilingual_pattern("进入游戏")
# 结果: "进入游戏|進入遊戲"

# 创建双语正则表达式
import re
pattern = re.compile(r"适龄提示|年龄分级")
bilingual_regex = LangConverter.create_bilingual_regex(pattern)
# 结果: re.compile(r"适龄提示|適齡提示|年龄分级|年齡分級")
```

## 转换优先级

1. **内置字典优先** - 游戏特定词汇确保精确匹配
2. **OpenCC 台湾繁体** - 通用词汇使用 OpenCC `s2tw.json` 转换
3. **字典逐字转换** - OpenCC 不可用时的备选方案

## 依赖配置

**requirements.txt**:
```
opencc>=1.1.0
```

**OpenCC 配置**:
- 使用 `s2tw.json`（简体 → 台湾繁体）
- 游戏使用台湾繁体，如：帳戶名、帳號

## 内置字典

游戏特定词汇映射（台湾繁体）：

| 简体 | 台湾繁体 |
|------|---------|
| 进入游戏 | 進入遊戲 |
| 开始游戏 | 開始遊戲 |
| 登录 | 登錄 |
| 账号 | 帳號 |
| 账户名 | 帳戶名 |
| 适龄提示 | 年齡分級 |
| 换区 | 換區 |
| 排位赛 | 排位賽 |
| 问卷调查 | 問卷調查 |

## 使用方式

### 1. 自动转换（推荐）

通过 `find_boxes()` 方法自动处理：

```python
# BaseJumpTask 中已集成自动转换
texts = self.ocr()
# 自动根据 GUI 语言设置转换匹配模式
boxes = self.find_boxes(texts, match=re.compile(r"进入游戏"))
```

### 2. 手动转换

```python
from src.utils.LangConverter import LangConverter

# 字符串转换
text = LangConverter.simplify_to_traditional("进入游戏")

# 正则表达式转换
pattern = re.compile(r"进入游戏")
converted = LangConverter.convert_regex_pattern(pattern, True)

# 双语模式创建
bilingual = LangConverter.create_bilingual_pattern("进入游戏")
```

## 双语正则表达式

当 GUI 设置为繁体中文时，`_convert_match_for_lang()` 会自动创建双语模式：

```python
# 原始正则
re.compile(r"适龄提示|年龄分级")

# 转换后（同时匹配简体和繁体）
re.compile(r"适龄提示|適齡提示|年龄分级|年齡分級")
```

## GUI 配置

在 `基本设置.json` 中配置：

```json
{
    "游戏文本语言": "繁体中文"  // 或 "简体中文"
}
```

## 注意事项

1. **字典优先**: 游戏特定词汇必须在字典中定义，确保精确匹配
2. **台湾繁体**: OpenCC 使用 `s2tw.json`，不是 `s2t.json`（标准繁体）
3. **双语模式**: 转换后的正则同时匹配简体和繁体，确保兼容性
4. **备选方案**: 即使 OpenCC 未安装，字典也能提供基本转换功能

## 常见问题

### Q: 为什么"账户名"匹配失败？

A: OpenCC 默认转换为香港繁体"賬戶名"，但游戏使用台湾繁体"帳戶名"。解决方案：
1. 在字典中添加完整映射
2. 或使用 `s2tw.json` 替代 `s2t.json`

### Q: 如何添加新的游戏词汇？

A: 在 `LangConverter.py` 的 `_SIMPLIFIED_TO_TRADITIONAL` 字典中添加：

```python
_SIMPLIFIED_TO_TRADITIONAL = {
    # 添加新词汇
    '新词汇': '新詞彙',
}
```

## 关键文件

| 文件 | 用途 |
|------|------|
| `src/utils/LangConverter.py` | 简繁转换工具类 |
| `src/task/BaseJumpTask.py` | 自动转换集成 |
| `requirements.txt` | OpenCC 依赖 |
| `configs/基本设置.json` | 语言配置 |
