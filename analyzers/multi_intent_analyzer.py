"""
Multi-Intent Analyzer for handling complex user queries with multiple intents.

This module can parse and analyze queries with multiple learning goals.
"""

import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Intent:
    """Single intent extracted from user query."""
    intent_text: str
    intent_type: str  # 'how', 'what', 'why', 'where', 'explain', 'show'
    keywords: List[str]
    priority: int  # 1 (high) to 3 (low)


@dataclass
class QueryUnderstanding:
    """Structured understanding for one user turn."""
    normalized_query: str
    intents: List[Intent]
    response_profile: Dict[str, Any]
    used_chat_context: bool = False


class MultiIntentAnalyzer:
    """Analyzes user queries to extract multiple intents."""

    QUESTION_STARTERS = (
        "what", "why", "how", "where", "when", "who", "which",
        "explain", "show", "compare", "list", "describe", "can", "could",
    )
    CONTEXT_WORDS = {
        "repo", "repository", "codebase", "code", "project", "app",
        "this", "that", "these", "those", "here", "there",
        "use", "used", "using", "purpose", "mean", "means",
    }
    GENERIC_FRAGMENTS = {
        "what", "why", "how", "where", "when", "who", "which",
        "this repo", "in this repo", "this repository", "in this repository",
        "this codebase", "in this codebase", "why we use", "what is this repo",
    }
    SUBJECT_STOP_WORDS = {
        "tell", "show", "explain", "describe", "give", "help", "learn",
        "understand", "know", "about", "please", "kindly", "need", "want",
        "should", "must", "could", "would", "can", "use", "using", "used",
        "have", "has", "had", "do", "does", "did", "are", "is", "was", "were",
        "me", "my", "our", "your", "their", "there", "here",
    }
    FOLLOWUP_PREFIXES = (
        "and ",
        "also ",
        "then ",
        "so ",
        "what about",
        "how about",
        "why",
        "how",
        "where",
    )
    FOLLOWUP_REFERENCES = {
        "that", "it", "this", "these", "those", "them", "same",
    }
    BROAD_OVERVIEW_CUES = (
        "about",
        "overview",
        "summary",
        "flow",
        "architecture",
        "high level",
        "big picture",
        "end to end",
        "purpose",
    )
    DEPTH_CUES = {
        "brief": ("brief", "short", "quick", "tldr", "one line", "in short"),
        "deep": ("detailed", "detail", "deep", "in depth", "thorough", "step by step", "comprehensive"),
    }
    FORMAT_CUES = {
        "steps": ("step by step", "steps", "walkthrough"),
        "bullets": ("bullet", "list", "points"),
    }
    EXAMPLE_CUES = (
        "example",
        "examples",
        "sample",
        "use case",
        "real world",
        "snippet",
    )
    
    def __init__(self, langchain_orchestrator):
        """
        Initialize multi-intent analyzer.
        
        Args:
            langchain_orchestrator: LangChainOrchestrator for AI operations
        """
        self.orchestrator = langchain_orchestrator
    
    def analyze_query(self, user_query: str) -> List[Intent]:
        """
        Analyze user query to extract multiple intents.
        
        Args:
            user_query: User's natural language query
            
        Returns:
            List of Intent objects
        """
        try:
            logger.info(f"Analyzing query for multiple intents: {user_query}")

            rule_based_intents = self._extract_intents_rule_based(user_query)
            if rule_based_intents:
                logger.info("Using deterministic intent decomposition")
                return rule_based_intents

            # AI fallback is only used if deterministic decomposition fails.
            intents = self._sanitize_intents(
                self._extract_intents_with_ai(user_query),
                user_query
            )
            if not intents:
                intents = [self._build_single_intent(user_query)]

            logger.info(f"Extracted {len(intents)} intents")
            return intents
        
        except Exception as e:
            logger.error(f"Intent analysis failed: {e}")
            return [self._build_single_intent(user_query)]

    def understand_query(
        self,
        user_query: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
    ) -> QueryUnderstanding:
        """
        Build a generalized understanding of the user turn.
        Includes follow-up resolution and response-style preferences.
        """
        cleaned_query = self._strip_conversational_prefix(self._normalize_text(user_query))
        resolved_query = cleaned_query
        used_context = False

        if self._is_followup_query(cleaned_query):
            previous_user_query = self._latest_user_query(chat_history or [])
            if previous_user_query:
                resolved_query = self._resolve_followup_with_previous(cleaned_query, previous_user_query)
                used_context = (resolved_query != cleaned_query)

        intents = self.analyze_query(resolved_query)
        response_profile = self._detect_response_profile(cleaned_query)

        return QueryUnderstanding(
            normalized_query=resolved_query,
            intents=intents,
            response_profile=response_profile,
            used_chat_context=used_context,
        )
    
    def _extract_intents_with_ai(self, query: str) -> List[Intent]:
        """
        Use AI to extract multiple intents from query.
        
        Args:
            query: User query
            
        Returns:
            List of Intent objects
        """
        try:
            prompt = f"""Analyze this user query and extract all distinct learning intents/questions.
For each intent, identify:
1. The specific question or goal
2. The type (how/what/why/where/explain/show)
3. Key technical terms or concepts
4. Priority (1=high, 2=medium, 3=low)

User Query: "{query}"

Respond in this format:
INTENT 1: [intent text]
TYPE: [type]
KEYWORDS: [keyword1, keyword2, ...]
PRIORITY: [1-3]

INTENT 2: ...

Extract all intents:"""
            
            response = self.orchestrator.generate_completion(prompt, max_tokens=500)
            if response is None:
                return []
            if not isinstance(response, str):
                response = str(response)
            
            # Parse response
            intents = self._parse_intent_response(response)
            
            return intents

        except Exception as e:
            logger.warning(f"AI intent extraction failed: {e}")
            return []

    def _extract_intents_rule_based(self, user_query: str) -> List[Intent]:
        """Deterministically split and sanitize query into meaningful intents."""
        query = self._strip_conversational_prefix(self._normalize_text(user_query))
        if not query:
            return []

        segments = self._decompose_query(query)
        if len(segments) > 1:
            segments = self._resolve_followup_references(segments)
            segments = self._merge_related_segments(segments)

        intents = []
        for index, segment in enumerate(segments, start=1):
            intent_text = self._normalize_text(segment)
            if not intent_text:
                continue
            intents.append(Intent(
                intent_text=intent_text,
                intent_type=self._detect_intent_type(intent_text),
                keywords=self._extract_keywords(intent_text),
                priority=min(index, 3)
            ))

        return self._sanitize_intents(intents, query)
    
    def _parse_intent_response(self, response: str) -> List[Intent]:
        """
        Parse AI response into Intent objects.
        
        Args:
            response: AI response text
            
        Returns:
            List of Intent objects
        """
        intents = []
        
        try:
            # Split by INTENT markers
            intent_blocks = re.split(r"\bINTENT\s+", response, flags=re.IGNORECASE)

            for block in intent_blocks[1:]:  # Skip first empty split
                lines = block.strip().split('\n')
                
                intent_text = ""
                intent_type = "explain"
                keywords = []
                priority = 2
                
                for line in lines:
                    line = line.strip()

                    if re.match(r"^\d+\s*:\s*", line):
                        intent_text = line.split(':', 1)[1].strip()
                    elif line.upper().startswith('TYPE:'):
                        intent_type = line.split(':', 1)[1].strip().lower()
                    elif line.upper().startswith('KEYWORDS:'):
                        kw_text = line.split(':', 1)[1].strip()
                        keywords = [k.strip() for k in kw_text.split(',')]
                    elif line.upper().startswith('PRIORITY:'):
                        try:
                            priority = int(line.split(':', 1)[1].strip()[0])
                        except Exception:
                            priority = 2
                    elif ':' in line and not line.upper().startswith('INTENT'):
                        # This is the intent text
                        intent_text = line.split(':', 1)[1].strip()
                
                if intent_text:
                    intents.append(Intent(
                        intent_text=intent_text,
                        intent_type=intent_type,
                        keywords=keywords,
                        priority=priority
                    ))
        
        except Exception as e:
            logger.warning(f"Failed to parse intent response: {e}")

        return intents

    def _decompose_query(self, query: str) -> List[str]:
        """Split a query into meaningful intent segments."""
        sentence_parts = [
            self._normalize_text(part)
            for part in re.split(r"[?\n;]+", query)
            if self._normalize_text(part)
        ]

        segments: List[str] = []
        starter_expr = "|".join(self.QUESTION_STARTERS)
        split_pattern = re.compile(
            rf"\s+(?:and|also|plus|then)\s+(?=(?:{starter_expr})\b)",
            flags=re.IGNORECASE
        )

        for part in sentence_parts:
            split_parts = [self._normalize_text(s) for s in re.split(split_pattern, part)]
            segments.extend(s for s in split_parts if s)

        if not segments:
            return [query]

        return segments

    def _resolve_followup_references(self, segments: List[str]) -> List[str]:
        """
        Resolve follow-up pronouns (that/it/this) to the first segment topic.
        Example: "why we use that" -> "why we use shimmer"
        """
        if not segments:
            return segments

        primary_subject = self._extract_primary_subject(segments[0])
        if not primary_subject:
            return segments

        resolved = [segments[0]]
        for segment in segments[1:]:
            if re.search(r"\b(that|it|them|those|these)\b", segment, flags=re.IGNORECASE):
                segment = re.sub(
                    r"\b(that|it|them|those|these)\b",
                    primary_subject,
                    segment,
                    count=1,
                    flags=re.IGNORECASE,
                )
            resolved.append(self._normalize_text(segment))

        return resolved

    def _merge_related_segments(self, segments: List[str]) -> List[str]:
        """
        Merge follow-up clauses into one intent when they refer to same subject.
        Example: "what is shimmer ... and why should we use shimmer"
        becomes one cohesive intent.
        """
        if len(segments) < 2:
            return segments

        merged = [segments[0]]
        subject = self._extract_primary_subject(segments[0]).lower()

        for segment in segments[1:]:
            seg_norm = self._normalize_text(segment)
            seg_lower = seg_norm.lower()
            should_merge = False

            if subject and subject in seg_lower:
                # Follow-up reasoning/usage questions should stay with primary concept.
                if re.match(r"^(why|how|explain|describe|show|where)\b", seg_lower):
                    should_merge = True

            if should_merge:
                merged[-1] = self._normalize_text(f"{merged[-1]} and {seg_norm}")
            else:
                merged.append(seg_norm)

        return merged

    def _sanitize_intents(self, intents: List[Intent], original_query: str) -> List[Intent]:
        """Remove noisy generic intents and keep only query-relevant intents."""
        if not intents:
            return []

        normalized_query = self._normalize_text(original_query).lower()
        anchor_terms = {
            term for term in self._extract_keywords(normalized_query)
            if term not in self.CONTEXT_WORDS
        }

        cleaned: List[Intent] = []
        seen = set()

        for intent in intents:
            text = self._normalize_text(intent.intent_text)
            if not text:
                continue

            text_lower = text.lower()
            if text_lower in self.GENERIC_FRAGMENTS:
                continue
            if re.fullmatch(r"(what|why|how|where|when|who|which)(\s+\w+){0,2}", text_lower):
                continue
            if re.fullmatch(r"(in\s+)?this\s+(repo|repository|codebase)", text_lower):
                continue

            if anchor_terms and not any(anchor in text_lower for anchor in anchor_terms):
                continue

            if text_lower in seen:
                continue
            seen.add(text_lower)

            cleaned.append(Intent(
                intent_text=text,
                intent_type=intent.intent_type or self._detect_intent_type(text),
                keywords=intent.keywords or self._extract_keywords(text),
                priority=min(len(cleaned) + 1, 3)
            ))

        if cleaned:
            return cleaned[:3]

        fallback = self._normalize_text(original_query)
        return [self._build_single_intent(fallback)] if fallback else []

    def _detect_intent_type(self, text: str) -> str:
        """Infer intent type from sentence prefix."""
        text_lower = self._normalize_text(text).lower()
        for intent_type in ("how", "what", "why", "where", "show"):
            if text_lower.startswith(intent_type):
                return intent_type
        if text_lower.startswith(("explain", "describe", "compare", "list")):
            return "explain"
        return "explain"

    def _extract_primary_subject(self, text: str) -> str:
        """Pick the best noun-like anchor from the first query segment."""
        normalized = self._normalize_text(text).lower()

        # Strong signal: "what is X", "explain X", "describe X"
        direct_subject_patterns = [
            r"\bwhat\s+(?:is|are)\s+([a-zA-Z_][\w-]*)\b",
            r"\b(?:explain|describe|define)\s+([a-zA-Z_][\w-]*)\b",
        ]
        for pattern in direct_subject_patterns:
            match = re.search(pattern, normalized)
            if match:
                candidate = match.group(1).strip()
                if candidate and candidate not in self.CONTEXT_WORDS and candidate not in self.SUBJECT_STOP_WORDS:
                    return candidate

        keywords = [
            keyword for keyword in self._extract_keywords(text)
            if keyword not in self.CONTEXT_WORDS and keyword not in self.SUBJECT_STOP_WORDS
        ]
        return keywords[0] if keywords else ""

    def _normalize_text(self, text: str) -> str:
        """Normalize spacing and trailing punctuation for stable parsing."""
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text).strip()
        return text.strip(" ,.")

    def _strip_conversational_prefix(self, text: str) -> str:
        """Remove conversational lead-ins that are not part of technical intent."""
        if not text:
            return ""
        cleaned = text
        prefixes = (
            r"^(please\s+)?tell\s+me\s+",
            r"^(please\s+)?can\s+you\s+",
            r"^(please\s+)?could\s+you\s+",
            r"^(please\s+)?would\s+you\s+",
            r"^(please\s+)?help\s+me\s+",
        )
        for prefix in prefixes:
            cleaned = re.sub(prefix, "", cleaned, flags=re.IGNORECASE)
        return self._normalize_text(cleaned)

    def _build_single_intent(self, user_query: str) -> Intent:
        """Build a single high-priority intent from full query."""
        cleaned_query = self._strip_conversational_prefix(self._normalize_text(user_query))
        return Intent(
            intent_text=cleaned_query,
            intent_type=self._detect_intent_type(cleaned_query),
            keywords=self._extract_keywords(cleaned_query),
            priority=1
        )

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'should', 'could', 'may', 'might', 'must', 'can', 'i', 'you', 'he',
            'she', 'it', 'we', 'they', 'me', 'my', 'our', 'your', 'what', 'which', 'who', 'when', 'where',
            'why', 'how', 'this', 'that', 'these', 'those', 'about', 'repo',
            'repository', 'codebase', 'tell', 'please'
        }

        words = text.lower().split()
        keywords = [w.strip('.,!?;:()[]{}') for w in words if w.lower() not in stop_words and len(w) > 2]

        return keywords

    def _is_followup_query(self, query: str) -> bool:
        """Detect likely follow-up turns that depend on previous context."""
        query_lower = self._normalize_text(query).lower()
        if not query_lower:
            return False

        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_:-]*", query_lower)
        has_followup_prefix = any(query_lower.startswith(prefix) for prefix in self.FOLLOWUP_PREFIXES)
        has_reference_token = any(token in self.FOLLOWUP_REFERENCES for token in tokens)

        informative_tokens = [
            token for token in tokens
            if token not in self.FOLLOWUP_REFERENCES
            and token not in self.CONTEXT_WORDS
            and token not in self.SUBJECT_STOP_WORDS
            and token not in self.QUESTION_STARTERS
            and len(token) > 2
        ]

        # Do not treat broad, self-contained prompts as follow-ups even if they contain "this/that".
        if self._is_self_contained_overview_query(query_lower, informative_tokens):
            return False

        if has_followup_prefix and len(informative_tokens) <= 6:
            return True

        if has_reference_token and len(tokens) <= 10 and len(informative_tokens) <= 2:
            return True

        # Very short prompts are frequently elliptical follow-ups.
        return len(tokens) <= 4 and len(informative_tokens) == 0

    def _is_self_contained_overview_query(self, query: str, informative_tokens: List[str]) -> bool:
        """True when query is a fresh broad request, not an elliptical follow-up."""
        if not query:
            return False
        has_overview_cue = any(cue in query for cue in self.BROAD_OVERVIEW_CUES)
        if not has_overview_cue:
            return False
        return len(informative_tokens) >= 2

    def _latest_user_query(self, chat_history: List[Dict[str, Any]]) -> str:
        """Get latest user turn text from chat history."""
        for message in reversed(chat_history):
            if not isinstance(message, dict):
                continue
            if message.get("role") != "user":
                continue
            content = self._normalize_text(str(message.get("content", "")))
            if content:
                return content
        return ""

    def _resolve_followup_with_previous(self, followup_query: str, previous_query: str) -> str:
        """Resolve follow-up references by reusing previous query subject."""
        followup = self._normalize_text(followup_query)
        previous = self._normalize_text(previous_query)
        if not followup or not previous:
            return followup

        subject = self._extract_primary_subject(previous)
        resolved = followup
        if subject and re.search(r"\b(that|it|this|these|those|them|same)\b", resolved, flags=re.IGNORECASE):
            resolved = re.sub(
                r"\b(that|it|this|these|those|them|same)\b",
                subject,
                resolved,
                count=1,
                flags=re.IGNORECASE,
            )

        # If still short and connective, append to previous to preserve intent context.
        token_count = len(re.findall(r"[a-zA-Z_][a-zA-Z0-9_:-]*", resolved))
        if token_count <= 7 and any(resolved.lower().startswith(prefix) for prefix in self.FOLLOWUP_PREFIXES):
            suffix = re.sub(r"^(and|also|then|so)\s+", "", resolved, flags=re.IGNORECASE)
            merged = f"{previous} and {suffix}"
            return self._normalize_text(merged)

        return self._normalize_text(resolved)

    def _detect_response_profile(self, query: str) -> Dict[str, Any]:
        """Infer response style preferences from user wording."""
        query_lower = self._normalize_text(query).lower()

        depth = "standard"
        if any(cue in query_lower for cue in self.DEPTH_CUES["brief"]):
            depth = "brief"
        if any(cue in query_lower for cue in self.DEPTH_CUES["deep"]):
            depth = "deep"

        fmt = "narrative"
        if any(cue in query_lower for cue in self.FORMAT_CUES["steps"]):
            fmt = "steps"
        elif any(cue in query_lower for cue in self.FORMAT_CUES["bullets"]):
            fmt = "bullets"

        include_examples = any(cue in query_lower for cue in self.EXAMPLE_CUES)

        return {
            "depth": depth,
            "format": fmt,
            "include_examples": include_examples,
        }
