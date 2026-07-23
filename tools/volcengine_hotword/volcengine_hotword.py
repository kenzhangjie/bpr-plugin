#!/usr/bin/env python3
"""volcengine_hotword — 火山引擎豆包语音 热词表(Boosting Table)管理 CLI。

命令:
  list                        列出所有热词表(ID / 名字 / 词数 / 预览)
  show   <表>                 查看某张表的全部词
  upload <file.txt> --name N  用 txt 建表(同名需加 --overwrite 覆盖)
  add    <表> 词...           往表里加词(--weight 给新词统一权重)
  delete <表> 词...           从表里删词
  rm     <表>                 删整张表
  limits                      查看配额(表数 / 词数上限 + 已用)
  apps                        列出 AppID(帮你找 app_id)

<表> 可传 热词表 ID 或 表名(表名会自动解析成 ID)。
词支持 "词|权重" 格式,权重范围 1-10,不填默认 4。

配置: 默认从 /Users/ken/.config/keys.env 读取(--config 覆盖),需要:
  VOLC_AK / VOLC_SK / VOLC_APP_ID   (必需)
  VOLC_ACCOUNT_ID                   (仅 apps 命令需要)

注意: 这里的 AK/SK 是 IAM 密钥(console.volcengine.com/iam/keymanage),
      与豆包语音识别用的 VOLC_API_KEY 不是同一个东西。
"""
import argparse
import json
import re
import sys

import volc_sign as vs

DEFAULT_CONFIG = "/Users/ken/.config/keys.env"
VERSION_BOOSTING = "2022-08-30"
VERSION_APPS = "2021-11-22"

# 官方配额限制(本地 fail-fast 用,详见 doc 6561/1742791)
MAX_WORD_BYTES = 30   # 单词 utf-8 字节上限
MAX_WORD_CN = 10      # 单词汉字数上限
MAX_TABLE_WORDS = 5000
WEIGHT_MIN, WEIGHT_MAX = 1, 10
DEFAULT_WEIGHT = 4


class VolcError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


# --------------------------------------------------------------------------- 配置

def load_config(path):
    conf = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export "):]
                key, _, val = line.partition("=")
                val = val.strip()
                # 先去行内注释(空白+#),base64 密钥不含空格所以安全
                val = re.split(r"\s+#", val, 1)[0].strip()
                # 再去引号包裹
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                conf[key.strip()] = val
    except FileNotFoundError:
        sys.exit(f"配置文件不存在: {path}")
    return conf


def require(conf, key):
    val = conf.get(key)
    if not val:
        sys.exit(
            f"配置缺少 {key}(在 {conf.get('__path__', DEFAULT_CONFIG)} 里)。\n"
            f"热词管理需要 VOLC_AK / VOLC_SK / VOLC_APP_ID,"
            f"AK/SK 从 console.volcengine.com/iam/keymanage 获取。"
        )
    return val


# --------------------------------------------------------------------------- 响应处理

def handle(resp):
    """解析响应,出错抛 VolcError,成功返回 Result。"""
    if isinstance(resp, dict) and resp.get("dry_run"):
        print("[dry-run] 将要发送的请求:")
        print(json.dumps(resp, ensure_ascii=False, indent=2))
        return None
    try:
        data = resp.json()
    except ValueError:
        raise VolcError(str(resp.status_code), f"非 JSON 响应: {resp.text[:300]}")
    # ListApplications 是老格式: {"status","error","data"}
    if "ResponseMetadata" not in data and "data" in data:
        if data.get("error"):
            raise VolcError("ListApplications", str(data["error"]))
        return data["data"]
    err = data.get("ResponseMetadata", {}).get("Error")
    if err:
        raise VolcError(err.get("Code"), err.get("Message"))
    if resp.status_code >= 300:
        raise VolcError(str(resp.status_code), resp.text[:300])
    return data.get("Result", data)


# --------------------------------------------------------------------------- 客户端

