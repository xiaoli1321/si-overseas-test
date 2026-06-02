from functools import lru_cache
import os
from typing import Any, Dict, Tuple, Type

import jinja2
import yaml

from pydantic import model_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    PydanticBaseSettingsSource,
)

from src.core.utils import resolve_path


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """
    Custom settings source to load from config.yaml and map
    nested configuration keys to flat Pydantic Settings fields.
    """

    def get_field_value(self, field, field_name: str) -> Tuple[Any, str, bool]:
        # We override __call__ directly, so this isn't used
        return None, field_name, False

    def __call__(self) -> Dict[str, Any]:
        config_path = os.environ.get("CONFIG_FILE", "config.yaml")

        # Try both direct path and prefixed with backend/
        possible_paths = [config_path, os.path.join("backend", config_path)]

        yaml_data = {}
        for p in possible_paths:
            if os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        yaml_data = yaml.safe_load(f) or {}
                    break
                except Exception:
                    pass

        flat: Dict[str, Any] = {}
        if not isinstance(yaml_data, dict):
            return flat

        # Map nested app keys
        app = yaml_data.get("app", {})
        if isinstance(app, dict):
            for k in (
                "log_level",
                "upload_dir",
                "cors_origins",
                "database_url",
                "auto_create_tables",
                "file_storage_backend",
            ):
                if k in app:
                    flat[k] = app[k]

        storage = yaml_data.get("storage", {})
        if isinstance(storage, dict):
            for k in (
                "file_storage_backend",
                "oss_endpoint",
                "oss_bucket",
                "oss_access_key_id",
                "oss_access_key_secret",
                "oss_key_prefix",
                "oss_public_base_url",
                "oss_use_signed_url",
                "oss_signed_url_expire_seconds",
            ):
                if k in storage:
                    val = storage[k]
                    if (
                        isinstance(val, str)
                        and val.startswith("${")
                        and val.endswith("}")
                    ):
                        env_key = val[2:-1]
                        env_val = os.environ.get(env_key)
                        if env_val:
                            val = env_val
                        else:
                            continue
                    flat[k] = val

        # Map nested security keys
        security = yaml_data.get("security", {})
        if isinstance(security, dict):
            for k in ("jwt_secret_key", "jwt_algorithm", "access_token_expire_minutes"):
                if k in security:
                    flat[k] = security[k]

        # Map nested seeding keys
        seeding = yaml_data.get("seeding", {})
        if isinstance(seeding, dict):
            for k in ("seed_user_email", "seed_user_password"):
                if k in seeding:
                    flat[k] = seeding[k]

        # Map nested device keys
        device = yaml_data.get("device", {})
        if isinstance(device, dict):
            for k in ("default_device_type", "sn_regex_pattern"):
                if k in device:
                    flat[k] = device[k]

        # Map nested agent keys
        agent = yaml_data.get("agent", {})
        if isinstance(agent, dict):
            if "system_prompt_path" in agent:
                flat["agent_system_prompt_path"] = agent["system_prompt_path"]
            if "keywords" in agent:
                flat["agent_keywords"] = agent["keywords"]
            if "unrelated_card_prompt_turns" in agent:
                flat["agent_unrelated_card_prompt_turns"] = agent[
                    "unrelated_card_prompt_turns"
                ]

        # Map nested vlm keys
        vlm = yaml_data.get("vlm", {})
        if isinstance(vlm, dict):
            for k in (
                "dashscope_api_key",
                "vlm_base_url",
                "vlm_enabled",
                "vlm_max_retries",
                "intent_model",
                "vlm_model",
            ):
                if k in vlm:
                    flat[k] = vlm[k]
            if "prompt_version" in vlm:
                flat["vlm_prompt_version"] = vlm["prompt_version"]
            if "system_prompt_glucose_path" in vlm:
                flat["vlm_system_prompt_glucose_path"] = vlm[
                    "system_prompt_glucose_path"
                ]

        # Map nested thresholds keys
        thresholds = yaml_data.get("thresholds", {})
        if isinstance(thresholds, dict):
            for k in ("data_accuracy_abs_threshold",):
                if k in thresholds:
                    flat[k] = thresholds[k]
            if "default_profile" in thresholds:
                flat["default_threshold_profile"] = thresholds["default_profile"]

        verdict_presentation = yaml_data.get("verdict_presentation", {})
        if isinstance(verdict_presentation, dict):
            flat["verdict_presentation"] = verdict_presentation

        # Map nested overseas_api keys (resolve ${ENV_VAR} references)
        overseas_api = yaml_data.get("overseas_api", {})
        if isinstance(overseas_api, dict):
            for k in (
                "enabled",
                "login_url",
                "base_url",
                "device_detail_path",
                "username",
                "password",
                "request_timeout_seconds",
                "search_concurrency",
                "cache_ttl_seconds",
                "negative_cache_ttl_seconds",
            ):
                if k in overseas_api:
                    val = overseas_api[k]
                    # Resolve ${ENV_VAR} references from environment
                    if (
                        isinstance(val, str)
                        and val.startswith("${")
                        and val.endswith("}")
                    ):
                        env_key = val[2:-1]
                        env_val = os.environ.get(env_key)
                        if env_val:
                            val = env_val
                        else:
                            continue  # Skip unresolved env vars, let .env / defaults handle it
                    flat[f"overseas_api_{k}"] = val

        return flat


