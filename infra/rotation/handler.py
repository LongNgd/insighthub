"""Secrets Manager four-step rotation for an ElastiCache Redis AUTH token.

The service accepts two tokens during ROTATE. Old clients continue to work
while the EKS runtime Secret and workloads are refreshed.
"""

import os
import socket
import ssl
import time
from typing import Any

import boto3


def _redis_ping(host: str, token: str) -> bool:
    """Return False only for an AUTH rejection; fail on transport errors."""
    with socket.create_connection((host, 6379), timeout=5) as raw:
        with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as conn:
            conn.settimeout(5)
            with conn.makefile("rb") as response:
                encoded = token.encode("utf-8")
                conn.sendall(
                    b"*2\r\n$4\r\nAUTH\r\n$"
                    + str(len(encoded)).encode("ascii")
                    + b"\r\n"
                    + encoded
                    + b"\r\n"
                )
                auth_reply = response.readline()
                if auth_reply.startswith((b"-WRONGPASS", b"-NOAUTH")):
                    return False
                if auth_reply != b"+OK\r\n":
                    raise RuntimeError("Unexpected Redis AUTH response")
                conn.sendall(b"*1\r\n$4\r\nPING\r\n")
                if response.readline() != b"+PONG\r\n":
                    raise RuntimeError("Redis PING did not succeed")
    return True


def _secret_value(client: Any, secret_id: str, *, version: str | None = None) -> str:
    request: dict[str, str] = {"SecretId": secret_id}
    if version is None:
        request["VersionStage"] = "AWSCURRENT"
    else:
        request["VersionId"] = version
        request["VersionStage"] = "AWSPENDING"
    return client.get_secret_value(**request)["SecretString"]


def _create_secret(client: Any, secret_id: str, token: str) -> None:
    try:
        _secret_value(client, secret_id, version=token)
        return
    except client.exceptions.ResourceNotFoundException:
        pass

    password = client.get_random_password(
        PasswordLength=40, ExcludePunctuation=True
    )["RandomPassword"]
    client.put_secret_value(
        SecretId=secret_id,
        ClientRequestToken=token,
        SecretString=password,
        VersionStages=["AWSPENDING"],
    )


def _wait_for_available(client: Any, group_id: str, deadline: float) -> None:
    while time.monotonic() < deadline:
        groups = client.describe_replication_groups(
            ReplicationGroupId=group_id
        )["ReplicationGroups"]
        if len(groups) != 1:
            raise RuntimeError("Expected one Redis replication group")
        if groups[0]["Status"] == "available":
            return
        time.sleep(5)
    raise TimeoutError("Redis modification did not become available")


def _set_secret(
    secrets: Any, cache: Any, secret_id: str, token: str, host: str, group_id: str
) -> None:
    pending = _secret_value(secrets, secret_id, version=token)
    if _redis_ping(host, pending):
        return
    current = _secret_value(secrets, secret_id)
    if not _redis_ping(host, current):
        raise RuntimeError("Current Redis credential failed before rotation")
    cache.modify_replication_group(
        ReplicationGroupId=group_id,
        AuthToken=pending,
        AuthTokenUpdateStrategy="ROTATE",
        ApplyImmediately=True,
    )
    _wait_for_available(cache, group_id, time.monotonic() + 140)
    if not _redis_ping(host, pending):
        raise RuntimeError("Pending Redis credential failed after rotation")


def _finish_secret(client: Any, secret_id: str, token: str) -> None:
    versions = client.describe_secret(SecretId=secret_id)["VersionIdsToStages"]
    current = next(
        (version for version, stages in versions.items() if "AWSCURRENT" in stages),
        None,
    )
    if current == token:
        return
    if current is None:
        raise RuntimeError("Secret has no AWSCURRENT version")
    client.update_secret_version_stage(
        SecretId=secret_id,
        VersionStage="AWSCURRENT",
        MoveToVersionId=token,
        RemoveFromVersionId=current,
    )


def lambda_handler(event: dict[str, str], _context: Any) -> None:
    """Handle one Secrets Manager rotation step without logging credentials."""
    secret_id = event["SecretId"]
    token = event["ClientRequestToken"]
    step = event["Step"]
    if secret_id != os.environ["SECRET_ARN"]:
        raise ValueError("Unexpected secret ARN")
    if step not in {"createSecret", "setSecret", "testSecret", "finishSecret"}:
        raise ValueError("Unexpected rotation step")

    secrets = boto3.client("secretsmanager")
    stages = secrets.describe_secret(SecretId=secret_id)["VersionIdsToStages"].get(
        token, []
    )
    if "AWSCURRENT" in stages:
        return
    if step != "createSecret" and "AWSPENDING" not in stages:
        raise ValueError("Rotation version is not AWSPENDING")

    if step == "createSecret":
        _create_secret(secrets, secret_id, token)
    elif step == "setSecret":
        _set_secret(
            secrets,
            boto3.client("elasticache"),
            secret_id,
            token,
            os.environ["REDIS_HOST"],
            os.environ["REDIS_REPLICATION_GROUP"],
        )
    elif step == "testSecret":
        if not _redis_ping(
            os.environ["REDIS_HOST"], _secret_value(secrets, secret_id, version=token)
        ):
            raise RuntimeError("Pending Redis credential did not authenticate")
    else:
        if not _redis_ping(
            os.environ["REDIS_HOST"], _secret_value(secrets, secret_id, version=token)
        ):
            raise RuntimeError("Cannot promote an unverified Redis credential")
        _finish_secret(secrets, secret_id, token)