class HotwordClient:
    def __init__(self, ak, sk, app_id, account_id=None, dry_run=False,
                 default_table="bpr-ai-vc", openai_key=None,
                 weight_model="gpt-5-mini"):
        self.ak = ak
        self.sk = sk
        self.app_id = int(app_id)
        self.account_id = account_id
        self.dry_run = dry_run
        self.default_table = default_table
        self.openai_key = openai_key
        self.weight_model = weight_model

    def _json(self, action, body=None, query_extra=None, method="POST"):
        return handle(vs.call_json(
            action, VERSION_BOOSTING, self.ak, self.sk,
            body_params=body, query_extra=query_extra, method=method,
            dry_run=self.dry_run,
        ))

    def list_tables(self, page=1, size=100, preview=10):
        return self._json("ListBoostingTable", {
            "AppID": self.app_id, "PageNumber": page,
            "PageSize": size, "PreviewSize": preview,
        })

    def get_table(self, table_id):
        return self._json("GetBoostingTable",
                          {"AppID": self.app_id, "BoostingTableID": table_id})

    def delete_table(self, table_id):
        return self._json("DeleteBoostingTable",
                          {"AppID": self.app_id, "BoostingTableID": table_id})

    def limits(self):
        return self._json("ListBoostingTableLimits", {"AppID": self.app_id})

    def check_name(self, name):
        return self._json("CheckBoostingTableName",
                          {"AppID": self.app_id, "BoostingTableName": name})

    def list_apps(self):
        if not self.account_id:
            sys.exit("apps 命令需要配置 VOLC_ACCOUNT_ID。")
        return handle(vs.call_json(
            "ListApplications", VERSION_APPS, self.ak, self.sk,
            query_extra={"X-Account-Id": self.account_id}, method="GET",
            dry_run=self.dry_run,
        ))

    def create_table(self, name, content_bytes):
        return handle(vs.call_multipart(
            "CreateBoostingTable", VERSION_BOOSTING, self.ak, self.sk,
            fields={"Action": "CreateBoostingTable", "Version": VERSION_BOOSTING,
                    "AppID": self.app_id, "BoostingTableName": name},
            file_bytes=content_bytes, dry_run=self.dry_run,
        ))

    def update_table(self, table_id, content_bytes, name=None):
        fields = {"Action": "UpdateBoostingTable", "Version": VERSION_BOOSTING,
                  "AppID": self.app_id, "BoostingTableID": table_id}
        if name:
            fields["BoostingTableName"] = name
        return handle(vs.call_multipart(
            "UpdateBoostingTable", VERSION_BOOSTING, self.ak, self.sk,
            fields=fields, file_bytes=content_bytes, dry_run=self.dry_run,
        ))


# --------------------------------------------------------------------------- 热词解析 / 校验

def parse_line(line):
    """'词|8' -> ('词', 8);'词' -> ('词', None)。"""
    line = line.strip()
    if not line:
        return None
    if "|" in line:
        word, _, w = line.partition("|")
        word = word.strip()
        try:
            return word, int(w.strip())
        except ValueError:
            return word, None
    return line, None


def validate_word(word, weight):
    if not word:
        raise ValueError("空词")
    if len(word.encode("utf-8")) > MAX_WORD_BYTES:
        raise ValueError(f"「{word}」超长(utf-8 需 ≤{MAX_WORD_BYTES} 字节)")
    cn = sum(1 for c in word if "一" <= c <= "鿿")
    if cn > MAX_WORD_CN:
        raise ValueError(f"「{word}」汉字数超过 {MAX_WORD_CN}")
    if weight is not None and not (WEIGHT_MIN <= weight <= WEIGHT_MAX):
        raise ValueError(f"「{word}」权重 {weight} 越界(需 {WEIGHT_MIN}-{WEIGHT_MAX})")
    for ch in word:
        if ch.isspace():
            continue
        if ch.isalnum():
            continue
        raise ValueError(f"「{word}」含标点/特殊符号「{ch}」,热词不支持(数字/符号请换汉字,如 A4L→A四L)")
    if any(c.isdigit() and c.isascii() for c in word):
        print(f"  ⚠ 「{word}」含阿拉伯数字,火山建议换成汉字(如 A4L→A四L)", file=sys.stderr)


