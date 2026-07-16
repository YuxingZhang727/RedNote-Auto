# xhs-content-agent

一个手动触发、人工审核的小红书内容运营流水线:按大方向话题拆解出几个具体小切口 → 分别搜索采集同话题下的多篇笔记 → 用 LLM 综合这些笔记的信息(而非照抄改写)生成一篇原创图文 → 自动配一张标题卡片图 → 人工审核(可编辑)→ 批准后发布到小红书创作者账号。

```
大方向话题 ──► 拆解成小切口 ──► 按小切口搜索采集笔记 ──► 综合生成原创草稿
                                                              │
                                                              ▼
   已发布 ◄────────── 人工审核 / 编辑 / 批准 ◄────────── 待审核草稿 + 自动配图
```

提供两种用法:命令行(`cli.py`)和本地网页(`app.py`,含账号 cookie 状态检测、pipeline 树状图可视化、在线审核发布)。两者共用同一套 `core/` 逻辑和同一个 SQLite 数据库,可以混用——比如用命令行跑采集,再打开网页审核。

## 目录结构

```
xhs-content-agent/
├── app.py                  # Flask 网页后端(可选,CLI 也能独立完成全部功能)
├── cli.py                  # 命令行入口:collect / explore / draft / review / publish
├── core/
│   ├── xhs_client.py       # 调用 xhs-apis skill(vendored Spider_XHS)的统一封装,含失败重试
│   ├── collector.py        # 按关键词搜索并采集笔记
│   ├── topic_planner.py    # 用 LLM 把大方向拆解成几个具体小切口
│   ├── synthesizer.py      # 用 LLM 综合多篇笔记,生成原创标题+正文
│   ├── text_card.py        # 用 Pillow 生成标题卡片图(配图)
│   ├── llm_json.py         # DeepSeek 调用的公共封装(JSON 模式 / 纯文本模式)
│   ├── image_processor.py  # (备用)真实图片去水印+裁剪,当前流程未默认调用
│   ├── db.py                # SQLite 数据层,建表 + 增删改查
│   ├── review.py           # 终端交互式审核
│   └── publisher.py        # 发布到小红书创作者平台(支持 --dry-run)
├── templates/index.html    # 网页界面(单页)
├── static/{app.js,style.css}
├── data/                   # 运行时生成:pipeline.db、drafts/<id>/ 配图(不进版本库)
├── config/accounts.json.example  # cookie 配置模板(真实文件不进版本库)
└── .env.example             # DEEPSEEK_API_KEY 模板
```

## 环境准备

### 1. 依赖 xhs-apis skill

