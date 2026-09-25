"""Contract tests for the four Redis AUTH rotation steps without AWS access."""

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class FakeSecrets:
    class exceptions:
        class ResourceNotFoundException(Exception):
            pass

    def __init__(self):
        self.values = {"initial": "current-token"}
        self.stages = {"initial": ["AWSCURRENT"]}

    def describe_secret(self, **_kwargs):
        return {"VersionIdsToStages": self.stages}

    def get_secret_value(self, **kwargs):
        version = kwargs.get("VersionId", "initial")
        if version not in self.values:
            raise self.exceptions.ResourceNotFoundException()
        if kwargs.get("VersionStage") not in self.stages[version]:
            raise self.exceptions.ResourceNotFoundException()
        return {"SecretString": self.values[version]}

    def get_random_password(self, **_kwargs):
        return {"RandomPassword": "pending-token"}

    def put_secret_value(self, **kwargs):
        token = kwargs["ClientRequestToken"]
        self.values[token] = kwargs["SecretString"]
        self.stages[token] = kwargs["VersionStages"]

    def update_secret_version_stage(self, **kwargs):
        self.stages[kwargs["RemoveFromVersionId"]].remove("AWSCURRENT")
        self.stages[kwargs["MoveToVersionId"]] = ["AWSCURRENT"]


class FakeCache:
    def __init__(self):
        self.valid_tokens = {"current-token"}
        self.modifications = 0

    def modify_replication_group(self, **kwargs):
        assert kwargs["AuthTokenUpdateStrategy"] == "ROTATE"
        self.valid_tokens.add(kwargs["AuthToken"])
        self.modifications += 1

    def describe_replication_groups(self, **_kwargs):
        return {"ReplicationGroups": [{"Status": "available"}]}


def load_handler():
    boto3 = types.ModuleType("boto3")
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = Exception
    botocore.exceptions = exceptions
    source = Path(__file__).resolve().parents[1] / "infra" / "rotation" / "handler.py"
    spec = importlib.util.spec_from_file_location("redis_rotation_handler", source)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {"boto3": boto3, "botocore": botocore, "botocore.exceptions": exceptions},
    ):
        spec.loader.exec_module(module)
    return module


class RedisRotationTests(unittest.TestCase):
    def setUp(self):
        self.handler = load_handler()
        self.secrets = FakeSecrets()
        self.cache = FakeCache()
        self.handler.boto3.client = lambda service: {
            "secretsmanager": self.secrets,
            "elasticache": self.cache,
        }[service]
        self.handler._redis_ping = (
            lambda _host, token: token in self.cache.valid_tokens
        )
        self.env = patch.dict(
            os.environ,
            {
                "SECRET_ARN": "arn:example:redis",
                "REDIS_HOST": "redis.example",
                "REDIS_REPLICATION_GROUP": "insighthub-prod-redis",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def event(self, step):
        return {
            "SecretId": "arn:example:redis",
            "ClientRequestToken": "next",
            "Step": step,
        }

    def test_four_steps_are_idempotent(self):
        for step in ("createSecret", "setSecret", "testSecret", "finishSecret"):
            self.handler.lambda_handler(self.event(step), None)
            self.handler.lambda_handler(self.event(step), None)
        self.assertEqual(self.cache.modifications, 1)
        self.assertEqual(self.secrets.stages["next"], ["AWSCURRENT"])
        self.assertEqual(self.secrets.stages["initial"], [])

    def test_rejects_unexpected_secret(self):
        event = self.event("createSecret")
        event["SecretId"] = "arn:example:other"
        with self.assertRaises(ValueError):
            self.handler.lambda_handler(event, None)

    def test_does_not_promote_unverified_token(self):
        self.handler.lambda_handler(self.event("createSecret"), None)
        with self.assertRaisesRegex(RuntimeError, "unverified"):
            self.handler.lambda_handler(self.event("finishSecret"), None)
        self.assertEqual(self.secrets.stages["initial"], ["AWSCURRENT"])


if __name__ == "__main__":
    unittest.main()
