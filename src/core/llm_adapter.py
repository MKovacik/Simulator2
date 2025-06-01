"""
LM Studio Adapter for CrewAI
---------------------------
This module provides a custom LLM adapter for LM Studio to work with CrewAI.
It handles the specific requirements of LM Studio's API, particularly the
limitation of only supporting 'user' and 'assistant' roles.
"""

import os
import json
import requests
from typing import Any, Dict, List, Mapping, Optional
from langchain_core.language_models.llms import LLM
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from dotenv import load_dotenv
import time

# Global list to store LLM logs
llm_logs = []

# Load environment variables
load_dotenv()

# Get LM Studio configuration from environment variables
LMSTUDIO_BASE_URL = os.getenv('LMSTUDIO_BASE_URL', 'http://localhost:1234/v1')
LMSTUDIO_MODEL_NAME = os.getenv('LMSTUDIO_MODEL_NAME', 'mistral-7b-instruct-v0.3')

class LMStudioLLM(LLM):
    """
    Custom LLM class for LM Studio API integration with CrewAI.
    
    This class handles the specific requirements of LM Studio's API,
    particularly combining system and user prompts into a single 'user' role
    message to work around LM Studio's limitations.
    """
    
    model_name: str = LMSTUDIO_MODEL_NAME
    base_url: str = LMSTUDIO_BASE_URL
    temperature: float = 0.7
    max_tokens: int = 2000
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print(f"[LLM] Initialized LMStudioLLM with model: {self.model_name}")
        print(f"[LLM] Base URL: {self.base_url}")
        print(f"[LLM] Temperature: {self.temperature}, Max tokens: {self.max_tokens}")
        
        # Store logs
        llm_logs.append(f"[LLM] Initialized LMStudioLLM with model: {self.model_name}")
        llm_logs.append(f"[LLM] Base URL: {self.base_url}")
        llm_logs.append(f"[LLM] Temperature: {self.temperature}, Max tokens: {self.max_tokens}")
    
    @property
    def _llm_type(self) -> str:
        return "lm-studio-api"
    
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """
        Call the LM Studio API with the given prompt.
        
        This method combines any system prompt with the user prompt into a single
        'user' role message to work around LM Studio's limitations of only supporting
        'user' and 'assistant' roles.
        """
        # Extract system prompt if present (CrewAI often includes it in the format "System: ... User: ...")
        system_prompt = ""
        user_prompt = prompt
        
        if "System:" in prompt and "User:" in prompt:
            parts = prompt.split("User:", 1)
            if len(parts) == 2:
                system_part = parts[0].strip()
                user_part = parts[1].strip()
                
                if system_part.startswith("System:"):
                    system_prompt = system_part[7:].strip()
                    user_prompt = user_part
        
        # Combine system and user prompts if system prompt is present
        if system_prompt:
            combined_prompt = f"{system_prompt}\n\n{user_prompt}"
        else:
            combined_prompt = user_prompt
        
        # Prepare the API request
        endpoint_url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": combined_prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        
        if stop:
            payload["stop"] = stop
        
        # Log the API request details
        req_log1 = f"[LLM] Sending request to LM Studio API"
        req_log2 = f"[LLM] Prompt length: {len(combined_prompt)} characters"
        print(req_log1)
        print(req_log2)
        
        # Store logs
        llm_logs.append(req_log1)
        llm_logs.append(req_log2)
        
        # Make the API request
        try:
            start_time = time.time()
            response = requests.post(endpoint_url, json=payload)
            elapsed_time = time.time() - start_time
            response.raise_for_status()
            
            # Parse the response
            response_data = response.json()
            content = response_data["choices"][0]["message"]["content"]
            
            # Log successful response details
            resp_log1 = f"[LLM] Response received in {elapsed_time:.2f} seconds"
            resp_log2 = f"[LLM] Response length: {len(content)} characters"
            print(resp_log1)
            print(resp_log2)
            
            # Store logs
            llm_logs.append(resp_log1)
            llm_logs.append(resp_log2)
            
            # Log token usage if available
            if "usage" in response_data:
                usage = response_data["usage"]
                usage_log1 = f"[LLM] Token usage: {usage.get('total_tokens', 'N/A')} total tokens"
                usage_log2 = f"[LLM] - Prompt tokens: {usage.get('prompt_tokens', 'N/A')}"
                usage_log3 = f"[LLM] - Completion tokens: {usage.get('completion_tokens', 'N/A')}"
                print(usage_log1)
                print(usage_log2)
                print(usage_log3)
                
                # Store logs
                llm_logs.append(usage_log1)
                llm_logs.append(usage_log2)
                llm_logs.append(usage_log3)
            
            return content
            
        except Exception as e:
            error_msg = f"[LLM] Error calling LM Studio API: {str(e)}"
            print(error_msg)
            
            # Store error log
            llm_logs.append(error_msg)
            
            if hasattr(e, 'response') and e.response is not None:
                resp_err = f"[LLM] Response status: {e.response.status_code}"
                print(resp_err)
                llm_logs.append(resp_err)
                
                try:
                    error_data = e.response.json()
                    json_err = f"[LLM] Response error: {error_data}"
                    print(json_err)
                    llm_logs.append(json_err)
                except:
                    text_err = f"[LLM] Response text: {e.response.text}"
                    print(text_err)
                    llm_logs.append(text_err)
            raise e


def get_llm() -> LMStudioLLM:
    """Get an instance of the LLM adapter."""
    return LMStudioLLM()


def get_llm_logs() -> List[str]:
    """Get the collected LLM logs."""
    logs = llm_logs.copy()
    return logs


def clear_llm_logs() -> None:
    """Clear the collected LLM logs."""
    global llm_logs  # Need global here because we're reassigning the variable
    llm_logs = []
