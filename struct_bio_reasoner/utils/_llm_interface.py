"""
Base interface and implementations for different LLM backends.
This allows the co-scientist system to work with any LLM provider.

This is the ProtoGnosis LLM interface integrated into Jnana.
"""
import os
import json
import requests
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union, Tuple
from .inference_auth_token import get_access_token


import logging

# Configure logger
logger = logging.getLogger(__name__)

# Import libraries for different LLM providers
# These imports are wrapped in try-except blocks to make them optional
try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    import openai
except ImportError:
    openai = None

try:
    import ollama
except ImportError:
    ollama = None

try:
    from cerebras.cloud.sdk import Cerebras
except ImportError:
    cerebras = None


class LLMInterface(ABC):
    """Abstract base class defining the interface for LLM providers."""
    
    def __init__(self, model: str, model_adapter: Optional[Dict] = None):
        """Initialize the LLM interface."""
        self.model = model
        self.model_adapter = model_adapter
        self.total_calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1024) -> str:
        """
        Generate a response from the LLM.

        Args:
            prompt: The main prompt text
            system_prompt: Optional system instructions
            temperature: Controls randomness (0 to 1)
            max_tokens: Maximum response length

        Returns:
            Generated text from the LLM
        """
        pass

    @abstractmethod
    def generate_with_json_output(self, prompt: str, json_schema: Dict,
                                 system_prompt: Optional[str] = None,
                                 temperature: float = 0.7, max_tokens: int = 1024,
                                 tools: Optional[List[Dict]] = None) -> Union[Dict, Tuple[Dict, int, int]]:
        """
        Generate a response that conforms to a specific JSON schema.

        Args:
            prompt: The main prompt text
            json_schema: Dictionary describing the expected JSON structure
            system_prompt: Optional system instructions
            temperature: Controls randomness (0 to 1)
            max_tokens: Maximum response length
            tools: Optional list of tool schemas (may not be used with json_object mode)

        Returns:
            Tuple containing:
            - Response as a structured dictionary matching the given schema
            - Number of prompt tokens used
            - Number of completion tokens used
        """
        pass

    def generate_with_tools(self, prompt: str, tools: List[Dict],
                           system_prompt: Optional[str] = None,
                           temperature: float = 0.7, max_tokens: int = 1024) -> Dict:
        """
        Generate a response with tool calling support.

        This method allows the LLM to call tools/functions during generation.

        Args:
            prompt: The prompt to send to the LLM
            tools: List of tool schemas in OpenAI format
            system_prompt: Optional system-level instructions
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Dictionary containing:
                - 'content': Text response (if any)
                - 'tool_calls': List of tool calls (if any)
                - 'finish_reason': Why generation stopped
                - 'prompt_tokens': Number of prompt tokens
                - 'completion_tokens': Number of completion tokens
        """
        # Default implementation - subclasses should override
        raise NotImplementedError("Tool calling not supported by this LLM provider")


"""
Fixed implementation of the AnthropicLLM class based on the latest Anthropic API requirements.
"""
import os
from typing import Dict, List, Optional, Any, Union
import anthropic