class Settings(BaseSettings):
    # Base Infrastructure
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/cgm_agent"
    )
    db_schema: str = "public"
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8
    auto_create_tables: bool = False
    batch_max_serials: int = 50
    batch_concurrency: int = 5
    task_stale_minutes: int = 30
    log_level: str = "INFO"
    upload_dir: str = "uploads"
    cors_origins: list[str] = ["*"]

    # File Storage
    file_storage_backend: str = "local"
    oss_endpoint: str = ""
    oss_bucket: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_key_prefix: str = "si-overseas"
    oss_public_base_url: str = ""
    oss_use_signed_url: bool = True
    oss_signed_url_expire_seconds: int = 600

    # Seeding
    seed_user_email: str = "christest@sibionics.com"
    seed_user_password: str = "password123"

    # Device
    default_device_type: str = "GS1"
    sn_regex_pattern: str = r"[A-Z0-9]{10,20}"

    # AI Agent Classifier
    agent_system_prompt_path: str = "prompts/agent/agent_system_prompt.jinja2"
    agent_system_prompt: str = ""
    agent_keywords: dict[str, str] = {}
    agent_unrelated_card_prompt_turns: int = 3

    # VLM Integration
    dashscope_api_key: str = ""
    vlm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    intent_model: str = "qwen-plus"
    vlm_model: str = "qwen-vl-max"
    vlm_enabled: bool = True
    vlm_max_retries: int = 2
    vlm_prompt_version: str = "application-failure-v1"
    vlm_system_prompt_glucose_path: str = (
        "prompts/scanner/vlm_system_prompt_glucose.jinja2"
    )
    vlm_system_prompt_glucose: str = ""

    # Thresholds
    data_accuracy_abs_threshold: float = 0.83
    default_threshold_profile: dict[str, Any] = {}
    verdict_presentation: dict[str, Any] = {}
    verdict_presentation_enabled: bool = True
    verdict_presentation_template_version: str = "standard-cases-v1"

    # Overseas API
    # 默认值为空，实际值通过 .env 或部署平台环境变量注入
    # PRE 测试环境: 在 .env 中配置
    # 生产环境: 通过 K8s Secrets / CI 环境变量 / 云平台配置中心注入
    overseas_api_enabled: bool = True
    overseas_api_login_url: str = ""
    overseas_api_base_url: str = ""
    overseas_api_device_detail_path: str = "/system/expand/oversea/deviceDetail"
    overseas_api_username: str = ""
    overseas_api_password: str = ""
    overseas_api_request_timeout_seconds: float = 15.0
    overseas_api_search_concurrency: int = 5
    overseas_api_cache_ttl_seconds: int = 300
    overseas_api_negative_cache_ttl_seconds: int = 60

    # Scanner
    scanner_templates_dir: str = "prompts/scanner"
    scanner_ref_dir: str = "prompts/scanner/reference"

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"), env_file_encoding="utf-8", extra="ignore"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
        )

    @model_validator(mode="after")
    def load_prompts_and_fallbacks(self) -> "Settings":
        def render_prompt(path: str, default: str, **variables: Any) -> str:
            resolved = resolve_path(path)
            if resolved:
                try:
                    env = jinja2.Environment(
                        loader=jinja2.FileSystemLoader(os.path.dirname(resolved))
                    )
                    template = env.get_template(os.path.basename(resolved))
                    return template.render(**variables).strip()
                except Exception:
                    pass
            return default

        # Defaults for prompt templates (rendered output equivalent)
        default_agent_prompt = (
            "You are a professional quality assurance assistant for Continuous Glucose Monitoring (CGM) devices.\n"
            "Classify the user's issue description into one of the following categories:\n"
            '- "Data accuracy"\n'
            '- "Sensor falling off"\n'
            '- "Sensor Abnormal"\n'
            '- "Application failure"\n'
            '- "other_cgm"\n'
            '- "unrelated"\n\n'
            'Your output must be a valid JSON object containing only the key "fault_category":\n'
            '- "fault_category": Data accuracy | Sensor falling off | Sensor Abnormal | Application failure | other_cgm | unrelated'
        )

        # Load prompts using Jinja2 rendering with variables
        if not self.agent_system_prompt:
            self.agent_system_prompt = render_prompt(
                self.agent_system_prompt_path,
                default_agent_prompt,
                categories=[
                    "Data accuracy",
                    "Sensor falling off",
                    "Sensor Abnormal",
                    "Application failure",
                    "other_cgm",
                    "unrelated",
                ],
            )
        if not self.vlm_system_prompt_glucose:
            self.vlm_system_prompt_glucose = render_prompt(
                self.vlm_system_prompt_glucose_path,
                "Analyze the uploaded images of CGM and BGM glucose readings. "
                "Return a JSON object with glucose_readings array.",
                image_count=4,
                device_types=["CGM", "BGM"],
            )

        # Load keywords if empty
        if not self.agent_keywords:
            self.agent_keywords = {
                "Application failure": "assembly needle launch electrode applicator insert photo",
                "Sensor falling off": "fall off detached loose peel fell",
                "Sensor Abnormal": "abnormal error warm-up warmup replace device recovery",
                "Data accuracy": "accuracy inaccurate bgm low fluctuation jump glucose",
            }

        self.verdict_presentation = {
            **self.verdict_presentation,
            "enabled": self.verdict_presentation_enabled,
            "template_version": self.verdict_presentation_template_version,
        }

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
