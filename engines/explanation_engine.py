"""Explanation engine for generating code explanations with analogies."""
import time
import hashlib
from dataclasses import dataclass
from typing import List
from ai.langchain_orchestrator import LangChainOrchestrator
from utils.performance_metrics import record_metric
import logging
import streamlit as st

logger = logging.getLogger(__name__)


@dataclass
class CodeExample:
    """Represents a code example."""
    description: str
    code: str
    output: str


@dataclass
class Explanation:
    """Complete code explanation."""
    summary: str
    detailed_explanation: str
    analogies: List[str]
    examples: List[CodeExample]
    key_concepts: List[str]


class ExplanationEngine:
    """Generates code explanations with analogies using LLM."""
    
    def __init__(self, langchain_orchestrator: LangChainOrchestrator):
        """Initialize with LangChain orchestrator."""
        self.orchestrator = langchain_orchestrator
        self.framework_patterns = self._initialize_framework_patterns()
        self._ensure_explanation_cache()
    
    def _ensure_explanation_cache(self):
        """Ensure explanation cache exists in session state."""
        if "explanation_cache" not in st.session_state:
            st.session_state.explanation_cache = {}
    
    def _generate_explanation_hash(
        self,
        code: str,
        context: str,
        language: str,
        difficulty: str
    ) -> str:
        """Generate hash for explanation request."""
        content = f"{code}:{context}:{language}:{difficulty}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _get_cached_explanation(self, exp_hash: str):
        """Get cached explanation if available."""
        self._ensure_explanation_cache()
        return st.session_state.explanation_cache.get(exp_hash)
    
    def _cache_explanation(self, exp_hash: str, explanation: Explanation) -> None:
        """Cache explanation result."""
        self._ensure_explanation_cache()
        
        # Limit cache size to 30 entries
        if len(st.session_state.explanation_cache) >= 30:
            # Remove oldest entry
            oldest_key = next(iter(st.session_state.explanation_cache))
            del st.session_state.explanation_cache[oldest_key]
        
        st.session_state.explanation_cache[exp_hash] = explanation
    
    def _initialize_framework_patterns(self) -> dict:
        """Initialize framework detection patterns and insights."""
        return {
            "react": {
                "patterns": ["useState", "useEffect", "useContext", "React.Component", "jsx", "tsx"],
                "insights": [
                    "React uses a component-based architecture - like building with LEGO blocks",
                    "State management in React is like keeping track of items in a shopping cart",
                    "React hooks are like special tools that give components superpowers",
                    "Virtual DOM is like having a draft copy before making final changes"
                ],
                "best_practices": [
                    "Keep components small and focused (Single Responsibility)",
                    "Use functional components with hooks for modern React",
                    "Avoid prop drilling - use Context API or state management",
                    "Memoize expensive computations with useMemo"
                ],
                "indian_context": "Think of React components like different counters at a railway station - each handles specific tasks independently"
            },
            "nodejs": {
                "patterns": ["require(", "express", "app.listen", "module.exports", "async/await"],
                "insights": [
                    "Node.js is event-driven - like a restaurant taking multiple orders simultaneously",
                    "Non-blocking I/O means Node doesn't wait - like a chai wallah serving multiple customers",
                    "Express.js routes are like different windows at a government office",
                    "Middleware functions are like security checkpoints at an airport"
                ],
                "best_practices": [
                    "Use async/await for cleaner asynchronous code",
                    "Implement proper error handling middleware",
                    "Use environment variables for configuration",
                    "Follow REST API conventions for endpoints"
                ],
                "indian_context": "Node.js event loop is like a traffic signal managing multiple lanes efficiently"
            },
            "express": {
                "patterns": ["app.get(", "app.post(", "req.body", "res.json(", "middleware"],
                "insights": [
                    "Express middleware is like a chain of security checks at an event",
                    "Routes define endpoints - like different departments in an office",
                    "Request/Response cycle is like ordering and receiving food at a restaurant",
                    "Error handling middleware catches issues - like a safety net"
                ],
                "best_practices": [
                    "Use router for organizing routes",
                    "Implement input validation middleware",
                    "Use helmet for security headers",
                    "Structure code with MVC pattern"
                ],
                "indian_context": "Express routes are like different counters at a post office - each serves a specific purpose"
            },
            "mongodb": {
                "patterns": ["mongoose", "Schema", "Model", "find(", "aggregate(", "ObjectId"],
                "insights": [
                    "MongoDB stores documents - like files in folders, not tables",
                    "Collections are like different sections in a library",
                    "Schemas define structure - like forms at a bank",
                    "Aggregation pipeline is like a factory assembly line processing data"
                ],
                "best_practices": [
                    "Index frequently queried fields",
                    "Use aggregation for complex queries",
                    "Implement proper schema validation",
                    "Avoid deeply nested documents"
                ],
                "indian_context": "MongoDB collections are like different registers at a school - students, teachers, classes"
            },
            "aws": {
                "patterns": ["boto3", "lambda", "s3", "dynamodb", "ec2", "aws-sdk"],
                "insights": [
                    "AWS Lambda is serverless - like renting a taxi only when needed",
                    "S3 buckets store files - like a digital locker system",
                    "DynamoDB is NoSQL - like a flexible filing system",
                    "EC2 instances are virtual servers - like renting office space"
                ],
                "best_practices": [
                    "Use IAM roles for secure access",
                    "Implement proper error handling and retries",
                    "Monitor costs with CloudWatch",
                    "Use environment variables for configuration"
                ],
                "indian_context": "AWS services are like different government departments - each specialized for specific tasks"
            },
            "python": {
                "patterns": ["def ", "class ", "import ", "__init__", "self."],
                "insights": [
                    "Python is readable - code should be like a well-written story",
                    "List comprehensions are concise - like shorthand notation",
                    "Decorators add functionality - like gift wrapping",
                    "Generators are memory-efficient - like streaming vs downloading"
                ],
                "best_practices": [
                    "Follow PEP 8 style guidelines",
                    "Use virtual environments for dependencies",
                    "Write docstrings for functions and classes",
                    "Use type hints for better code clarity"
                ],
                "indian_context": "Python's simplicity is like Hindi - easy to learn, powerful to use"
            },
            "javascript": {
                "patterns": ["function", "const", "let", "=>", "Promise", "async"],
                "insights": [
                    "JavaScript is single-threaded but asynchronous - like a chef multitasking",
                    "Promises handle async operations - like getting a token at a bank",
                    "Closures preserve scope - like keeping secrets in a diary",
                    "Event loop manages execution - like a traffic controller"
                ],
                "best_practices": [
                    "Use const/let instead of var",
                    "Prefer async/await over callbacks",
                    "Use strict equality (===)",
                    "Handle errors in promises"
                ],
                "indian_context": "JavaScript callbacks are like getting a callback from customer service - you don't wait on hold"
            }
        }
    
    def detect_frameworks(self, code: str) -> List[str]:
        """
        Detect frameworks and technologies used in code.
        
        Args:
            code: Code to analyze
            
        Returns:
            List of detected frameworks
        """
        detected = []
        code_lower = code.lower()
        
        for framework, config in self.framework_patterns.items():
            for pattern in config["patterns"]:
                if pattern.lower() in code_lower:
                    detected.append(framework)
                    break
        
        return detected
    
    def get_framework_insights(self, frameworks: List[str]) -> dict:
        """
        Get insights for detected frameworks.
        
        Args:
            frameworks: List of framework names
            
        Returns:
            Dictionary of insights by framework
        """
        insights = {}
        
        for framework in frameworks:
            if framework in self.framework_patterns:
                insights[framework] = {
                    "insights": self.framework_patterns[framework]["insights"],
                    "best_practices": self.framework_patterns[framework]["best_practices"],
                    "indian_context": self.framework_patterns[framework]["indian_context"]
                }
        
        return insights
    
    def explain_code(
        self,
        code: str,
        context: str = "",
        language: str = "english",
        difficulty: str = "intermediate"
    ) -> Explanation:
        """
        Generate explanation for code snippet with caching.
        
        Args:
            code: Code to explain
            context: Additional context
            language: Output language
            difficulty: Explanation difficulty level
            
        Returns:
            Complete explanation
        """
        start_time = time.time()
        
        try:
            # Check cache
            exp_hash = self._generate_explanation_hash(code, context, language, difficulty)
            cached_explanation = self._get_cached_explanation(exp_hash)
            
            if cached_explanation is not None:
                duration = time.time() - start_time
                record_metric("explanation_cached", duration, {
                    "cache_hit": True,
                    "code_length": len(code),
                    "language": language
                })
                logger.info(f"Cache hit for explanation - returned in {duration:.3f}s")
                return cached_explanation
            
            # Cache miss - generate explanation
            # Detect frameworks
            frameworks = self.detect_frameworks(code)
            framework_insights = self.get_framework_insights(frameworks)
            
            # Build enhanced context with framework insights
            enhanced_context = context
            if framework_insights:
                enhanced_context += "\n\nDetected Technologies: " + ", ".join(frameworks)
                for fw, insights in framework_insights.items():
                    enhanced_context += f"\n\n{fw.upper()} Context: {insights['indian_context']}"
            
            # Generate main explanation (uses LLM caching internally)
            explanation_text = self.orchestrator.explain_code(
                code=code,
                language=language,
                difficulty=difficulty
            )
            
            # Add framework-specific insights to explanation
            if framework_insights:
                explanation_text += "\n\n### Framework-Specific Insights:\n"
                for fw, insights in framework_insights.items():
                    explanation_text += f"\n**{fw.upper()}:**\n"
                    explanation_text += f"- {insights['insights'][0]}\n"
                    if insights['best_practices']:
                        explanation_text += f"- Best Practice: {insights['best_practices'][0]}\n"
            
            # Extract key concepts (simplified)
            key_concepts = self._extract_key_concepts(code)
            
            # Add detected frameworks to key concepts
            key_concepts.extend([fw.upper() for fw in frameworks])
            
            # Generate analogy
            if key_concepts:
                analogy = self.generate_analogy(key_concepts[0], language)
            else:
                analogy = "No specific analogy generated"
            
            # Add framework-specific analogies
            analogies = [analogy]
            for fw, insights in framework_insights.items():
                analogies.append(insights['indian_context'])
            
            # Create examples (simplified)
            examples = self._generate_examples(code)
            
            explanation = Explanation(
                summary=explanation_text[:200] + "..." if len(explanation_text) > 200 else explanation_text,
                detailed_explanation=explanation_text,
                analogies=analogies[:3],  # Limit to 3 analogies
                examples=examples,
                key_concepts=key_concepts[:8]  # Limit to 8 concepts
            )
            
            # Cache the result
            self._cache_explanation(exp_hash, explanation)
            
            # Record metrics
            duration = time.time() - start_time
            record_metric("explanation_generated", duration, {
                "cache_hit": False,
                "code_length": len(code),
                "language": language,
                "num_frameworks": len(frameworks)
            })
            
            logger.info(f"Explanation generated in {duration:.3f}s")
            return explanation
        
        except Exception as e:
            duration = time.time() - start_time
            record_metric("explanation_error", duration, {
                "error": str(e)
            })
            logger.error(f"Explanation generation failed: {e}")
            return self._get_fallback_explanation(code)
    
    def generate_analogy(self, concept: str, language: str = "english") -> str:
        """
        Generate culturally relevant analogy for concept.
        
        Args:
            concept: Programming concept
            language: Output language
            
        Returns:
            Analogy explanation
        """
        try:
            return self.orchestrator.generate_analogy(concept, language)
        except Exception as e:
            logger.error(f"Analogy generation failed: {e}")
            return f"Think of {concept} like organizing items in a chai stall - everything has its place!"
    
    def simplify_explanation(
        self,
        explanation: str,
        language: str = "english"
    ) -> str:
        """
        Simplify existing explanation to more basic level.
        
        Args:
            explanation: Original explanation
            language: Output language
            
        Returns:
            Simplified explanation
        """
        try:
            prompt = f"""Simplify this explanation for a beginner:

{explanation}

Make it very simple and easy to understand, using everyday language."""
            
            return self.orchestrator.generate_completion(prompt)
        except Exception as e:
            logger.error(f"Simplification failed: {e}")
            return "Simplified version: " + explanation[:100] + "..."
    
    def explain_with_examples(
        self,
        code: str,
        language: str = "english"
    ) -> Explanation:
        """
        Generate explanation with code examples.
        
        Args:
            code: Code to explain
            language: Output language
            
        Returns:
            Explanation with examples
        """
        return self.explain_code(code, "", language, "intermediate")
    
    def _extract_key_concepts(self, code: str) -> List[str]:
        """Extract key programming concepts from code."""
        concepts = []
        
        # Simple keyword-based extraction
        if "class " in code:
            concepts.append("Object-Oriented Programming")
        if "def " in code or "function " in code:
            concepts.append("Functions")
        if "async " in code or "await " in code:
            concepts.append("Asynchronous Programming")
        if "try:" in code or "except" in code:
            concepts.append("Error Handling")
        if "import " in code:
            concepts.append("Modules and Imports")
        if "for " in code or "while " in code:
            concepts.append("Loops")
        if "if " in code:
            concepts.append("Conditional Logic")
        
        return concepts[:5]  # Limit to 5 concepts
    
    def _generate_examples(self, code: str) -> List[CodeExample]:
        """Generate simple code examples."""
        examples = []
        
        # Add a basic example
        if "def " in code:
            examples.append(CodeExample(
                description="Basic function usage",
                code="# Call the function\nresult = function_name(arg1, arg2)",
                output="# Returns the computed result"
            ))
        
        return examples
    
    def _get_fallback_explanation(self, code: str) -> Explanation:
        """Generate fallback explanation when AI fails."""
        return Explanation(
            summary="This code performs specific operations. Enable AWS Bedrock for detailed AI analysis.",
            detailed_explanation=f"Code analysis:\n\n{code[:200]}...\n\nConfigure AWS credentials for full AI-powered explanations.",
            analogies=["Think of code like a recipe - each line is a step to achieve the final result!"],
            examples=[],
            key_concepts=self._extract_key_concepts(code)
        )