小红书接口调用依赖 [XhsSkills](https://github.com/cv-cat/XhsSkills) 的 `xhs-apis` skill,需要它作为**同级目录**存在,即:

```
某个目录/
├── XhsSkills/           # 克隆自 github.com/cv-cat/XhsSkills
└── xhs-content-agent/   # 本项目
```

按 XhsSkills 自己的 README 装好它的 Python 依赖(`pip install -r XhsSkills/skills/xhs-apis/scripts/requirements.txt`)和 Node 依赖(`cd XhsSkills/skills/xhs-apis/scripts && npm install`)。

### 2. 安装本项目依赖

```bash
pip install -r requirements.txt
```

### 3. 配置账号 cookie 和 API key

```bash
cp .env.example .env
cp config/accounts.json.example config/accounts.json
```

编辑 `.env`,填入:

```
DEEPSEEK_API_KEY=你的-deepseek-key
```

去 [platform.deepseek.com](https://platform.deepseek.com) 注册后在 API Keys 页面生成。

编辑 `config/accounts.json`,填入两个账号的 cookie:

```json
{
  "pc": { "cookies_str": "..." },
  "creator": { "cookies_str": "..." }
}
```

- `pc`:小红书网页版(www.xiaohongshu.com)登录后的 cookie,用于搜索/采集笔记
- `creator`:小红书创作者平台(creator.xiaohongshu.com)登录后的 cookie,用于发布

获取方式:浏览器登录对应站点后,按 F12 打开开发者工具 → Network(网络)标签 → 刷新页面或触发任意请求 → 点开任意一个请求 → 在请求头(Request Headers)里找到 `cookie` 字段,复制完整值。

`.env` 和 `config/accounts.json` 都已经在 `.gitignore` 里,不会被提交到仓库。cookie 会过期(一般几天到几周不等),失效后按同样方式重新获取、替换即可——网页版界面会自动检测并提醒。

## 用法

### 命令行

完整走一遍流程:

```bash
# 1. 把一个大方向拆成几个具体小切口,并分别搜索采集(每个小切口采几篇)
python cli.py explore --theme "<你的大方向话题>" --topics 3 --limit 5

# 2. 对上一步采集到的、还没处理过的笔记,按小切口分组综合生成原创草稿(自动配标题卡片图)
python cli.py draft

# 3. 终端交互式审核:每条草稿会打印话题、来源笔记标题、生成的标题/正文、配图路径
#    输入 y 批准 / n 拒绝 / e 用 $EDITOR 打开编辑标题和正文后批准 / 其他键跳过
python cli.py review

# 4. 先 dry-run 看一眼真实会发送的完整 payload(标题/正文/图片路径),不会真的调用发布接口
python cli.py publish --dry-run

# 5. 确认无误后正式发布已批准的草稿
python cli.py publish
```

也可以只针对一个关键词单独采集,不经过话题拆解:

```bash
python cli.py collect --keyword "具体关键词" --limit 10
```

每个命令都是独立、可重复运行的:`draft` 只处理 `collect`/`explore` 采集到的、状态还是"新"的笔记;重复运行 `collect`/`explore` 不会导致同一篇笔记被重复采集(按 note_id 去重)。

### 网页

```bash
python app.py
```

打开 `http://127.0.0.1:5050`(只监听本机,不会暴露到公网)。页面从上到下分五块:

1. **账号 / Cookie**——pc / creator 两个账号的连接状态,打开页面会自动各测一次;任意一个失效会在页面顶部弹红色提醒。可以直接在这里粘贴新 cookie 保存,不用去改配置文件。
2. **生成草稿**——表单形式的 `explore`(大方向话题 + 拆几个小切口 + 每个小切口采集数量)和一个"对新采集的笔记生成草稿"按钮,对应命令行的 `explore` 和 `draft`。执行结果(JSON)会打印在下方日志框。
3. **Pipeline 概览**——树状图,展示最新一次 explore 的完整链路:主题 → 每个小切口 → 采集到的笔记(点击可跳转原笔记)→ 生成的草稿(带状态徽章,点击会滚动到下面对应的审核卡片并高亮)。只展示最新一次,不会堆积历史记录。
4. **待审核草稿**——每条草稿一张卡片:标题和正文都是可编辑的输入框/文本框,改完点"保存修改"即可;配图有缩略图预览;批准/拒绝按钮。
5. **发布**——显示当前已批准待发布的数量。"Dry-run 预览"随时可点,只打印 payload 不会真发。要真实发布必须先勾选"我确认要真实发布(不可逆)",按钮才会变为可点击,点击后还会弹一次浏览器原生确认框,双重确认后才会调用发布接口。

## 说明与限制

- 这一版是**手动触发**的:没有定时任务,发布前必须经过人工审核批准,真实发布需要显式确认——这是有意的设计,不是待办事项。
- 配图是本地用 Pillow 生成的纯标题卡片(不是小红书官方的"文字配图"功能,那个功能没有被逆向出可调用的 API),想用真实照片可以在生成草稿后手动替换 `data/drafts/<id>/` 下的图片文件,或者调用 `core/image_processor.py` 里现成的去水印+裁剪逻辑接自己的图片来源。
- LLM 综合生成的内容可能包含不完全准确的费率/政策等信息,发布前请自行核实,不构成专业建议。
- xhs-apis 底层依赖的网络环境偶尔会出现连接被重置/截断的情况(和本机代理/网络状况有关),`xhs_client.py` 对只读接口(搜索、拿详情)做了自动重试;如果重试后依然失败,命令行/网页都会打印清晰的失败原因,重新跑一次通常就好了。
- 仅供个人学习/内容运营效率工具使用,请遵守小红书平台规则,不要用于批量营销/垃圾内容发布。

## Credits

本项目的小红书接口能力构建在以下开源项目之上:

- [Spider_XHS](https://github.com/cv-cat/Spider_XHS) — 逆向还原了小红书 PC 端与创作者平台的签名算法,封装了采集与发布的核心 HTTP 接口。**仅供学习交流使用,禁止任何商业化行为。**
- [XhsSkills](https://github.com/cv-cat/XhsSkills) — 基于 Spider_XHS 封装的 Agent Skill(`xhs-apis`),本项目通过它调用小红书接口。

内容生成使用 [DeepSeek](https://www.deepseek.com/) API(`deepseek-chat`)。