def fmt_line(word, weight):
    return f"{word}|{weight}" if weight is not None else word


def parse_file_content(text):
    """返回有序的 [(word, weight), ...],按词去重(保留首次)。"""
    seen = {}
    for raw in text.splitlines():
        parsed = parse_line(raw)
        if parsed and parsed[0] and parsed[0] not in seen:
            seen[parsed[0]] = parsed[1]
    return list(seen.items())


def build_content(pairs):
    # 不加结尾换行: 火山会把尾部空行判为非法格式 (BoostingTableWrongFormat)
    return "\n".join(fmt_line(w, wt) for w, wt in pairs)


# --------------------------------------------------------------------------- 辅助

def _table_pairs(r):
    """从 GetBoostingTable 结果取全部词对(用于读改写)。
    火山实测不返回 File,只返回 Preview;若 Preview 少于 WordCount(被截断),
    中止以防 add/delete 静默丢词。"""
    content = r.get("File")
    if content:
        return parse_file_content(content)
    preview = r.get("Preview", [])
    if len(preview) < r.get("WordCount", 0):
        sys.exit(f"无法安全读改写: 接口只返回 {len(preview)} 词预览,"
                 f"表内共 {r.get('WordCount')} 词。请改用 upload --overwrite 传完整文件。")
    return parse_file_content("\n".join(preview))


def resolve_table(client, ref):
    """把 ID 或表名解析成 BoostingTableID。"""
    result = client.list_tables()
    if result is None:  # dry-run
        return ref
    for t in result.get("BoostingTables", []):
        if t["BoostingTableID"] == ref or t["BoostingTableName"] == ref:
            return t["BoostingTableID"]
    sys.exit(f"找不到热词表: {ref}(用 `list` 看现有表)")


# --------------------------------------------------------------------------- 命令

def cmd_list(client, args):
    r = client.list_tables()
    if r is None:
        return
    tables = r.get("BoostingTables", [])
    if not tables:
        print("(没有热词表)")
        return
    print(f"共 {r.get('BoostingTableCount', len(tables))} 张表:\n")
    for t in tables:
        preview = " ".join(t.get("Preview", [])[:8])
        print(f"  {t['BoostingTableName']}")
        print(f"    ID={t['BoostingTableID']}  词数={t.get('WordCount')}  "
              f"更新={t.get('UpdateTime')}")
        print(f"    预览: {preview}\n")


def cmd_show(client, args):
    tid = resolve_table(client, args.table or client.default_table)
    r = client.get_table(tid)
    if r is None:
        return
    print(f"表名: {r['BoostingTableName']}  (ID={r['BoostingTableID']}, "
          f"{r.get('WordCount')} 词)\n")
    content = r.get("File")
    if content:
        print(content.rstrip("\n"))
    else:
        # 火山实测不返回 File,只返回 Preview(大表可能被截断)
        preview = r.get("Preview", [])
        print("\n".join(preview))
        if r.get("WordCount", 0) > len(preview):
            print(f"\n(仅显示 Preview {len(preview)} 词,表内共 {r.get('WordCount')} 词)")


def cmd_upload(client, args):
    with open(args.file, encoding="utf-8") as f:
        pairs = parse_file_content(f.read())
    if not pairs:
        sys.exit("文件里没有有效热词。")
    if len(pairs) > MAX_TABLE_WORDS:
        sys.exit(f"词数 {len(pairs)} 超过单表上限 {MAX_TABLE_WORDS}。")
    for w, wt in pairs:
        validate_word(w, wt)
    content = build_content(pairs).encode("utf-8")

    existing = _find_table(client, args.name)
    if existing and not args.overwrite:
        sys.exit(f"表名「{args.name}」已存在(ID={existing})。"
                 f"覆盖请加 --overwrite,或换个名字。")
    if existing:
        r = client.update_table(existing, content, name=args.name)
        action = "已覆盖"
    else:
        r = client.create_table(args.name, content)
        action = "已创建"
    if r is None:
        return
    print(f"{action}热词表「{r['BoostingTableName']}」"
          f"(ID={r['BoostingTableID']}, {r.get('WordCount')} 词)")
    print(f"→ 识别请求里传 boosting_table_id={r['BoostingTableID']} 即可生效。")


