#!/usr/bin/env python3
"""Package and deploy the Page 47 review runtime to Amazon Bedrock AgentCore."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, cast

import boto3
import yaml

from page47.snapshotter.config import JSONObject, JSONValue, as_json_value


class IdentityClient(Protocol):
    def get_caller_identity(self, **kwargs: object) -> object: ...


class StorageClient(Protocol):
    def head_bucket(self, **kwargs: object) -> object: ...

    def create_bucket(self, **kwargs: object) -> object: ...

    def upload_file(self, **kwargs: object) -> object: ...


class ParameterClient(Protocol):
    def get_parameter(self, **kwargs: object) -> object: ...

    def put_parameter(self, **kwargs: object) -> object: ...


class ControlClient(Protocol):
    def list_agent_runtimes(self, **kwargs: object) -> object: ...

    def create_agent_runtime(self, **kwargs: object) -> object: ...

    def update_agent_runtime(self, **kwargs: object) -> object: ...


class Session(Protocol):
    def client(self, service_name: str, *, region_name: str) -> object: ...


@dataclass(frozen=True, slots=True)
class DeploymentSettings:
    region: str
    runtime_name: str
    runtime: str
    entrypoint: tuple[str, ...]
    entrypoint_source: str
    protocol: str
    network_mode: str
    build_platform: str
    artifact_bucket_prefix: str
    artifact_prefix: str
    execution_role_parameter: str
    runtime_arn_parameter: str
    idle_session_timeout_seconds: int
    max_lifetime_seconds: int
    max_zip_megabytes: int
    max_unzipped_megabytes: int
    config_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuntimeSummary:
    runtime_id: str
    name: str
    arn: str | None


def _object(value: object, context: str) -> JSONObject:
    decoded = as_json_value(value)
    if not isinstance(decoded, dict):
        raise ValueError(f"{context} was not an object")
    return decoded


def _text(value: JSONObject, key: str, context: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{context}.{key} must be non-empty text")
    return item.strip()


def _runtime_name(value: JSONObject, key: str, context: str) -> str:
    name = _text(value, key, context)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,47}", name) is None:
        raise ValueError(
            f"{context}.{key} must start with a letter and contain only letters, numbers, "
            "and underscores"
        )
    return name


def _integer(value: JSONObject, key: str, context: str, minimum: int) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int) or item < minimum:
        raise ValueError(f"{context}.{key} must be an integer of at least {minimum}")
    return item


def _text_list(value: JSONObject, key: str, context: str) -> tuple[str, ...]:
    item = value.get(key)
    if not isinstance(item, list) or not item:
        raise ValueError(f"{context}.{key} must be a non-empty list")
    output: list[str] = []
    for index, entry in enumerate(item):
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError(f"{context}.{key}[{index}] must be non-empty text")
        output.append(entry.strip())
    return tuple(output)


def load_deployment_settings(path: Path) -> DeploymentSettings:
    decoded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = _object(decoded, "AgentCore configuration")
    runtime = _object(root.get("runtime"), "runtime")
    invocation = _object(runtime.get("invocation"), "runtime.invocation")
    deployment = _object(runtime.get("deployment"), "runtime.deployment")
    return DeploymentSettings(
        region=_text(invocation, "region", "runtime.invocation"),
        runtime_name=_runtime_name(deployment, "name", "runtime.deployment"),
        runtime=_text(deployment, "runtime", "runtime.deployment"),
        entrypoint=_text_list(deployment, "entrypoint", "runtime.deployment"),
        entrypoint_source=_text(deployment, "entrypoint_source", "runtime.deployment"),
        protocol=_text(deployment, "protocol", "runtime.deployment"),
        network_mode=_text(deployment, "network_mode", "runtime.deployment"),
        build_platform=_text(deployment, "build_platform", "runtime.deployment"),
        artifact_bucket_prefix=_text(
            deployment, "artifact_bucket_prefix", "runtime.deployment"
        ),
        artifact_prefix=_text(deployment, "artifact_prefix", "runtime.deployment"),
        execution_role_parameter=_text(
            deployment, "execution_role_parameter", "runtime.deployment"
        ),
        runtime_arn_parameter=_text(
            invocation, "runtime_arn_parameter", "runtime.invocation"
        ),
        idle_session_timeout_seconds=_integer(
            deployment,
            "idle_session_timeout_seconds",
            "runtime.deployment",
            1,
        ),
        max_lifetime_seconds=_integer(
            deployment, "max_lifetime_seconds", "runtime.deployment", 1
        ),
        max_zip_megabytes=_integer(deployment, "max_zip_megabytes", "runtime.deployment", 1),
        max_unzipped_megabytes=_integer(
            deployment, "max_unzipped_megabytes", "runtime.deployment", 1
        ),
        config_files=_text_list(deployment, "config_files", "runtime.deployment"),
    )


def _python_version(runtime: str) -> str:
    if not runtime.startswith("PYTHON_3_"):
        raise ValueError(f"Unsupported AgentCore Python runtime name: {runtime}")
    return runtime.removeprefix("PYTHON_").replace("_", ".")


def _copy_without_cache(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Package source directory was not found: {source}")
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def _install_dependencies(
    project_root: Path,
    package_root: Path,
    settings: DeploymentSettings,
) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError(
            "uv is required to build Linux arm64 AgentCore dependencies; install uv and retry"
        )
    command = [
        uv,
        "pip",
        "install",
        f"--python-platform={settings.build_platform}",
        f"--python-version={_python_version(settings.runtime)}",
        f"--target={package_root}",
        "--only-binary=:all:",
        "-r",
        str(project_root / "pyproject.toml"),
    ]
    subprocess.run(command, cwd=project_root, check=True)


def _archive(package_root: Path, archive_path: Path) -> tuple[str, int]:
    total_bytes = 0
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package_root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Symlinks are not allowed in the AgentCore package: {path}")
            if path.is_dir():
                continue
            relative = path.relative_to(package_root).as_posix()
            content = path.read_bytes()
            total_bytes += len(content)
            info = zipfile.ZipInfo(relative)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = stat.S_IMODE(path.stat().st_mode)
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, content)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    return digest, total_bytes


def build_package(
    project_root: Path,
    config_path: Path,
    settings: DeploymentSettings,
    output_path: Path,
) -> tuple[str, int, int]:
    with tempfile.TemporaryDirectory(prefix="page47-agentcore-") as temporary:
        package_root = Path(temporary) / "package"
        package_root.mkdir()
        _install_dependencies(project_root, package_root, settings)
        _copy_without_cache(project_root / "src" / "page47", package_root / "page47")

        entrypoint_source = project_root / settings.entrypoint_source
        if len(settings.entrypoint) != 1:
            raise ValueError("This package builder requires exactly one Python entrypoint")
        entrypoint = package_root / settings.entrypoint[0]
        if entrypoint_source.suffix != ".py":
            raise ValueError("AgentCore entrypoint source must be a Python file")
        entrypoint.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entrypoint_source, entrypoint)

        config_root = package_root / "config"
        config_root.mkdir()
        source_config_root = config_path.parent
        for name in settings.config_files:
            source = source_config_root / name
            if not source.is_file():
                raise FileNotFoundError(f"Configured AgentCore file was not found: {source}")
            shutil.copy2(source, config_root / name)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        digest, unzipped_bytes = _archive(package_root, output_path)
    zipped_bytes = output_path.stat().st_size
    if zipped_bytes > settings.max_zip_megabytes * 1024 * 1024:
        raise ValueError(
            f"AgentCore package is {zipped_bytes} bytes, above the configured zip limit"
        )
    if unzipped_bytes > settings.max_unzipped_megabytes * 1024 * 1024:
        raise ValueError(
            f"AgentCore package expands to {unzipped_bytes} bytes, above the configured limit"
        )
    return digest, zipped_bytes, unzipped_bytes


def _json_value(value: object) -> JSONValue:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        output: JSONObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("AWS response key was not text")
            output[key] = _json_value(item)
        return output
    raise ValueError(f"Unsupported AWS response value: {type(value).__name__}")


def _response(value: object, context: str) -> JSONObject:
    decoded = _json_value(value)
    if not isinstance(decoded, dict):
        raise ValueError(f"AWS {context} response was not an object")
    return decoded


def _required_text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"AWS response {context} was not non-empty text")
    return value.strip()


def _error_code(error: Exception) -> str | None:
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return None
    error_value = response.get("Error")
    if not isinstance(error_value, dict):
        return None
    code = error_value.get("Code")
    return code if isinstance(code, str) else None


def _account_id(identity: IdentityClient) -> str:
    response = _response(identity.get_caller_identity(), "STS")
    account = _required_text(response.get("Account"), "STS.Account")
    if len(account) != 12 or not account.isdigit():
        raise ValueError("STS returned an invalid account ID")
    return account


def _parameter_value(client: ParameterClient, name: str) -> str:
    response = _response(
        client.get_parameter(Name=name, WithDecryption=True),
        f"SSM parameter {name}",
    )
    parameter = _response(response.get("Parameter"), f"SSM parameter {name}.Parameter")
    return _required_text(parameter.get("Value"), f"SSM parameter {name}.Value")


def _ensure_bucket(
    storage: StorageClient,
    bucket: str,
    region: str,
    account_id: str,
) -> None:
    try:
        storage.head_bucket(Bucket=bucket, ExpectedBucketOwner=account_id)
        return
    except Exception as error:
        if _error_code(error) not in {"404", "NoSuchBucket", "NotFound"}:
            raise
    arguments: dict[str, object] = {"Bucket": bucket}
    if region != "us-east-1":
        arguments["CreateBucketConfiguration"] = {"LocationConstraint": region}
    storage.create_bucket(**arguments)


def _runtime_summaries(control: ControlClient) -> list[RuntimeSummary]:
    output: list[RuntimeSummary] = []
    next_token: str | None = None
    while True:
        arguments: dict[str, object] = {}
        if next_token is not None:
            arguments["nextToken"] = next_token
        response = _response(control.list_agent_runtimes(**arguments), "AgentCore list")
        raw_items = response.get("agentRuntimes")
        if not isinstance(raw_items, list):
            raise ValueError("AgentCore list response did not contain agentRuntimes")
        for index, raw_item in enumerate(raw_items):
            item = _response(raw_item, f"AgentCore list agentRuntimes[{index}]")
            runtime_id = _required_text(
                item.get("agentRuntimeId"),
                f"AgentCore list agentRuntimes[{index}].agentRuntimeId",
            )
            name = _required_text(
                item.get("agentRuntimeName"),
                f"AgentCore list agentRuntimes[{index}].agentRuntimeName",
            )
            raw_arn = item.get("agentRuntimeArn")
            arn = raw_arn.strip() if isinstance(raw_arn, str) and raw_arn.strip() else None
            output.append(RuntimeSummary(runtime_id=runtime_id, name=name, arn=arn))
        raw_next_token = response.get("nextToken")
        if raw_next_token is None:
            break
        next_token = _required_text(raw_next_token, "AgentCore list nextToken")
    return output


def _artifact(bucket: str, key: str, settings: DeploymentSettings) -> JSONObject:
    return {
        "codeConfiguration": {
            "code": {"s3": {"bucket": bucket, "prefix": key}},
            "runtime": settings.runtime,
            "entryPoint": list(settings.entrypoint),
        }
    }


def _runtime_arguments(
    bucket: str,
    key: str,
    role_arn: str,
    settings: DeploymentSettings,
) -> JSONObject:
    return {
        "agentRuntimeArtifact": _artifact(bucket, key, settings),
        "roleArn": role_arn,
        # Existing runtimes may default to the shared spans destination. Keep
        # the runtime's OTEL spans with its own CloudWatch runtime log group.
        "environmentVariables": {
            "UNIFIED_TRACES_DESTINATION_ENABLED": "true",
        },
        "networkConfiguration": {"networkMode": settings.network_mode},
        "protocolConfiguration": {"serverProtocol": settings.protocol},
        "lifecycleConfiguration": {
            "idleRuntimeSessionTimeout": settings.idle_session_timeout_seconds,
            "maxLifetime": settings.max_lifetime_seconds,
        },
        "description": "Page 47 public-record review runtime",
    }


def _client_token() -> str:
    """Return a client token that meets the AgentCore API length constraint."""
    return f"page47-{uuid.uuid4().hex}"


def deploy(
    project_root: Path,
    config_path: Path,
    settings: DeploymentSettings,
    archive_path: Path,
) -> JSONObject:
    session = cast(Session, boto3.Session())
    identity = cast(IdentityClient, session.client("sts", region_name=settings.region))
    storage = cast(StorageClient, session.client("s3", region_name=settings.region))
    parameters = cast(ParameterClient, session.client("ssm", region_name=settings.region))
    control = cast(
        ControlClient,
        session.client("bedrock-agentcore-control", region_name=settings.region),
    )
    account_id = _account_id(identity)
    role_arn = _parameter_value(parameters, settings.execution_role_parameter)
    bucket = f"{settings.artifact_bucket_prefix}-{account_id}-{settings.region}"
    key = f"{settings.artifact_prefix}/{archive_path.name}"
    _ensure_bucket(storage, bucket, settings.region, account_id)
    storage.upload_file(
        Filename=str(archive_path),
        Bucket=bucket,
        Key=key,
        ExtraArgs={"ExpectedBucketOwner": account_id, "ContentType": "application/zip"},
    )
    matches = [item for item in _runtime_summaries(control) if item.name == settings.runtime_name]
    if len(matches) > 1:
        raise RuntimeError(f"More than one AgentCore runtime is named {settings.runtime_name}")
    arguments = _runtime_arguments(bucket, key, role_arn, settings)
    if matches:
        existing = matches[0]
        response = _response(
            control.update_agent_runtime(agentRuntimeId=existing.runtime_id, **arguments),
            "AgentCore update",
        )
        action = "updated"
    else:
        response = _response(
            control.create_agent_runtime(
                agentRuntimeName=settings.runtime_name,
                clientToken=_client_token(),
                **arguments,
            ),
            "AgentCore create",
        )
        action = "created"
    runtime_arn = _required_text(response.get("agentRuntimeArn"), "AgentCore runtime ARN")
    parameters.put_parameter(
        Name=settings.runtime_arn_parameter,
        Value=runtime_arn,
        Type="String",
        Overwrite=True,
        Description="Page 47 AgentCore review runtime ARN",
    )
    return {
        "action": action,
        "runtime_name": settings.runtime_name,
        "runtime_arn": runtime_arn,
        "artifact": f"s3://{bucket}/{key}",
        "package_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "region": settings.region,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy Page 47 to AgentCore")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--config", type=Path, default=Path("config/agentcore.yaml"))
    parser.add_argument("--output", type=Path, default=Path("runtime/agentcore-deployment.zip"))
    parser.add_argument("--deploy", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    config_path = (project_root / args.config).resolve()
    settings = load_deployment_settings(config_path)
    digest, zipped_bytes, unzipped_bytes = build_package(
        project_root,
        config_path,
        settings,
        (project_root / args.output).resolve(),
    )
    result: JSONObject = {
        "package": str((project_root / args.output).resolve()),
        "package_sha256": digest,
        "zipped_bytes": zipped_bytes,
        "unzipped_bytes": unzipped_bytes,
        "deployed": False,
    }
    if args.deploy:
        result.update(
            deploy(
                project_root,
                config_path,
                settings,
                (project_root / args.output).resolve(),
            )
        )
        result["deployed"] = True
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
