"""
State Machine Runner - Executes Step Functions-compatible ASL definitions.
Parses the ingestion.asl.json state machine and executes it step by step.
"""

import json
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class StateMachineRunner:
    """Executes AWS Step Functions-compatible state machines locally."""

    def __init__(self, definition_path: str):
        with open(definition_path, "r") as f:
            self.definition = json.load(f)
        self.current_state = self.definition.get("StartAt")
        self.states = self.definition.get("States", {})
        self.execution_history = []

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the state machine from the StartAt state."""
        output = input_data
        self.current_state = self.definition.get("StartAt")

        logger.info(f"Starting state machine execution at: {self.current_state}")

        while self.current_state:
            state_def = self.states.get(self.current_state)
            if not state_def:
                raise ValueError(f"State '{self.current_state}' not found in definition")

            state_type = state_def.get("Type")
            logger.info(f"Executing state: {self.current_state} (Type: {state_type})")

            # Execute the state
            output = self._execute_state(self.current_state, state_def, output)
            self.execution_history.append({
                "state": self.current_state,
                "type": state_type,
                "output": output,
                "timestamp": time.time(),
            })

            # Determine next state
            self.current_state = self._get_next_state(state_def, output)

        logger.info("State machine execution completed")
        return output

    def _execute_state(self, state_name: str, state_def: Dict[str, Any],
                       input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single state."""
        state_type = state_def.get("Type")

        if state_type == "Pass":
            return {**input_data, **(state_def.get("Result", {}))}

        elif state_type == "Task":
            resource = state_def.get("Resource", "")
            parameters = state_def.get("Parameters", {})
            
            # Mock task execution - resolves function references
            if "arn:aws:lambda" in resource or "function" in resource:
                function_name = resource.split(":")[-1].split(".")[0]
                return self._mock_lambda(function_name, input_data, parameters)
            
            return input_data

        elif state_type == "Choice":
            return self._evaluate_choices(state_def.get("Choices", []), input_data)

        elif state_type == "Succeed":
            return input_data

        elif state_type == "Fail":
            cause = state_def.get("Cause", "Unknown error")
            error = state_def.get("Error", "StateMachineError")
            raise Exception(f"{error}: {cause}")

        elif state_type == "Wait":
            seconds = state_def.get("Seconds", 0)
            if seconds > 0:
                time.sleep(seconds)
            return input_data

        return input_data

    def _get_next_state(self, state_def: Dict[str, Any],
                        output: Dict[str, Any]) -> Optional[str]:
        """Determine the next state based on the current state definition and output."""
        state_type = state_def.get("Type")

        if state_type == "Choice":
            return output.get("_next_state")

        if state_type == "Succeed" or state_type == "Fail":
            return None

        # Default: use the End or Next field
        if state_def.get("End", False):
            return None
        
        return state_def.get("Next")

    def _evaluate_choices(self, choices: list, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate Choice state rules."""
        for choice in choices:
            variable = choice.get("Variable", "")
            # Extract the path after $
            var_name = variable.replace("$.", "") if variable.startswith("$.") else variable
            value = input_data.get(var_name)
            
            for operator, expected in choice.items():
                if operator == "Variable":
                    continue
                elif operator == "Next":
                    continue
                elif operator == "StringEquals" and value == expected:
                    return {"_next_state": choice.get("Next")}
                elif operator == "BooleanEquals" and value == expected:
                    return {"_next_state": choice.get("Next")}
                elif operator == "NumericEquals" and value == expected:
                    return {"_next_state": choice.get("Next")}
                elif operator == "IsPresent" and expected and value is not None:
                    return {"_next_state": choice.get("Next")}

        # Default
        default = choice.get("Default") if isinstance(choice, dict) else None
        if "Default" in input_data:
            default = input_data["Default"]
        fallback = next(
            (c.get("Next") for c in choices if c.get("Next")),
            None
        )
        return {"_next_state": default or fallback}

    def _mock_lambda(self, function_name: str, input_data: Dict[str, Any],
                     parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Mock Lambda execution for local testing."""
        logger.info(f"Mock executing Lambda: {function_name}")
        return {
            "status": "success",
            "function": function_name,
            "input": input_data,
            "parameters": parameters,
        }

    def get_history(self) -> list:
        """Get execution history."""
        return self.execution_history