def _auto_weights(client, words):
    """裸词(没给权重)→ 用 Claude 按档位算权重。失败则空 dict(词走服务端默认 4)。"""
    if not words:
        return {}
    if not client.openai_key:
        print("  ⚠ 未配置 OPENAI_API_KEY,不自动算权重,这些词将用服务端默认权重 4",
              file=sys.stderr)
        return {}
    try:
        import autoweight
        m = autoweight.assign_weights(words, client.openai_key, client.weight_model)
        print("  🤖 自动权重: " + "  ".join(f"{w}|{m.get(w, '?')}" for w in words))
        return m
    except Exception as e:
        print(f"  ⚠ 自动算权重失败({type(e).__name__}: {e}),这些词将用默认权重 4",
              file=sys.stderr)
        return {}


def cmd_add(client, args):
    tid = resolve_table(client, args.table or client.default_table)
    r = client.get_table(tid)
    if r is None:
        return
    pairs = _table_pairs(r)
    existing_words = {w for w, _ in pairs}

    # 解析输入词;记录哪些没给权重
    parsed = []
    for token in args.words:
        word, weight = parse_line(token)
        if weight is None and args.weight is not None:
            weight = args.weight
        parsed.append((word, weight))

    # 没给权重的裸词 → 自动算(--no-auto-weight 关闭)
    weights_map = {}
    if not args.no_auto_weight:
        weights_map = _auto_weights(client, [w for w, wt in parsed if wt is None])

    added = []
    for word, weight in parsed:
        if weight is None:
            weight = weights_map.get(word)  # 仍 None 则由服务端默认 4
        validate_word(word, weight)
        if word in existing_words:
            print(f"  · 「{word}」已存在,跳过")
            continue
        pairs.append((word, weight))
        existing_words.add(word)
        added.append(fmt_line(word, weight) if weight is not None else f"{word}(默认4)")
    if not added:
        print("没有新增词。")
        return
    if len(pairs) > MAX_TABLE_WORDS:
        sys.exit(f"加完共 {len(pairs)} 词,超过单表上限 {MAX_TABLE_WORDS}。")
    res = client.update_table(tid, build_content(pairs).encode("utf-8"))
    if res is None:
        return
    print(f"已加入 {len(added)} 词: {' '.join(added)}(表现共 {res.get('WordCount')} 词)")


def cmd_delete(client, args):
    tid = resolve_table(client, args.table or client.default_table)
    r = client.get_table(tid)
    if r is None:
        return
    pairs = _table_pairs(r)
    targets = {parse_line(t)[0] for t in args.words}
    kept = [(w, wt) for w, wt in pairs if w not in targets]
    removed = [w for w, _ in pairs if w in targets]
    if not removed:
        print("没有匹配到要删的词。")
        return
    res = client.update_table(tid, build_content(kept).encode("utf-8"))
    if res is None:
        return
    print(f"已删除 {len(removed)} 词: {' '.join(removed)}(表现共 {res.get('WordCount')} 词)")


def cmd_rm(client, args):
    tid = resolve_table(client, args.table or client.default_table)
    if not args.yes and not client.dry_run:
        ans = input(f"确认删除整张热词表 {args.table} (ID={tid})? [y/N] ")
        if ans.strip().lower() != "y":
            print("已取消。")
            return
    r = client.delete_table(tid)
    if r is None:
        return
    print(f"已删除热词表 {args.table} (ID={tid})。")


