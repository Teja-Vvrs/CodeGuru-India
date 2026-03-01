"""LangChain orchestration for LLM interactions."""
import json
import logging
import time
from typing import Dict, Optional
from ai.bedrock_client import BedrockClient
from ai.prompt_templates import PromptManager
from utils.llm_cache import get_cache
from utils.performance_metrics import record_metric

logger = logging.getLogger(__name__)


class LangChainOrchestrator:
    """Orchestrates LLM calls using LangChain and AWS Bedrock."""
    
    def __init__(
        self,
        bedrock_client: BedrockClient,
        prompt_manager: PromptManager,
        enable_cache: bool = True
    ):
        """
        Initialize with Bedrock client and prompt manager.
        
        Args:
            bedrock_client: AWS Bedrock client
            prompt_manager: Prompt template manager
            enable_cache: Enable response caching (default: True)
        """
        self.bedrock_client = bedrock_client
        self.prompt_manager = prompt_manager
        self.enable_cache = enable_cache
        self.cache = get_cache() if enable_cache else None
    
    def generate_completion(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        """
        Generate completion from LLM with caching.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            
        Returns:
            Generated text
        """
        start_time = time.time()
        
        try:
            parameters = {
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            # Check cache first
            if self.enable_cache and self.cache:
                cached_response = self.cache.get(prompt, parameters)
                if cached_response is not None:
                    duration = time.time() - start_time
                    record_metric("llm_completion_cached", duration, {
                        "cache_hit": True,
                        "prompt_length": len(prompt)
                    })
                    logger.info(f"Cache hit - returned in {duration:.3f}s")
                    return cached_response
            
            # Cache miss - call LLM
            response = self.bedrock_client.invoke_model(
                prompt=prompt,
                parameters=parameters
            )
            
            # Store in cache
            if self.enable_cache and self.cache:
                self.cache.set(prompt, response, parameters)
            
            # Record metrics
            duration = time.time() - start_time
            record_metric("llm_completion", duration, {
                "cache_hit": False,
                "prompt_length": len(prompt),
                "response_length": len(response) if response else 0
            })
            
            logger.info(f"LLM completion generated in {duration:.3f}s")
            return response
        
        except Exception as e:
            duration = time.time() - start_time
            record_metric("llm_completion_error", duration, {
                "error": str(e)
            })
            logger.error(f"Completion generation failed: {e}")
            return f"Error generating response: {str(e)}"
    
    def generate_with_chain(
        self,
        chain_type: str,
        inputs: Dict
    ) -> str:
        """
        Execute a LangChain chain with inputs.
        
        Args:
            chain_type: Type of chain to execute
            inputs: Input parameters for the chain
            
        Returns:
            Chain output
        """
        try:
            if chain_type == "code_explanation":
                prompt = self.prompt_manager.get_code_explanation_prompt(
                    code=inputs.get("code", ""),
                    language=inputs.get("language", "english"),
                    difficulty=inputs.get("difficulty", "intermediate")
                )
            
            elif chain_type == "analogy_generation":
                prompt = self.prompt_manager.get_analogy_generation_prompt(
                    concept=inputs.get("concept", ""),
                    language=inputs.get("language", "english")
                )
            
            elif chain_type == "debugging":
                prompt = self.prompt_manager.get_debugging_prompt(
                    code=inputs.get("code", ""),
                    language=inputs.get("language", "english")
                )
            
            elif chain_type == "summary":
                prompt = self.prompt_manager.get_summary_prompt(
                    code=inputs.get("code", ""),
                    language=inputs.get("language", "english")
                )
            
            elif chain_type == "quiz_generation":
                prompt = self.prompt_manager.get_quiz_generation_prompt(
                    topic=inputs.get("topic", ""),
                    difficulty=inputs.get("difficulty", "intermediate"),
                    num_questions=inputs.get("num_questions", 5),
                    language=inputs.get("language", "english"),
                    code_context=inputs.get("code_context", "")
                )
            
            elif chain_type == "flashcard_generation":
                prompt = self.prompt_manager.get_flashcard_generation_prompt(
                    code_concepts=inputs.get("concepts", []),
                    language=inputs.get("language", "english"),
                    difficulty=inputs.get("difficulty", "intermediate")
                )
            
            elif chain_type == "learning_path":
                prompt = self.prompt_manager.get_learning_path_prompt(
                    path_name=inputs.get("path_name", ""),
                    current_level=inputs.get("current_level", "beginner"),
                    language=inputs.get("language", "english"),
                    concepts=inputs.get("concepts", [])
                )
            
            elif chain_type == "concept_summary":
                prompt = self.prompt_manager.get_concept_summary_prompt(
                    concepts=inputs.get("concepts", []),
                    language=inputs.get("language", "english"),
                    intent=inputs.get("intent", "")
                )
            
            elif chain_type == "framework_specific":
                prompt = self.prompt_manager.get_framework_specific_prompt(
                    code=inputs.get("code", ""),
                    framework=inputs.get("framework", ""),
                    language=inputs.get("language", "english")
                )
            
            else:
                return f"Unknown chain type: {chain_type}"
            
            return self.generate_completion(prompt)
        
        except Exception as e:
            logger.error(f"Chain execution failed: {e}")
            return f"Error executing chain: {str(e)}"
    
    def generate_structured_output(
        self,
        prompt: str,
        output_schema: Dict
    ) -> Dict:
        """
        Generate structured output matching schema.
        
        Args:
            prompt: Input prompt
            output_schema: Expected output schema
            
        Returns:
            Structured output as dictionary
        """
        try:
            # Add schema instructions to prompt
            schema_prompt = f"""{prompt}

CRITICAL INSTRUCTIONS:
1. Respond ONLY with valid JSON
2. Do NOT include any text before or after the JSON
3. Do NOT include markdown code blocks
4. Start your response with {{ and end with }}

Expected JSON schema:
{json.dumps(output_schema, indent=2)}"""
            
            response = self.generate_completion(schema_prompt, max_tokens=2000)
            
            # Log the raw response for debugging
            logger.info("=" * 80)
            logger.info("RAW AI RESPONSE:")
            logger.info(response)
            logger.info("=" * 80)
            
            # Try multiple strategies to extract JSON
            parsed_json = None
            
            # Strategy 1: Try to find JSON between curly braces
            try:
                start_idx = response.find('{')
                end_idx = response.rfind('}') + 1
                
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response[start_idx:end_idx]
                    logger.info(f"Strategy 1 - Extracted JSON: {json_str[:200]}...")
                    parsed_json = json.loads(json_str)
                    logger.info("✓ Successfully parsed JSON using strategy 1 (curly braces)")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"✗ Strategy 1 failed: {e}")
            
            # Strategy 2: Try to find JSON between square brackets (for arrays)
            if not parsed_json:
                try:
                    start_idx = response.find('[')
                    end_idx = response.rfind(']') + 1
                    
                    if start_idx != -1 and end_idx > start_idx:
                        json_str = response[start_idx:end_idx]
                        logger.info(f"Strategy 2 - Extracted JSON: {json_str[:200]}...")
                        parsed_json = json.loads(json_str)
                        logger.info("✓ Successfully parsed JSON using strategy 2 (square brackets)")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"✗ Strategy 2 failed: {e}")
            
            # Strategy 3: Try to parse entire response
            if not parsed_json:
                try:
                    logger.info(f"Strategy 3 - Trying to parse entire response")
                    parsed_json = json.loads(response)
                    logger.info("✓ Successfully parsed entire response as JSON")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"✗ Strategy 3 failed: {e}")
            
            # Strategy 4: Try to remove markdown code blocks
            if not parsed_json:
                try:
                    # Remove ```json and ``` markers
                    cleaned = response.replace('```json', '').replace('```', '').strip()
                    logger.info(f"Strategy 4 - Cleaned response: {cleaned[:200]}...")
                    parsed_json = json.loads(cleaned)
                    logger.info("✓ Successfully parsed JSON after removing markdown")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"✗ Strategy 4 failed: {e}")
            
            if parsed_json:
                return parsed_json
            
            # All strategies failed - log full response for analysis
            logger.error("=" * 80)
            logger.error("ALL JSON PARSING STRATEGIES FAILED")
            logger.error("Full response for analysis:")
            logger.error(response)
            logger.error("=" * 80)
            
            return {
                "error": "Failed to parse JSON response",
                "error_type": "json_decode_error",
                "raw_response": response[:500],
                "message": "The AI response was not in valid JSON format. Using fallback generation."
            }
        
        except Exception as e:
            logger.error(f"Structured output generation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "error": str(e),
                "error_type": "generation_error",
                "message": "Failed to generate structured output"
            }
    
    def explain_code(
        self,
        code: str,
        language: str = "english",
        difficulty: str = "intermediate"
    ) -> str:
        """
        Generate code explanation.
        
        Args:
            code: Code to explain
            language: Output language
            difficulty: Explanation difficulty level
            
        Returns:
            Code explanation
        """
        return self.generate_with_chain(
            chain_type="code_explanation",
            inputs={
                "code": code,
                "language": language,
                "difficulty": difficulty
            }
        )
    
    def debug_code(
        self,
        code: str,
        language: str = "english"
    ) -> str:
        """
        Analyze code for issues.
        
        Args:
            code: Code to debug
            language: Output language
            
        Returns:
            Debugging analysis
        """
        return self.generate_with_chain(
            chain_type="debugging",
            inputs={
                "code": code,
                "language": language
            }
        )
    
    def summarize_code(
        self,
        code: str,
        language: str = "english"
    ) -> str:
        """
        Generate code summary.
        
        Args:
            code: Code to summarize
            language: Output language
            
        Returns:
            Code summary
        """
        return self.generate_with_chain(
            chain_type="summary",
            inputs={
                "code": code,
                "language": language
            }
        )
    
    def generate_analogy(
        self,
        concept: str,
        language: str = "english"
    ) -> str:
        """
        Generate culturally relevant analogy.
        
        Args:
            concept: Programming concept
            language: Output language
            
        Returns:
            Analogy explanation
        """
        return self.generate_with_chain(
            chain_type="analogy_generation",
            inputs={
                "concept": concept,
                "language": language
            }
        )