class AnthropicLLM(LLMInterface):
    """Interface for Anthropic Claude models."""
    
    def __init__(self, model: str, api_key: str, model_adapter: Optional[Dict] = None):
        """Initialize the Anthropic LLM interface."""
        super().__init__(model, model_adapter)
        self.api_key = api_key
        
        # Import Anthropic library
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError("Please install the Anthropic Python library: pip install anthropic")
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1024) -> str:
        """Generate a response from Claude."""
        try:
            # Prepare the messages
            messages = [{"role": "user", "content": prompt}]
            
            # Create the message
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=messages
            )
            
            # Extract the response text
            response_text = response.content[0].text
            
            # Update token counts
            self.total_calls += 1
            self.total_prompt_tokens += response.usage.input_tokens
            self.total_completion_tokens += response.usage.output_tokens
            
            return response_text
        except Exception as e:
            logger.error(f"Error generating response from Anthropic: {str(e)}")
            raise

    def generate_with_json_output(self, prompt: str, json_schema: Dict,
                                 system_prompt: Optional[str] = None,
                                 temperature: float = 0.7, max_tokens: int = 1024,
                                 tools: Optional[List[Dict]] = None) -> Union[Dict, Tuple[Dict, int, int]]:
        """Generate a response that conforms to a JSON schema."""
        try:
            # Add JSON formatting instructions to the system prompt
            json_instructions = f"""
            Your response must be formatted as a JSON object that conforms to the following schema:
            {json.dumps(json_schema, indent=2)}
            
            Ensure your response can be parsed by Python's json.loads().
            """
            
            full_system_prompt = f"{system_prompt}\n\n{json_instructions}" if system_prompt else json_instructions
            
            # Generate the response
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=full_system_prompt,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Extract the response text
            response_text = response.content[0].text
            
            # Update token counts
            self.total_calls += 1
            self.total_prompt_tokens += response.usage.input_tokens
            self.total_completion_tokens += response.usage.output_tokens
            
            # Parse the JSON response
            # First, try to find JSON within markdown code blocks
            import re
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                # If no code block, use the entire response
                json_str = response_text
            
            # Clean up the JSON string
            json_str = json_str.strip()
            
            # Parse the JSON
            try:
                parsed_json = json.loads(json_str)
                return (parsed_json, response.usage.input_tokens, response.usage.output_tokens)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON response: {json_str}")
                raise ValueError(f"Failed to parse JSON response from LLM: {json_str}")
        
        except Exception as e:
            logger.error(f"Error generating JSON response from Anthropic: {str(e)}")
            raise


