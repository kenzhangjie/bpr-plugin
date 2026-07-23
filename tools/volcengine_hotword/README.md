# volcengine_hotword

火山引擎豆包语音 **热词表(Boosting Table)管理 CLI**。封装官方「热词管理 API v1.0」
(docs 6561/1742791),用来对最源头的 ASR 识别做专有名词纠偏。

## 依赖

只需 `requests`(已验证 Python 3.9 + requests 2.32 可跑)。

```bash
pip install requests
```

## 配置

默认从 `/Users/ken/.config/keys.env` 读取(`--config` 可覆盖),需要加这几个变量:

```env
VOLC_AK=你的IAM_AccessKeyID
VOLC_SK=你的IAM_SecretAccessKey
VOLC_APP_ID=豆包语音应用的AppID        # 整数
VOLC_ACCOUNT_ID=主账号ID               # 可选, 仅 apps 命令需要
```

> ⚠️ 这里的 **AK/SK 是 IAM 密钥**(<https://console.volcengine.com/iam/keymanage>),
> 与豆包语音识别请求用的 `VOLC_API_KEY` **不是同一个东西**,别混用。
> AppID 在豆包语音控制台的应用里看,或先跑 `apps` 命令列出来。

## 用法

已软链到 `~/.local/bin/hotword`,任意目录直接用 `hotword` 即可(等价于
`python3 <本目录>/volcengine_hotword.py`):

```bash
hotword list
hotword add codex|7 鹅厂|6          # 默认表 bpr-ai-vc, 显式权重
hotword add codex 鹅厂               # 裸词 → 自动用 Claude 按档位补 |权重
hotword show
```

**自动权重**:`add` 时不给 `|权重` 的词,会调 OpenAI(默认 `gpt-5-mini`)按
"多容易被 ASR 听错 × 多重要"打 1-10 分。需要 keys.env 里有可用的 `OPENAI_API_KEY`;
读不到或调用失败则回退为服务端默认权重 4(不阻断)。相关配置:
- `VOLC_HOTWORD_WEIGHT_MODEL`(可选,默认 `gpt-5-mini`;可设更轻的模型换速度)
- `--no-auto-weight`:关闭自动,裸词直接用默认 4
- `--weight N`:给本次所有裸词统一权重(覆盖自动)

依赖:自动权重需 `pip install openai`(已装 2.47.0)。gpt-5-mini 是推理模型,
单次约 10-20s;对速度敏感可改 `VOLC_HOTWORD_WEIGHT_MODEL`。

> 大小写敏感:去重按精确字符串匹配,`cowork` 与已存在的 `CoWork` 视为两个词。
> 想加词沿用表里已有的大小写。

下面示例用完整 `python3 ...` 写法,换成 `hotword ...` 完全等价:

```bash
# 整表级
python3 volcengine_hotword.py list                          # 列出所有热词表
python3 volcengine_hotword.py show 我的热词                  # 看某表全部词(ID 或表名)
python3 volcengine_hotword.py upload words.txt --name 我的热词 # 用 txt 建表
python3 volcengine_hotword.py upload words.txt --name 我的热词 --overwrite  # 覆盖同名
python3 volcengine_hotword.py rm 我的热词                    # 删整张表(-y 跳过确认)
python3 volcengine_hotword.py limits                        # 看配额
python3 volcengine_hotword.py apps                          # 列 AppID

# 单词级(API 无此接口, 用「读改写」实现: Get→改→Update)
python3 volcengine_hotword.py add 我的热词 TapNow 影视飓风 --weight 8
python3 volcengine_hotword.py add 我的热词 "奥迪A四L|6"
python3 volcengine_hotword.py delete 我的热词 TapNow

# 任何写操作都可加 --dry-run 先看将发送的请求
python3 volcengine_hotword.py --dry-run upload words.txt --name 我的热词
```

`<表>` 传 **热词表 ID 或表名**都行(表名会自动解析成 ID)。
词支持 `词|权重` 格式,权重 1-10,不填默认 4。

拿到热词表 ID 后,在识别请求里传 `boosting_table_id=<ID>` 即可生效。

## 热词规则(本地已做 fail-fast 校验)

- 单词 ≤10 汉字 / ≤30 字节;单表 ≤5000 词;单应用 ≤500 表
- 权重 1-10
- 除换行/空格外不支持标点;含阿拉伯数字会警告(建议 A4L→A四L)
- 仅支持中英文热词

## 验证状态

**已完整 E2E 实测**(2026-07-23,真实 AK/SK 打线上接口):
`list` / `show` / `upload`(建表,multipart)/ `add` / `delete`(读改写)/ `ListAPIKeys`
全部跑通。已用本工具在 `default` 应用(AppID 1795603753)下建好 `bpr-ai-vc` 表(25 词)。

E2E 过程中修掉的坑(已在代码内注释):
- 火山签名 `x-content-sha256` 在 canonical 里留空值、且不发该头(照官方示例)
- `.env` 值需先去行内注释再去引号(否则 AK/SK 带进注释导致 `InvalidAuthorization`)
- 词表**不能有尾部空行**(否则 `BoostingTableWrongFormat`)
- `GetBoostingTable` 实测**不返回 `File`**,只返回 `Preview`;`show`/`add`/`delete`
  改用 Preview,且 Preview 被截断时 `add`/`delete` 会中止以防丢词

## 文件

- `volcengine_hotword.py` — CLI 主体(配置 / 命令 / 校验 / 读改写)
- `volc_sign.py` — 火山 HMAC-SHA256 签名 + 请求发送
