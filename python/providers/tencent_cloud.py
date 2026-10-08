"""Shared Tencent Cloud API transport.

Tencent ASR and SOE use the same TC3-HMAC-SHA256 transport. Keeping signing,
HTTP status handling, and Tencent's common ``Response.Error`` envelope here
prevents provider adapters from duplicating security-sensitive request code.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests


class TencentCloudError(Exception):
    """Raised when a Tencent Cloud HTTP or API request fails."""


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hmac(secret: bytes | str, message: bytes | str) -> bytes:
    secret_bytes = secret if isinstance(secret, bytes) else secret.encode("utf-8")
    message_bytes = message if isinstance(message, bytes) else message.encode("utf-8")
    return hmac.new(secret_bytes, message_bytes, hashlib.sha256).digest()


def tc3_authorization(
    *,
    secret_id: str,
    secret_key: str,
    region: str,
    service: str,
    host: str,
    payload: str,
    timestamp: int,
) -> str:
    """Build the Tencent Cloud v3 authorization header."""

    date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))
    signed_headers = "content-type;host"
    canonical_headers = "content-type:application/json; charset=utf-8\nhost:%s\n" % host
    canonical_request = "\n".join(
        ["POST", "/", "", canonical_headers, signed_headers, _hash(payload)]
    )
    credential_scope = f"{date}/{service}/tc3_request"
    string_to_sign = "\n".join(
        ["TC3-HMAC-SHA256", str(timestamp), credential_scope, _hash(canonical_request)]
    )
    secret_date = _hmac("TC3" + secret_key, date)
    secret_service = _hmac(secret_date, service)
    secret_signing = _hmac(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return (
        "TC3-HMAC-SHA256 "
        f"Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


@dataclass
class TencentCloudClient:
    """Small authenticated client shared by Tencent provider adapters."""

    secret_id: str
    secret_key: str
    region: str
    endpoint: str
    service: str
    version: str
    timeout: float

    def request(
        self,
        action: str,
        body: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if not self.secret_id or not self.secret_key:
            raise TencentCloudError(
                "TENCENT_SECRET_ID and TENCENT_SECRET_KEY are required."
            )

        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        parsed = urlparse(self.endpoint)
        if not parsed.netloc:
            raise TencentCloudError("Tencent Cloud endpoint must include a hostname.")
        host = parsed.netloc
        timestamp = int(time.time())
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Version": self.version,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Region": self.region,
            "Authorization": tc3_authorization(
                secret_id=self.secret_id,
                secret_key=self.secret_key,
                region=self.region,
                service=self.service,
                host=host,
                payload=payload,
                timestamp=timestamp,
            ),
        }

        try:
            response = requests.post(
                self.endpoint,
                headers=headers,
                data=payload,
                timeout=timeout or self.timeout,
            )
            response.raise_for_status()
            parsed_response = response.json()
        except requests.RequestException as exc:
            raise TencentCloudError(f"Tencent Cloud request failed: {exc}") from exc
        except ValueError as exc:
            raise TencentCloudError("Tencent Cloud returned invalid JSON.") from exc

        if not isinstance(parsed_response, dict):
            raise TencentCloudError("Tencent Cloud returned an invalid JSON object.")
        envelope = parsed_response.get("Response", parsed_response)
        api_error = envelope.get("Error") if isinstance(envelope, dict) else None
        if isinstance(api_error, dict):
            message = api_error.get("Message") or api_error.get("Code") or "unknown error"
            raise TencentCloudError(f"Tencent Cloud API error: {message}")
        return parsed_response
