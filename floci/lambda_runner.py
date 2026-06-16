"""
Lambda Runner - Executes Python Lambda functions locally.
Each Lambda is treated as a Python module with a lambda_handler entry point.
"""

import sys
import os
import json
import importlib.util
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class LambdaRunner:
    """Loads and executes Lambda functions from the lambdas directory."""

    def __init__(self, lambdas_dir: str = "/app/lambdas"):
        self.lambdas_dir = lambdas_dir
        self.loaded_functions = {}

    def execute(self, function_name: str, event: Dict[str, Any],
                context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a Lambda function by name."""
        module = self._load_function(function_name)
        if module is None:
            return self._mock_execute(function_name, event)

        ctx = context or {
            "function_name": function_name,
            "memory_limit_in_mb": 128,
            "invoked_function_arn": f"arn:aws:lambda:local:function:{function_name}",
        }

        try:
            result = module.lambda_handler(event, ctx)
            logger.info(f"Lambda {function_name} executed successfully")
            return {"status": "success", "result": result}
        except Exception as e:
            logger.error(f"Lambda {function_name} failed: {e}")
            return {"status": "error", "error": str(e)}

    def _load_function(self, function_name: str):
        """Load a Lambda function module."""
        if function_name in self.loaded_functions:
            return self.loaded_functions[function_name]

        # Look for app.py in the function directory
        function_path = os.path.join(self.lambdas_dir, function_name, "app.py")
        if not os.path.exists(function_path):
            logger.warning(f"Lambda function not found: {function_path}")
            return None

        spec = importlib.util.spec_from_file_location(
            f"lambda_{function_name}", function_path
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"lambda_{function_name}"] = module
        spec.loader.exec_module(module)
        self.loaded_functions[function_name] = module
        return module

    def _mock_execute(self, function_name: str,
                      event: Dict[str, Any]) -> Dict[str, Any]:
        """Mock execution for when the Lambda file doesn't exist."""
        logger.info(f"Mock executing Lambda: {function_name}")
        return {
            "status": "success",
            "function": function_name,
            "event": event,
            "mock": True,
        }