def cmd_limits(client, args):
    r = client.limits()
    if r is None:
        return
    print(f"表数: {r.get('CurTotalTableCount')}/{r.get('TotalTableCountLimit')}")
    print(f"总词数: {r.get('CurTotalSize')}/{r.get('TotalSizeLimit')}")
    print(f"单表词数上限: {r.get('SingleTableSizeLimit')}")
    print(f"单词长度上限: {r.get('SingleWordSizeLimitCN')} 汉字 / "
          f"{r.get('SingleWordSizeLimitBytes')} 字节")


def cmd_apps(client, args):
    r = client.list_apps()
    if r is None:
        return
    apps = r.get("applications", [])
    if not apps:
        print("(没有应用)")
        return
    for a in apps:
        print(f"  {a.get('name')}  appid={a.get('appid')}  "
              f"state={a.get('state')}")


def _find_table(client, name):
    """按名字查表,返回 ID 或 None(dry-run 时返回 None)。"""
    result = client.list_tables()
    if result is None:
        return None
    for t in result.get("BoostingTables", []):
        if t["BoostingTableName"] == name:
            return t["BoostingTableID"]
    return None


# --------------------------------------------------------------------------- 入口

def build_parser():
    p = argparse.ArgumentParser(
        prog="volcengine_hotword",
        description="火山引擎豆包语音 热词表管理 CLI",
    )
    p.add_argument("--config", default=DEFAULT_CONFIG, help="配置文件路径")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印将要发送的请求,不实际执行")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出所有热词表").set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="查看某表全部词")
    s.add_argument("table", nargs="?", default=None,
                   help="热词表 ID 或表名(默认 bpr-ai-vc)")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("upload", help="用 txt 建表 / 覆盖")
    s.add_argument("file", help="TXT 文件路径(每行一个词,可 词|权重)")
    s.add_argument("--name", required=True, help="热词表名")
    s.add_argument("--overwrite", action="store_true", help="同名则覆盖")
    s.set_defaults(func=cmd_upload)

    s = sub.add_parser("add", help="往表里加词")
    s.add_argument("-t", "--table", default=None,
                   help="热词表 ID 或表名(默认 bpr-ai-vc)")
    s.add_argument("words", nargs="+", help="要加的词(可 词|权重;不给权重则自动算)")
    s.add_argument("--weight", type=int, help="给新词统一权重 1-10(覆盖自动)")
    s.add_argument("--no-auto-weight", action="store_true",
                   help="裸词不自动算权重,用服务端默认 4")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("delete", help="从表里删词")
    s.add_argument("-t", "--table", default=None,
                   help="热词表 ID 或表名(默认 bpr-ai-vc)")
    s.add_argument("words", nargs="+", help="要删的词")
    s.set_defaults(func=cmd_delete)

    s = sub.add_parser("rm", help="删整张表")
    s.add_argument("table", help="热词表 ID 或表名")
    s.add_argument("-y", "--yes", action="store_true", help="跳过确认")
    s.set_defaults(func=cmd_rm)

    sub.add_parser("limits", help="查看配额").set_defaults(func=cmd_limits)
    sub.add_parser("apps", help="列出 AppID").set_defaults(func=cmd_apps)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    conf = load_config(args.config)
    conf["__path__"] = args.config
    client = HotwordClient(
        ak=require(conf, "VOLC_AK"),
        sk=require(conf, "VOLC_SK"),
        app_id=require(conf, "VOLC_APP_ID"),
        account_id=conf.get("VOLC_ACCOUNT_ID"),
        dry_run=args.dry_run,
        default_table=conf.get("VOLC_HOTWORD_TABLE") or "bpr-ai-vc",
        openai_key=conf.get("OPENAI_API_KEY"),
        weight_model=conf.get("VOLC_HOTWORD_WEIGHT_MODEL") or "gpt-5-mini",
    )
    try:
        args.func(client, args)
    except VolcError as e:
        sys.exit(f"接口报错 {e}")
    except ValueError as e:
        sys.exit(f"校验失败: {e}")
    except FileNotFoundError as e:
        sys.exit(f"文件不存在: {e.filename}")


if __name__ == "__main__":
    main()