class GeminiLLM(LLMInterface):
    """Implementation for Google's Gemini API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-pro", model_adapter: Optional[Dict] = None):
        """
        Initialize the Gemini LLM interface.

        Args:
            api_key: Google API key (defaults to GOOGLE_API_KEY env variable)
            model: Model identifier to use
            model_adapter: Optional configuration for model adaptation
        """
        super().__init__(model, model_adapter)
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("No Google API key provided")

        genai.configure(api_key=self.api_key)

    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1024) -> str:
        """Generate a response from Gemini."""
        model = genai.GenerativeModel(
            model_name=self.model,
            generation_config={"temperature": temperature, "max_output_tokens": max_tokens}
        )

        # Combine system prompt and user prompt if both are provided
        if system_prompt:
            response = model.generate_content([
                {"role": "system", "parts": [system_prompt]},
                {"role": "user", "parts": [prompt]}
            ])
        else:
            response = model.generate_content(prompt)

        return response.text

    def generate_with_json_output(self, prompt: str, json_schema: Dict,
                                 system_prompt: Optional[str] = None,
                                 temperature: float = 0.7, max_tokens: int = 1024,
                                 tools: Optional[List[Dict]] = None) -> Tuple[Dict, int, int]:
        """Generate a structured JSON response from Gemini."""
        schema_prompt = f"""
        Your response must be formatted as a JSON object according to this schema:
        {json_schema}

        Ensure your response can be parsed by Python's json.loads().
        Return only the JSON object with no additional text.
        """

        full_prompt = f"{prompt}\n\n{schema_prompt}"
        system = system_prompt or "You output only valid JSON according to the specified schema."

        # Create model with system prompt if provided
        model = genai.GenerativeModel(
            model_name=self.model,
            generation_config={"temperature": temperature, "max_output_tokens": max_tokens}
        )

        if system_prompt:
            response = model.generate_content([
                {"role": "system", "parts": [system]},
                {"role": "user", "parts": [full_prompt]}
            ])
        else:
            response = model.generate_content(full_prompt)

        # Extract JSON string and parse
        import json
        try:
            # Strip any markdown code formatting if present
            content = response.text
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            parsed_response = json.loads(content)

            # Gemini doesn't provide token counts, so we estimate
            prompt_tokens = len(full_prompt.split()) * 1.3  # Rough estimate
            completion_tokens = len(response.text.split()) * 1.3  # Rough estimate

            self.total_calls += 1
            self.total_prompt_tokens += int(prompt_tokens)
            self.total_completion_tokens += int(completion_tokens)

            return parsed_response, int(prompt_tokens), int(completion_tokens)
        except Exception as e:
            raise ValueError(f"Failed to parse JSON response: {e}. Response was: {response.text}")


class OpenAILLM(LLMInterface):
    """Implementation for OpenAI's API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o", model_adapter: Optional[Dict] = None):
        """
        Initialize the OpenAI LLM interface.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env variable)
            model: Model identifier to use
            model_adapter: Optional configuration for model adaptation
        """
        super().__init__(model, model_adapter)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("No OpenAI API key provided")

        self.client = openai.OpenAI(api_key=self.api_key)

    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1024) -> str:
        """Generate a response from OpenAI."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        return response.choices[0].message.content

    def generate_with_json_output(self, prompt: str, json_schema: Dict,
                                 system_prompt: Optional[str] = None,
                                 temperature: float = 0.7, max_tokens: int = 1024,
                                 tools: Optional[List[Dict]] = None) -> Tuple[Dict, int, int]:
        """
        Generate a structured JSON response from OpenAI.

        Args:
            prompt: The user prompt
            json_schema: JSON schema for the response
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            tools: Optional list of tool schemas for function calling

        Returns:
            Tuple of (parsed_response, prompt_tokens, completion_tokens)
        """
        schema_prompt = f"""
        Your response must be formatted as a JSON object according to this schema:
        {json_schema}

        Ensure your response can be parsed by Python's json.loads().
        """

        full_prompt = f"{prompt}\n\n{schema_prompt}"
        system = system_prompt or "You output only valid JSON according to the specified schema."

        messages = [{"role": "system", "content": system}]
        messages.append({"role": "user", "content": full_prompt})

        # Build API call parameters
        api_params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}
        }

        # Add tools if provided (but don't use them with json_object mode)
        # OpenAI doesn't support both tools and json_object response_format
        # So we'll just log that tools are available but not use function calling
        if tools:
            logger.info(f"Tools available but not used with json_object mode: {[t['function']['name'] for t in tools]}")

        response = self.client.chat.completions.create(**api_params)

        # Extract JSON string and parse
        import json
        try:
            content = response.choices[0].message.content
            parsed_response = json.loads(content)

            # Get token counts from OpenAI response
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens

            self.total_calls += 1
            self.total_prompt_tokens += prompt_tokens
            self.total_completion_tokens += completion_tokens

            return parsed_response, prompt_tokens, completion_tokens
        except Exception as e:
            raise ValueError(f"Failed to parse JSON response: {e}. Response was: {response.choices[0].message.content}")

    def generate_with_tools(self, prompt: str, tools: List[Dict],
                           system_prompt: Optional[str] = None,
                           temperature: float = 0.7, max_tokens: int = 1024) -> Dict:
        """
        Generate a response with tool calling support.

        This allows the LLM to call tools/functions during generation.

        Args:
            prompt: The prompt to send to the LLM
            tools: List of tool schemas in OpenAI format
            system_prompt: Optional system-level instructions
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Dictionary containing:
                - 'content': Text response (if any)
                - 'tool_calls': List of tool calls (if any), each with:
                    - 'id': Tool call ID
                    - 'name': Tool name
                    - 'arguments': Dict of arguments
                - 'finish_reason': Why generation stopped
                - 'prompt_tokens': Number of prompt tokens
                - 'completion_tokens': Number of completion tokens
        """
        system = system_prompt or "You are a helpful assistant."

        messages = [{"role": "system", "content": system}]
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens
        )

        message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        # Get token counts
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens

        self.total_calls += 1
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens

        # Parse tool calls if present
        tool_calls = []
        if message.tool_calls:
            import json
            for tool_call in message.tool_calls:
                tool_calls.append({
                    'id': tool_call.id,
                    'name': tool_call.function.name,
                    'arguments': json.loads(tool_call.function.arguments)
                })

        return {
            'content': message.content,
            'tool_calls': tool_calls,
            'finish_reason': finish_reason,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens
        }


class OllamaLLM(LLMInterface):
    """Implementation for Ollama local LLM API."""

    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434", 
                 api_key: Optional[str] = None, model_adapter: Optional[Dict] = None):
        """
        Initialize the Ollama LLM interface.

        Args:
            model: Model identifier to use (e.g., "llama3", "mistral", "gemma")
            base_url: Base URL for the Ollama API
            api_key: Not used for Ollama, but kept for interface consistency
            model_adapter: Optional configuration for model adaptation
        """
        super().__init__(model, model_adapter)
        self.base_url = base_url.rstrip('/')

        # Check if Ollama is available
        if ollama is None:
            raise ImportError("Ollama package is not installed. Please install it with 'pip install ollama'.")

        # Initialize the client
        self.client = ollama.Client(host=base_url)

        # Test connection
        try:
            self.client.list()
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Ollama at {base_url}: {str(e)}. Make sure Ollama is running.")

    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1024) -> str:
        """Generate a response from Ollama."""
        # Prepare the request
        request = {
            "model": self.model,
            "prompt": prompt,
            # Ollama client doesn't accept temperature directly in generate()
            # "temperature": temperature,
            # "max_tokens": max_tokens,
            "stream": False
        }

        # Add system prompt if provided
        if system_prompt:
            request["system"] = system_prompt

        # Make the request
        response = self.client.generate(**request)

        # Extract the response text
        return response.get('response', '')

    def generate_with_json_output(self, prompt: str, json_schema: Dict,
                                 system_prompt: Optional[str] = None,
                                 temperature: float = 0.7, max_tokens: int = 1024,
                                 tools: Optional[List[Dict]] = None) -> Tuple[Dict, int, int]:
        """Generate a structured JSON response from Ollama."""
        schema_prompt = f"""
        Your response must be formatted as a JSON object according to this schema:
        {json_schema}

        Ensure your response can be parsed by Python's json.loads().
        Return only the JSON object with no additional text.
        """

        full_prompt = f"{prompt}\n\n{schema_prompt}"
        system = system_prompt or "You output only valid JSON according to the specified schema."

        # Generate the response
        response_text = self.generate(full_prompt, system_prompt=system)

        # Extract JSON string and parse
        import json
        try:
            # Strip any markdown code formatting if present
            content = response_text
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            # Try to parse the JSON
            parsed_json = json.loads(content)
            # Return the parsed JSON and dummy token counts to match the expected interface
            return parsed_json, 0, 0
        except Exception as e:
            raise ValueError(f"Failed to parse JSON response: {e}. Response was: {response_text}")


class LLMStudioLLM(LLMInterface):
    """Implementation for LLM Studio local API."""

    def __init__(self, model: str = "default", base_url: str = "http://localhost:3000", 
                 api_key: Optional[str] = None, model_adapter: Optional[Dict] = None):
        """
        Initialize the LLM Studio interface.

        Args:
            model: Model identifier (not used in LLM Studio as it's configured in the UI)
            base_url: Base URL for the LLM Studio API
            api_key: Not used for LLM Studio, but kept for interface consistency
            model_adapter: Optional configuration for model adaptation
        """
        super().__init__(model, model_adapter)
        self.base_url = base_url.rstrip('/')

        # Test connection
        try:
            response = requests.get(f"{self.base_url}/health")
            if response.status_code != 200:
                raise ConnectionError(f"LLM Studio returned status code {response.status_code}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to LLM Studio at {base_url}: {str(e)}. Make sure LLM Studio is running.")

    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1024) -> str:
        """Generate a response from LLM Studio."""
        # Prepare the request
        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": temperature,
                "max_new_tokens": max_tokens,
                "do_sample": temperature > 0
            }
        }

        # Add system prompt if provided
        if system_prompt:
            payload["system_prompt"] = system_prompt

        # Make the request
        response = requests.post(
            f"{self.base_url}/generate",
            json=payload,
            headers={"Content-Type": "application/json"}
        )

        # Check for errors
        if response.status_code != 200:
            raise ValueError(f"LLM Studio API returned status code {response.status_code}: {response.text}")

        # Extract the response text
        result = response.json()
        return result.get('generated_text', '')

    def _extract_and_parse_json(self, text):
        """Extract and parse JSON from text, handling control characters."""
        import re
        import json
        
        # Try to extract JSON using regex
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```|```\s*([\s\S]*?)\s*```|(\{[\s\S]*\})', text)
        if json_match:
            json_str = next(filter(None, json_match.groups()))
        else:
            json_str = text
        
        try:
            # First try standard parsing
            return json.loads(json_str)
        except json.JSONDecodeError:
            # If that fails, try to clean the string
            # Replace invalid control characters
            json_str = re.sub(r'[\x00-\x1F\x7F]', ' ', json_str)
            return json.loads(json_str)

    def generate_with_json_output(self, prompt: str, json_schema: Dict,
                                 system_prompt: Optional[str] = None,
                                 temperature: float = 0.7, max_tokens: int = 1024,
                                 tools: Optional[List[Dict]] = None) -> Tuple[Dict, int, int]:
        """Generate a structured JSON response from the LLM."""
        schema_prompt = f"""
        Your response must be formatted as a JSON object according to this schema:
        {json_schema}

        Ensure your response can be parsed by Python's json.loads().
        Return only the JSON object with no additional text.
        Do not include any control characters or newlines within string values.
        """

        full_prompt = f"{prompt}\n\n{schema_prompt}"
        
        # Generate the response
        response_text = self.generate(full_prompt, system_prompt, temperature, max_tokens)
        
        try:
            # Parse the JSON response using our robust parser
            response_json = self._extract_and_parse_json(response_text)

            # LLMStudio doesn't provide token counts, so we estimate
            prompt_tokens = len(full_prompt.split()) * 1.3  # Rough estimate
            completion_tokens = len(response_text.split()) * 1.3  # Rough estimate

            self.total_calls += 1
            self.total_prompt_tokens += int(prompt_tokens)
            self.total_completion_tokens += int(completion_tokens)

            return response_json, int(prompt_tokens), int(completion_tokens)
        except Exception as e:
            raise ValueError(f"Failed to parse JSON response: {str(e)}. Response was: {response_text}")


class CerebrasLLM(LLMInterface):
    def __init__(self, api_key: Optional[str] = None, model: str = "default", model_adapter: Optional[Dict] = None):
        """
        Initialize the Cerebras LLM interface.
        
        Args:
            api_key: Cerebras API key (defaults to CEREBRAS_API_KEY env variable)
            model: Model identifier to use
            model_adapter: Optional configuration for model adaptation
        """
        super().__init__(model, model_adapter)
        self.api_key = api_key or os.environ.get("CEREBRAS_API_KEY")

        if not self.api_key:
            raise ValueError("No Cerebras API key provided")

        self.client = Cerebras(api_key=self.api_key)
        self.n_calls = 0


    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1024) -> str:
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        self.total_prompt_tokens += prompt_tokens 
        self.total_completion_tokens += completion_tokens
        self.total_calls += 1

        return response.choices[0].message.content, prompt_tokens, completion_tokens


    def generate_with_json_output(self, prompt: str, json_schema: Dict,
                                 system_prompt: Optional[str] = None,
                                 temperature: float = 0.7, max_tokens: int = 1024,
                                 tools: Optional[List[Dict]] = None) -> Dict:
        """Generate a structured JSON response from Cerebras."""
        schema_prompt = f"""
        Your response must be formatted as a JSON object according to this schema:
        {json_schema}

        Ensure your response can be parsed by Python's json.loads().
        """

        full_prompt = f"{prompt}\n\n{schema_prompt}"
        system = system_prompt or "You output only valid JSON according to the specified schema."

        messages = [{"role": "system", "content": system}]
        messages.append({"role": "user", "content": full_prompt})

        # converted_schema = translate_cerebras_schema(json_schema)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
            # response_format={"type": "json_schema",
            #                  "json_schema": converted_schema}
        )

        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        
        self.total_prompt_tokens += prompt_tokens 
        self.total_completion_tokens += completion_tokens
        self.total_calls += 1

        # Extract JSON string and parse
        import json
        try:
            content = response.choices[0].message.content
            out = json.loads(content)

            return out, prompt_tokens, completion_tokens
        except Exception as e:
            raise ValueError(f"Failed to parse JSON response: {e}. Response was: {response.choices[0].message.content}")


class alcfLLM(LLMInterface):
    """Implementation for OpenAI's API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "openai/gpt-oss-120b", model_adapter: Optional[Dict] = None):
        """
        Initialize the OpenAI LLM interface.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env variable)
            model: Model identifier to use
            model_adapter: Optional configuration for model adaptation
        """
        super().__init__(model, model_adapter)
        if 'metis' in model:
            base_url = "https://inference-api.alcf.anl.gov/resource_server/metis/api/v1"
            self.model = model.replace('metis/', '')
        else:
            base_url = "https://inference-api.alcf.anl.gov/resource_server/sophia/vllm/v1"
            self.model = model
        
        self.model_adapter = model_adapter
        api_key = get_access_token()

        self.client = openai.OpenAI(
                api_key=api_key,
                base_url=base_url,
            )
       
    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1024) -> str:
        """Generate a response from OpenAI."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        return response.choices[0].message.content

    def generate_with_json_output(self, prompt: str, json_schema: Dict,
                                 system_prompt: Optional[str] = None,
                                 temperature: float = 0.7, max_tokens: int = 1024,
                                 tools: Optional[List[Dict]] = None) -> Tuple[Dict, int, int]:
        """Generate a structured JSON response from OpenAI."""
        schema_prompt = f"""
        Your response must be formatted as a JSON object according to this schema:
        {json_schema}

        Ensure your response can be parsed by Python's json.loads()."""

        full_prompt = f"{prompt}\n\n{schema_prompt}"
        system = system_prompt or "You output only valid JSON according to the specified schema."

        messages = [{"role": "system", "content": system,}]
        messages.append({"role": "user", "content": full_prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        print(f"{response=}")
        while response.choices[0].message.content is None:
            if response.choices[0].message.reasoning_content is not None:
                print(f"{response=}")
                messages.append({"role": "assistant", "content": response.choices[0].message.reasoning_content})
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )


        # Extract JSON string and parse
        import json
        try:
            content = response.choices[0].message.content
            parsed_response = json.loads(content)

            # Get token counts from OpenAI response
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens

            self.total_calls += 1
            self.total_prompt_tokens += prompt_tokens
            self.total_completion_tokens += completion_tokens

            return parsed_response, prompt_tokens, completion_tokens
        except Exception as e:
            raise ValueError(f"Failed to parse JSON response: {e}. Response was: {response.choices[0].message.content}")
 
        
class vllmLLM(LLMInterface):
    """Implementation for OpenAI's API."""

    def __init__(self, api_key: str = 'EMPTY', model: str = "openai/gpt-oss-120b", model_adapter: Optional[Dict] = None):
        """
        Initialize the OpenAI LLM interface.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env variable)
            model: Model identifier to use
            model_adapter: Optional configuration for model adaptation
        """
        super().__init__(model, model_adapter)
        self.model = model
        self.model_adapter = model_adapter
        
        self.client = openai.OpenAI(base_url="http://localhost:8000/v1", api_key=api_key)

    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1024) -> str:
        """Generate a response from OpenAI."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        return response.choices[0].message.content

    def generate_with_json_output(self, prompt: str, json_schema: Dict,
                                 system_prompt: Optional[str] = None,
                                 temperature: float = 0.7, max_tokens: int = 1024,
                                 tools: Optional[List[Dict]] = None) -> Tuple[Dict, int, int]:
        """Generate a structured JSON response from OpenAI."""
        schema_prompt = f"""
        Your response must be formatted as a JSON object according to this schema:
        {json_schema}

        Ensure your response can be parsed by Python's json.loads().
        """

        full_prompt = f"{prompt}\n\n{schema_prompt}"
        system = system_prompt or "You output only valid JSON according to the specified schema."

        messages = [{"role": "system", "content": system}]
        messages.append({"role": "user", "content": full_prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )

        # Extract JSON string and parse
        import json
        try:
            content = response.choices[0].message.content
            parsed_response = json.loads(content)

            # Get token counts from OpenAI response
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens

            self.total_calls += 1
            self.total_prompt_tokens += prompt_tokens
            self.total_completion_tokens += completion_tokens

            return parsed_response, prompt_tokens, completion_tokens
        except Exception as e:
            raise ValueError(f"Failed to parse JSON response: {e}. Response was: {response.choices[0].message.content}")
 


def typify_schema(in_schema):
    out_schema = {}

    for k, v in in_schema.items():
        # logging.info((k, v, type(k), type(v)))

        if isinstance(v, list):
            out_schema[k] = {
                "type": "array",
                "items": {"type": v[0]}
            }
        
        elif isinstance(v, dict):
            out_schema[k] = typify_schema(v)

        else:
            out_schema[k] = {"type": v}

    return out_schema


def translate_cerebras_schema(in_schema):
    out_schema = {
        "name": "coscientist_schema",
        "strict": True,
        "schema": {
            "type": "object",
            "required": list(in_schema.keys())
        }
    }

    typified_schema = typify_schema(in_schema)

    from jsonschema import validate, ValidationError, SchemaError

    try:
        validate(instance={}, schema=typified_schema)
    except SchemaError as e:
        logging.error(f"JSON schema is invalid: {e}.")
        raise e
    except Exception as e:
        logging.error(f"Other JSON schema issue: {e}")
        raise e

    out_schema["schema"]["properties"] = typified_schema

    return out_schema


def create_llm(provider: str, api_key: Optional[str] = None, model: Optional[str] = None, 
               base_url: Optional[str] = None, model_adapter: Optional[Dict[str, Any]] = None) -> LLMInterface:
    """
    Factory function to create LLM interfaces.

    Args:
        provider: The LLM provider ("anthropic", "gemini", "openai", "ollama", "llm_studio", "cerebras")
        api_key: Optional API key (otherwise uses environment variables)
        model: Optional model name (otherwise uses defaults)
        base_url: Optional base URL for local LLM providers
        model_adapter: Optional configuration for model adaptation

    Returns:
        An instance of the appropriate LLM interface
    """
    provider = provider.lower()

    # Create the base LLM interface
    llm = None
    
    if provider == "anthropic":
        if anthropic is None:
            raise ImportError("Anthropic package is not installed. Please install it with 'pip install anthropic'.")
        model = model or "claude-3-7-sonnet-20250219"
        llm = AnthropicLLM(api_key=api_key, model=model, model_adapter=model_adapter)
    elif provider == "gemini":
        if genai is None:
            raise ImportError("Google Generative AI package is not installed. Please install it with 'pip install google-generativeai'.")
        model = model or "gemini-1.5-pro"
        llm = GeminiLLM(api_key=api_key, model=model, model_adapter=model_adapter)
    elif provider == "openai":
        if openai is None:
            raise ImportError("OpenAI package is not installed. Please install it with 'pip install openai'.")
        model = model or "gpt-4o"
        llm = OpenAILLM(api_key=api_key, model=model, model_adapter=model_adapter)
    elif provider == "ollama":
        model = model or "llama3"
        ollama_url = base_url or "http://localhost:11434"
        llm = OllamaLLM(model=model, base_url=ollama_url, api_key=api_key, model_adapter=model_adapter)
    elif provider == "llm_studio":
        model = model or "default"
        studio_url = base_url or "http://localhost:3000"
        llm = LLMStudioLLM(model=model, base_url=studio_url, api_key=api_key, model_adapter=model_adapter)
    elif provider == "cerebras":
        model = model or "cerebras_api_keyllama-4-scout-17b-16e-instruct"
        llm = CerebrasLLM(api_key=api_key, model=model, model_adapter=model_adapter)
    elif provider == "alcf":
        model = model or "openai/gpt-oss-120b"
        # base_url = base_url or "https://inference-api.alcf.anl.gov/resource_server/sophia/vllm/v1"
        llm = alcfLLM(model=model, model_adapter=model_adapter)
    elif provider == "vllm":
        model = model or "openai/gpt-oss-120b"
        # base_url = base_url or "http://localhost:8000/v1"
        llm = vllmLLM(model=model, model_adapter=model_adapter)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    
    return llm
