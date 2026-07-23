"""火山引擎 OpenAPI 签名 (HMAC-SHA256) + 已签名请求发送。

实现遵循火山引擎签名规范 (https://www.volcengine.com/docs/6369/67268):
标准 V4 风格签名,X-Content-Sha256 头 = 请求体 sha256,并作为签名头之一。
热词管理 API 固定使用:
  域名   open.volcengineapi.com
  Region cn-north-1
  Service speech_saas_prod
"""
import datetime
import hashlib
import hmac
import json
import urllib.parse
import uuid

import requests

DOMAIN = "open.volcengineapi.com"
REGION = "cn-north-1"
SERVICE = "speech_saas_prod"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(sk: str, short_date: str) -> bytes:
    k = _hmac(sk.encode("utf-8"), short_date)
    k = _hmac(k, REGION)
    k = _hmac(k, SERVICE)
    return _hmac(k, "request")


def _canonical_query(params: dict) -> str:
    return urllib.parse.urlencode(sorted(params.items()))


def _signed_headers(method: str, query: str, body: bytes, content_type: str,
                    ak: str, sk: str) -> dict:
    """严格复刻火山官方示例(docs 6561/1742791)的签名方式:
    canonical headers 里 x-content-sha256 留空值,且不发送该请求头;
    真实 body hash 只作为 canonical request 的最后一行 (hashed payload)。
    """
    x_date = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    short_date = x_date[:8]
    payload_hash = _sha256_hex(body)
    credential_scope = f"{short_date}/{REGION}/{SERVICE}/request"
    signed_headers = "content-type;host;x-content-sha256;x-date"
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{DOMAIN}\n"
        f"x-content-sha256:\n"
        f"x-date:{x_date}\n"
    )
    canonical_request = (
        f"{method}\n/\n{query}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    string_to_sign = (
        f"HMAC-SHA256\n{x_date}\n{credential_scope}\n"
        f"{_sha256_hex(canonical_request.encode('utf-8'))}"
    )
    signature = hmac.new(
        _signing_key(sk, short_date), string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    authorization = (
        f"HMAC-SHA256 Credential={ak}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Content-Type": content_type,
        "X-Date": x_date,
        "Authorization": authorization,
    }


def call_json(action: str, version: str, ak: str, sk: str,
              body_params: dict = None, query_extra: dict = None,
              method: str = "POST", dry_run: bool = False):
    """调用 JSON 类接口 (list / get / delete / limits / apps)。"""
    query_params = {"Action": action, "Version": version}
    if query_extra:
        query_params.update(query_extra)
    query = _canonical_query(query_params)
    content_type = "application/json; charset=utf-8"
    body = b"" if method == "GET" else json.dumps(body_params or {}).encode("utf-8")
    headers = _signed_headers(method, query, body, content_type, ak, sk)
    url = f"https://{DOMAIN}/?{query}"
    if dry_run:
        return {"dry_run": True, "method": method, "url": url,
                "body": body.decode("utf-8") if body else ""}
    if method == "GET":
        return requests.get(url, headers=headers, timeout=30)
    return requests.post(url, headers=headers, data=body, timeout=30)


def _build_multipart(fields: dict, file_field: str, filename: str,
                     file_bytes: bytes, boundary: str) -> bytes:
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(b"")
        parts.append(str(value).encode("utf-8"))
    parts.append(f"--{boundary}".encode())
    parts.append(
        f'Content-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"'.encode()
    )
    parts.append(b"Content-Type: text/plain; charset=utf-8")
    parts.append(b"")
    parts.append(file_bytes)
    parts.append(f"--{boundary}--".encode())
    parts.append(b"")
    return b"\r\n".join(parts)


def call_multipart(action: str, version: str, ak: str, sk: str,
                   fields: dict, file_bytes: bytes, filename: str = "hotword.txt",
                   dry_run: bool = False):
    """调用 multipart 类接口 (create / update — 需上传 txt 文件)。"""
    query = _canonical_query({"Action": action, "Version": version})
    boundary = "----volchotword" + uuid.uuid4().hex
    body = _build_multipart(fields, "File", filename, file_bytes, boundary)
    content_type = f"multipart/form-data; boundary={boundary}"
    headers = _signed_headers("POST", query, body, content_type, ak, sk)
    url = f"https://{DOMAIN}/?{query}"
    if dry_run:
        return {"dry_run": True, "method": "POST", "url": url,
                "fields": fields, "file_bytes": len(file_bytes)}
    return requests.post(url, headers=headers, data=body, timeout=60)
