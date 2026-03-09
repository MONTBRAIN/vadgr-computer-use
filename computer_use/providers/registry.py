# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Provider factory and registry."""

import importlib
import logging
import os

from computer_use.core.errors import ConfigError
from computer_use.providers.base import VisionProvider

logger = logging.getLogger("computer_use.providers.registry")

_PROVIDERS = {
    "anthropic": "computer_use.providers.anthropic.AnthropicProvider",
    "openai": "computer_use.providers.openai.OpenAIProvider",
}


def get_provider(name: str, config: dict) -> VisionProvider:
    """Instantiate a vision provider by name.

    API key resolution order:
    1. config.yaml providers.<name>.api_key
    2. Environment variable <NAME>_API_KEY
    """
    if name not in _PROVIDERS:
        raise ConfigError(
            f"Unknown provider '{name}'. Available: {list(_PROVIDERS.keys())}"
        )

    module_path, class_name = _PROVIDERS[name].rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)

    provider_config = config.get("providers", {}).get(name, {})
    api_key = provider_config.get("api_key") or os.environ.get(
        f"{name.upper()}_API_KEY"
    )
    if not api_key:
        raise ConfigError(
            f"No API key for '{name}'. Set {name.upper()}_API_KEY env var "
            f"or add providers.{name}.api_key to config.yaml."
        )

    model = provider_config.get("model")
    kwargs = {"api_key": api_key}
    if model:
        kwargs["model"] = model

    logger.info("Initializing provider: %s (model: %s)", name, model or "default")
    return cls(**kwargs)


def list_providers() -> list[str]:
    """Return names of all registered providers."""
    return list(_PROVIDERS.keys())
