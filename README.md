# xhs-content-agent

一个手动触发、人工审核的小红书内容运营流水线:按大方向话题拆解出几个具体小切口 → 分别搜索采集同话题下的多篇笔记 → 用 LLM 综合这些笔记的信息(而非照抄改写)生成一篇原创图文 → 自动配一张标题卡片图 → 人工审核(可编辑)→ 批准后发布到小红书创作者账号。

```
大方向话题 ──► 拆解成小切口 ──► 按小切口搜索采集笔记 ──► 综合生成原创草稿
                                                              │
                                                              ▼
   已发布 ◄────────── 人工审核 / 编辑 / 批准 ◄────────── 待审核草稿 + 自动配图
```

提供两种用法:命令行(`cli.py`)和本地网页(`app.py`,含账号 cookie 状态检测、pipeline 树状图可视化、在线审核发布)。

## 目录结构

```
xhs-content-agent/
├── app.py                  # Flask 网页后端(可选,CLI 也能独立完成全部功能)
├── cli.py                  # 命令行入口:collect / explore / draft / review / publish
├── core/
│   ├── xhs_client.py       # 调用 xhs-apis skill(vendored Spider_XHS)的统一封装
│   ├── collector.py        # 按关键词搜索并采集笔记
│   ├── topic_planner.py    # 用 LLM 把大方向拆解成几个具体小切口
│   ├── synthesizer.py      # 用 LLM 综合多篇笔记,生成原创标题+正文
│   ├── text_card.py        # 用 Pillow 生成标题卡片图(配图)
│   ├── llm_json.py         # DeepSeek 调用的公共封装(JSON 模式 / 纯文本模式)
│   ├── db.py                # SQLite 数据层
│   ├── review.py           # 终端交互式审核
│   └── publisher.py        # 发布到小红书创作者平台(支持 --dry-run)
├── templates/index.html    # 网页界面
├── static/{app.js,style.css}
└── config/accounts.json.example  # cookie 配置模板(真实文件不进版本库)
```

## 环境准备

依赖 [XhsSkills](https://github.com/cv-cat/XhsSkills) 的 `xhs-apis` skill(需要作为同级目录 `../XhsSkills` 存在,并按其 README 装好 Python + Node 依赖),用来实际调用小红书的接口。

```bash
pip install -r requirements.txt
```

复制两份配置模板并填入真实值:

```bash
cp .env.example .env                                # 填入 DEEPSEEK_API_KEY
cp config/accounts.json.example config/accounts.json # 填入小红书 pc / creator 账号的 cookies_str
```

cookie 获取方式:浏览器登录小红书 pc 端 / 创作者平台后,F12 打开开发者工具 → Network → 找任意请求 → 复制请求头里的 `cookie` 字段。这两个配置文件已经在 `.gitignore` 里,不会被提交。

## 用法

### 命令行

```bash
python cli.py explore --theme "跨境电商独立站选品" --topics 3 --limit 5   # 拆解话题 + 采集
python cli.py draft                                                      # 综合生成草稿(自动配标题卡片图)
python cli.py review                                                     # 终端交互式审核:批准(y)/拒绝(n)/编辑(e)
python cli.py publish --dry-run                                          # 预览发布 payload,不真实发布
python cli.py publish                                                    # 真实发布已批准的草稿
```

### 网页

```bash
python app.py   # http://127.0.0.1:5050,仅本机可访问
```

网页包含四块:账号 / Cookie 状态(自动检测是否失效)、生成草稿控制面板(触发 explore / draft)、Pipeline 概览树状图(主题→小切口→采集笔记→生成草稿,只展示最新一次 explore)、待审核草稿列表(在线编辑/批准/拒绝)、发布面板(dry-run 默认,真实发布需要额外勾选确认框 + 二次弹窗确认)。

## 说明与限制

- 这一版是**手动触发**的:没有定时任务,发布前必须经过人工审核批准,真实发布需要显式确认——这是有意的设计,不是待办事项。
- 配图是本地用 Pillow 生成的纯标题卡片(不是小红书官方的"文字配图"功能,那个功能没有被逆向出可调用的 API),想用真实照片可以在生成草稿后手动替换 `data/drafts/<id>/` 下的图片文件。
- LLM 综合生成的内容可能包含不完全准确的费率/政策等信息,发布前请自行核实,不构成专业建议。
- 仅供个人学习/内容运营效率工具使用,请遵守小红书平台规则,不要用于批量营销/垃圾内容发布。

## Credits

本项目的小红书接口能力构建在以下开源项目之上:

- [Spider_XHS](https://github.com/cv-cat/Spider_XHS) — 逆向还原了小红书 PC 端与创作者平台的签名算法,封装了采集与发布的核心 HTTP 接口。**仅供学习交流使用,禁止任何商业化行为。**
- [XhsSkills](https://github.com/cv-cat/XhsSkills) — 基于 Spider_XHS 封装的 Agent Skill(`xhs-apis`),本项目通过它调用小红书接口。

内容生成使用 [DeepSeek](https://www.deepseek.com/) API(`deepseek-chat`)。
