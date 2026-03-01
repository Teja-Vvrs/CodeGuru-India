"""
Semantic Code Search using AI embeddings and similarity matching.

This module provides intelligent code search capabilities to find relevant files
based on user intent, not just keyword matching.
"""

import logging
import os
import re
import json
from difflib import SequenceMatcher
from typing import List, Dict, Any, Tuple, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CodeChunk:
    """Represents a chunk of code with metadata."""
    file_path: str
    content: str
    start_line: int
    end_line: int
    language: str
    chunk_type: str  # 'class', 'function', 'module', 'block'
    name: str
    relevance_score: float = 0.0


@dataclass
class CodeSymbol:
    """Lightweight symbol record extracted from source text."""
    file_path: str
    name: str
    kind: str  # function | class | component | route | endpoint
    start_line: int
    end_line: int
    signature: str = ""


@dataclass
class RepositoryMap:
    """Repository map used to route retrieval to relevant file groups."""
    entry_points: Set[str] = field(default_factory=set)
    routing_files: Set[str] = field(default_factory=set)
    api_files: Set[str] = field(default_factory=set)
    state_files: Set[str] = field(default_factory=set)
    ui_files: Set[str] = field(default_factory=set)
    data_files: Set[str] = field(default_factory=set)
    debug_files: Set[str] = field(default_factory=set)
    config_files: Set[str] = field(default_factory=set)
    symbol_to_files: Dict[str, Set[str]] = field(default_factory=dict)


class SemanticCodeSearch:
    """Semantic search engine for code repositories."""

    OVERVIEW_PATTERNS = (
        "key feature",
        "main feature",
        "major feature",
        "what are the features",
        "key features are",
        "feature of this codebase",
        "what this codebase does",
        "what does this app do",
        "overall functionality",
        "high level",
        "overview",
        "capabilities",
    )
    BROAD_CONTEXT_TERMS = (
        "codebase",
        "repo",
        "repository",
        "project",
        "application",
        "app",
        "system",
    )
    BROAD_OVERVIEW_CUES = (
        "about",
        "overview",
        "summary",
        "high level",
        "big picture",
        "purpose",
        "what does",
        "what is",
        "explain",
        "tell me",
    )
    CONFIG_PATTERNS = (
        "config",
        "configuration",
        "environment",
        "env",
        "build",
        "webpack",
        "vite",
        "tsconfig",
        "package json",
        "deployment",
    )
    LOCATION_PATTERNS = (
        "which file",
        "where is",
        "where are",
        "where does",
        "defined in",
        "implemented in",
        "located",
        "location",
        "is there",
        "exist",
        "file exists",
    )
    COMPARISON_PATTERNS = (
        "compare",
        "difference",
        "different",
        "vs",
        "versus",
        "better than",
        "contrast",
    )
    DEBUG_PATTERNS = (
        "error",
        "bug",
        "issue",
        "not working",
        "failing",
        "fails",
        "fix",
        "exception",
        "traceback",
        "crash",
    )
    NOISE_FILE_HINTS = (
        "config",
        "settings",
        "constant",
        "types",
        "schema",
        ".env",
        "package.json",
        "tsconfig",
        "webpack",
        "vite",
        "babel",
        "eslint",
        "prettier",
    )
    FEATURE_FILE_HINTS = (
        "router",
        "route",
        "page",
        "component",
        "screen",
        "view",
        "layout",
        "service",
        "api",
        "controller",
        "store",
        "state",
        "hook",
    )
    LOW_SIGNAL_KEYWORDS = {
        "tell",
        "actually",
        "please",
        "give",
        "describe",
        "summarize",
        "summary",
        "high",
        "level",
        "system",
        "implementation",
        "implement",
        "implemented",
        "use",
        "used",
        "using",
        "explain",
        "about",
        "overview",
        "details",
        "detail",
        "code",
        "codebase",
        "repo",
        "repository",
        "project",
        "application",
        "app",
        "feature",
        "features",
        "file",
        "files",
        "module",
        "modules",
        "functionality",
        "purpose",
        "works",
        "working",
    }
    AMBIGUOUS_QUERY_WORDS = {
        "this",
        "that",
        "it",
        "thing",
        "stuff",
        "module",
        "feature",
        "features",
        "part",
        "code",
        "repo",
        "repository",
        "codebase",
        "project",
        "app",
        "system",
        "about",
        "explain",
        "tell",
        "show",
        "help",
    }
    
    def __init__(self, langchain_orchestrator):
        """
        Initialize semantic search engine.
        
        Args:
            langchain_orchestrator: LangChainOrchestrator for AI operations
        """
        self.orchestrator = langchain_orchestrator
        self.code_chunks = []
        self.file_summaries = {}
        self.file_symbols: Dict[str, List[CodeSymbol]] = {}
        self.symbol_index: Dict[str, List[CodeSymbol]] = {}
        self.repository_map = RepositoryMap()
        self.rerank_cache: Dict[Tuple[str, Tuple[str, ...]], Dict[int, int]] = {}

    def clear_index(self) -> None:
        """Clear indexed chunks and summaries."""
        self.code_chunks = []
        self.file_summaries = {}
        self.file_symbols = {}
        self.symbol_index = {}
        self.repository_map = RepositoryMap()
        self.rerank_cache = {}
    
    def index_repository(self, repo_path: str, repo_analysis) -> None:
        """
        Index entire repository for semantic search.
        
        Args:
            repo_path: Path to repository
            repo_analysis: RepoAnalysis object
        """
        try:
            logger.info(f"Indexing repository: {repo_path}")
            
            self.code_chunks = []
            self.file_summaries = {}
            self.file_symbols = {}
            self.symbol_index = {}
            self.repository_map = RepositoryMap()
            
            # Get all code files
            all_files = []
            for files in repo_analysis.file_tree.values():
                all_files.extend(files)
            
            # Process each file
            for file_info in all_files:
                try:
                    file_path = os.path.join(repo_path, file_info.path)
                    
                    if not os.path.isfile(file_path):
                        continue
                    
                    # Read file content
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    symbols = self._extract_symbols(file_info.path, content, file_info.extension)
                    self.file_symbols[file_info.path] = symbols
                    self._add_to_symbol_index(symbols)
                    self._update_repository_map(file_info.path, content, symbols)

                    # Chunk the file
                    chunks = self._chunk_file(
                        file_info.path,
                        content,
                        file_info.extension,
                        symbols=symbols,
                    )
                    self.code_chunks.extend(chunks)
                    
                    # Generate file summary
                    summary = self._generate_file_summary(file_info.path, content)
                    self.file_summaries[file_info.path] = summary
                
                except Exception as e:
                    logger.warning(f"Failed to index file {file_info.path}: {e}")
                    continue
            
            logger.info(
                "Indexed %s chunks, %s symbols from %s files",
                len(self.code_chunks),
                sum(len(s) for s in self.file_symbols.values()),
                len(self.file_summaries),
            )
        
        except Exception as e:
            logger.error(f"Repository indexing failed: {e}")
    
    def search_by_intent(
        self,
        user_intent: str,
        top_k: int = 20
    ) -> List[CodeChunk]:
        """
        Search for relevant code chunks based on user intent.
        
        Args:
            user_intent: User's natural language query
            top_k: Number of top results to return
            
        Returns:
            List of relevant code chunks with scores
        """
        try:
            logger.info(f"Searching for intent: {user_intent}")
            logger.info(f"Total indexed chunks: {len(self.code_chunks)}")
            
            if not self.code_chunks:
                logger.warning("No code chunks indexed")
                return []

            signals = self.get_query_signals(user_intent)
            query_mode = signals["query_mode"]
            anchor_terms = signals["anchor_terms"]
            strict_mode = bool(signals["strict_mode"])

            candidate_chunks = self._route_chunks_via_repository_map(
                user_intent=user_intent,
                query_mode=query_mode,
                anchor_terms=anchor_terms,
            )
            if not candidate_chunks:
                if strict_mode and anchor_terms:
                    logger.warning("Repository map routing found no files for strict anchor query")
                    return []
                candidate_chunks = self.code_chunks
            else:
                candidate_chunks = self._augment_candidates_with_summary_files(
                    user_intent=user_intent,
                    candidate_chunks=candidate_chunks,
                )

            # Use AI to score relevance
            relevant_chunks = self._score_chunks_with_ai(user_intent, candidate_chunks, top_k)
            
            logger.info(f"Found {len(relevant_chunks)} relevant chunks")
            
            # If no chunks found, return top chunks only for non-strict broad modes.
            if not relevant_chunks and self.code_chunks:
                if strict_mode:
                    logger.warning("No grounded chunks found for strict query mode")
                    return []
                logger.warning("No relevant chunks found, returning top chunks")
                relevant_chunks = candidate_chunks[:min(top_k, len(candidate_chunks))]
                for chunk in relevant_chunks:
                    chunk.relevance_score = 0.5
            
            return relevant_chunks
        
        except Exception as e:
            logger.error(f"Semantic search failed: {e}", exc_info=True)
            return []

    def assess_grounding(self, user_intent: str, chunks: List[CodeChunk]) -> Dict[str, Any]:
        """
        Assess whether retrieved chunks are strongly grounded for the query.

        Returns:
            Dict with grounding flags and diagnostics.
        """
        query_mode = self._classify_query_mode(user_intent)
        keywords = self._extract_keywords(user_intent)
        anchor_terms = self._extract_anchor_terms(keywords, user_intent)
        strict_mode = self._is_strict_mode(
            query_mode,
            anchor_terms=anchor_terms,
            user_intent=user_intent,
        )

        if not chunks:
            return {
                "is_grounded": False,
                "query_mode": query_mode,
                "top_score": 0.0,
                "anchor_terms": anchor_terms,
                "anchor_coverage": 0,
                "reason": "no_chunks",
            }

        top_score = max(float(chunk.relevance_score or 0.0) for chunk in chunks)
        anchor_coverage = 0
        if anchor_terms:
            expanded = self._expand_query_keywords(anchor_terms)
            coverage = set()
            for chunk in chunks:
                content_lower = chunk.content.lower()
                path_lower = chunk.file_path.lower()
                for term in expanded:
                    if term and (term in content_lower or term in path_lower):
                        coverage.add(term)
            anchor_coverage = len(coverage)

        if strict_mode:
            min_score = 1.2
        elif query_mode == "overview":
            min_score = 0.25
        elif query_mode == "comparison":
            min_score = 0.35
        elif query_mode == "config":
            min_score = 0.4
        else:
            min_score = 0.6
        has_min_score = top_score >= min_score
        has_anchor = (anchor_coverage >= 1) if (strict_mode and anchor_terms) else True
        is_grounded = bool(has_min_score and has_anchor)

        reason = "ok"
        if not has_min_score:
            reason = "low_score"
        elif not has_anchor:
            reason = "missing_anchor"

        return {
            "is_grounded": is_grounded,
            "query_mode": query_mode,
            "top_score": top_score,
            "anchor_terms": anchor_terms,
            "anchor_coverage": anchor_coverage,
            "reason": reason,
        }
    
    def get_relevant_files(
        self,
        user_intent: str,
        top_k: int = 10
    ) -> List[Tuple[str, float, str]]:
        """
        Get relevant files based on intent.
        
        Args:
            user_intent: User's natural language query
            top_k: Number of files to return
            
        Returns:
            List of (file_path, relevance_score, summary) tuples
        """
        try:
            # Score files based on summaries
            file_scores = []
            
            for file_path, summary in self.file_summaries.items():
                score = self._calculate_relevance(user_intent, summary)
                file_scores.append((file_path, score, summary))
            
            # Sort by score
            file_scores.sort(key=lambda x: x[1], reverse=True)
            
            return file_scores[:top_k]
        
        except Exception as e:
            logger.error(f"File relevance calculation failed: {e}")
            return []

    def get_query_signals(self, user_intent: str) -> Dict[str, Any]:
        """Return reusable query signals for retrieval and clarity decisions."""
        query_mode = self._classify_query_mode(user_intent)
        keywords = self._extract_keywords(user_intent)
        anchor_terms = self._extract_anchor_terms(keywords, user_intent)
        strict_mode = self._is_strict_mode(
            query_mode,
            anchor_terms=anchor_terms,
            user_intent=user_intent,
        )
        return {
            "query_mode": query_mode,
            "keywords": keywords,
            "anchor_terms": anchor_terms,
            "strict_mode": strict_mode,
        }

    def analyze_query_clarity(self, user_intent: str) -> Dict[str, Any]:
        """
        Detect whether the query is too vague and should trigger a clarification prompt.
        Returns structured diagnostics and suggested focus areas.
        """
        signals = self.get_query_signals(user_intent)
        query = (user_intent or "").strip().lower()
        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_:-]*", query)
        non_generic = [
            token for token in tokens
            if token not in self.AMBIGUOUS_QUERY_WORDS
            and token not in self.LOW_SIGNAL_KEYWORDS
            and len(token) > 2
        ]
        has_file_ref = bool(
            re.search(
                r"[A-Za-z0-9_./-]+\.(?:jsx|tsx|py|js|ts|java|go|rb|php|cs|json|yaml|yml|toml)",
                query,
                flags=re.IGNORECASE,
            )
        )
        is_ambiguous = (
            not has_file_ref
            and signals["query_mode"] == "specific"
            and not signals["anchor_terms"]
            and len(non_generic) <= 1
            and len(tokens) <= 8
        )

        reason = "clear"
        if is_ambiguous:
            reason = "low_specificity"
        elif len(tokens) <= 2 and not signals["anchor_terms"]:
            reason = "too_short"

        return {
            "is_ambiguous": bool(is_ambiguous),
            "reason": reason,
            "query_mode": signals["query_mode"],
            "keywords": signals["keywords"],
            "anchor_terms": signals["anchor_terms"],
            "suggested_focus": self._suggest_clarification_targets(),
        }

    def _suggest_clarification_targets(self) -> List[str]:
        """Suggest meaningful focus options based on indexed repository map."""
        suggestions: List[str] = []
        repo_map = self.repository_map
        if repo_map.routing_files:
            suggestions.append("routing/navigation")
        if repo_map.api_files:
            suggestions.append("API/backend flow")
        if repo_map.state_files:
            suggestions.append("state management")
        if repo_map.ui_files:
            suggestions.append("UI/components")
        if repo_map.data_files:
            suggestions.append("database/models")
        if repo_map.debug_files:
            suggestions.append("errors/debug path")
        if not suggestions:
            suggestions = ["overall architecture", "specific file", "specific function/class"]
        return suggestions[:5]

    def _augment_candidates_with_summary_files(
        self,
        user_intent: str,
        candidate_chunks: List[CodeChunk],
    ) -> List[CodeChunk]:
        """Hybrid retrieval: merge route-based chunks with file-summary relevance chunks."""
        if not candidate_chunks or not self.file_summaries:
            return candidate_chunks

        summary_scores: List[Tuple[str, float]] = []
        for file_path, summary in self.file_summaries.items():
            summary_score = self._calculate_relevance(user_intent, summary)
            if summary_score <= 0:
                continue
            summary_scores.append((file_path, summary_score))
        summary_scores.sort(key=lambda item: item[1], reverse=True)
        top_files = {path for path, _ in summary_scores[:18]}
        if not top_files:
            return candidate_chunks

        merged: List[CodeChunk] = list(candidate_chunks)
        seen_keys = {
            (chunk.file_path, chunk.start_line, chunk.end_line, chunk.chunk_type, chunk.name)
            for chunk in merged
        }
        for chunk in self.code_chunks:
            if chunk.file_path not in top_files:
                continue
            key = (chunk.file_path, chunk.start_line, chunk.end_line, chunk.chunk_type, chunk.name)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged.append(chunk)

        return merged
    
    def _chunk_file(
        self,
        file_path: str,
        content: str,
        extension: str,
        symbols: List[CodeSymbol] = None,
    ) -> List[CodeChunk]:
        """
        Split file into semantic chunks.
        
        Args:
            file_path: Path to file
            content: File content
            extension: File extension
            
        Returns:
            List of code chunks
        """
        chunks = []

        lines = content.split('\n')
        chunk_size = 55
        step_size = 45

        # Add symbol-scoped chunks first for higher retrieval precision.
        if symbols:
            for symbol in symbols:
                start = max(1, symbol.start_line)
                end = min(len(lines), max(start, symbol.end_line))
                if end - start < 6:
                    end = min(len(lines), start + 14)
                chunk_content = "\n".join(lines[start - 1:end])
                if not chunk_content.strip():
                    continue
                chunks.append(CodeChunk(
                    file_path=file_path,
                    content=chunk_content,
                    start_line=start,
                    end_line=end,
                    language=self._get_language(extension),
                    chunk_type=symbol.kind,
                    name=symbol.name,
                ))

        for i in range(0, len(lines), step_size):
            chunk_lines = lines[i:i + chunk_size]
            if not chunk_lines:
                continue
            chunk_content = '\n'.join(chunk_lines)
            if chunk_content.strip():
                chunk = CodeChunk(
                    file_path=file_path,
                    content=chunk_content,
                    start_line=i + 1,
                    end_line=min(i + chunk_size, len(lines)),
                    language=self._get_language(extension),
                    chunk_type='block',
                    name=f"{file_path}:{i+1}-{min(i+chunk_size, len(lines))}"
                )
                chunks.append(chunk)

        # Dedupe repeated windows.
        unique = {}
        for chunk in chunks:
            key = (
                chunk.file_path,
                chunk.start_line,
                chunk.end_line,
                chunk.chunk_type,
                chunk.name,
            )
            unique[key] = chunk
        return list(unique.values())

    def _extract_symbols(self, file_path: str, content: str, extension: str) -> List[CodeSymbol]:
        """Extract symbol-like entities for retrieval grounding."""
        lines = content.splitlines()
        symbols: List[CodeSymbol] = []
        seen = set()

        def add_symbol(name: str, kind: str, line_no: int, signature: str = "") -> None:
            normalized_name = (name or "").strip()
            if not normalized_name:
                return
            dedupe_key = (kind, normalized_name.lower(), line_no)
            if dedupe_key in seen:
                return
            seen.add(dedupe_key)
            end_line = self._estimate_symbol_end_line(
                lines=lines,
                start_line=line_no,
                extension=extension,
            )
            symbols.append(CodeSymbol(
                file_path=file_path,
                name=normalized_name,
                kind=kind,
                start_line=line_no,
                end_line=end_line,
                signature=(signature or "").strip(),
            ))

        symbol_re = re.compile(
            r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\("
        )
        arrow_re = re.compile(
            r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_]\w*)\s*=>"
        )
        class_re = re.compile(
            r"^\s*(?:export\s+)?class\s+([A-Za-z_]\w*)\b"
        )
        py_def_re = re.compile(r"^\s*def\s+([A-Za-z_]\w*)\s*\(")
        py_class_re = re.compile(r"^\s*class\s+([A-Za-z_]\w*)\b")

        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            if extension == ".py":
                match = py_def_re.match(line)
                if match:
                    add_symbol(match.group(1), "function", index, stripped)
                match = py_class_re.match(line)
                if match:
                    add_symbol(match.group(1), "class", index, stripped)
            else:
                match = re.match(
                    r"^\s*export\s+default\s+function\s+([A-Za-z_]\w*)\s*\(",
                    line,
                )
                if match:
                    add_symbol(match.group(1), "component", index, stripped)

                match = symbol_re.match(line)
                if match:
                    kind = "component" if match.group(1)[:1].isupper() else "function"
                    add_symbol(match.group(1), kind, index, stripped)

                match = arrow_re.match(line)
                if match:
                    name = match.group(1)
                    kind = "component" if name[:1].isupper() else "function"
                    add_symbol(name, kind, index, stripped)

                match = class_re.match(line)
                if match:
                    add_symbol(match.group(1), "class", index, stripped)

            for route_path in re.findall(r"path\s*[:=]\s*[\"'`]([^\"'`]+)[\"'`]", line):
                if route_path.startswith("/"):
                    add_symbol(route_path, "route", index, stripped)

            for route_path in re.findall(r"<Route[^>]*\bpath\s*=\s*['\"{]([^'\"}]+)", line):
                if route_path.startswith("/"):
                    add_symbol(route_path, "route", index, stripped)

            endpoint_match = re.search(
                r"\b(?:router|app)\.(get|post|put|patch|delete)\s*\(\s*[\"'`]([^\"'`]+)[\"'`]",
                line,
                flags=re.IGNORECASE,
            )
            if endpoint_match:
                method = endpoint_match.group(1).upper()
                endpoint_path = endpoint_match.group(2)
                add_symbol(f"{method} {endpoint_path}", "endpoint", index, stripped)

        return symbols

    def _estimate_symbol_end_line(self, lines: List[str], start_line: int, extension: str) -> int:
        """Approximate end line for a symbol block."""
        total_lines = len(lines)
        if start_line >= total_lines:
            return total_lines

        max_span = 120 if extension == ".py" else 90
        max_line = min(total_lines, start_line + max_span)

        for cursor in range(start_line + 1, max_line + 1):
            candidate = lines[cursor - 1]
            if extension == ".py":
                if re.match(r"^\S", candidate) and candidate.strip() and not candidate.strip().startswith("#"):
                    return cursor - 1
            if re.match(r"^\s*(?:export\s+)?(?:async\s+)?function\s+[A-Za-z_]\w*\s*\(", candidate):
                return cursor - 1
            if re.match(r"^\s*(?:export\s+)?(?:const|let|var)\s+[A-Za-z_]\w*\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_]\w*)\s*=>", candidate):
                return cursor - 1
            if re.match(r"^\s*(?:export\s+)?class\s+[A-Za-z_]\w*", candidate):
                return cursor - 1

        return min(total_lines, start_line + 48)

    def _add_to_symbol_index(self, symbols: List[CodeSymbol]) -> None:
        """Update symbol lookup index."""
        for symbol in symbols:
            direct_key = symbol.name.lower()
            self.symbol_index.setdefault(direct_key, []).append(symbol)
            for token in self._symbol_name_tokens(symbol.name):
                self.symbol_index.setdefault(token, []).append(symbol)

    def _symbol_name_tokens(self, name: str) -> Set[str]:
        """Split a symbol name into searchable normalized tokens."""
        tokens: Set[str] = set()
        for part in re.split(r"[^A-Za-z0-9]+", (name or "").strip()):
            if not part:
                continue
            for piece in re.findall(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[0-9]+", part):
                lowered = piece.lower()
                if len(lowered) > 1:
                    tokens.add(lowered)
        if "/" in name:
            for segment in re.split(r"[/:-]", name):
                segment = segment.lower().strip()
                if len(segment) > 1:
                    tokens.add(segment)
        return tokens

    def _update_repository_map(self, file_path: str, content: str, symbols: List[CodeSymbol]) -> None:
        """Update repository map categories and symbol-to-file mapping."""
        path_lower = file_path.lower()
        basename = os.path.basename(path_lower)
        content_lower = content.lower()

        if self._is_entry_file(path_lower, basename):
            self.repository_map.entry_points.add(file_path)
        if self._is_config_file(path_lower, basename):
            self.repository_map.config_files.add(file_path)
        if self._is_routing_file(path_lower, content_lower, symbols):
            self.repository_map.routing_files.add(file_path)
        if self._is_api_file(path_lower, content_lower, symbols):
            self.repository_map.api_files.add(file_path)
        if self._is_state_file(path_lower, content_lower):
            self.repository_map.state_files.add(file_path)
        if self._is_ui_file(path_lower, basename):
            self.repository_map.ui_files.add(file_path)
        if self._is_data_file(path_lower, content_lower):
            self.repository_map.data_files.add(file_path)
        if self._is_debug_file(path_lower, content_lower):
            self.repository_map.debug_files.add(file_path)

        for symbol in symbols:
            keys = {symbol.name.lower(), *self._symbol_name_tokens(symbol.name)}
            if symbol.kind in {"route", "endpoint"}:
                keys.add(symbol.kind)
            for key in keys:
                if not key:
                    continue
                file_set = self.repository_map.symbol_to_files.setdefault(key, set())
                file_set.add(file_path)

        base_name = os.path.splitext(os.path.basename(file_path))[0]
        for token in self._symbol_name_tokens(base_name):
            self.repository_map.symbol_to_files.setdefault(token, set()).add(file_path)

    def _route_chunks_via_repository_map(
        self,
        user_intent: str,
        query_mode: str,
        anchor_terms: List[str],
    ) -> List[CodeChunk]:
        """Route retrieval to a smaller, intent-matched set of files."""
        if not self.code_chunks:
            return []

        mapped_files = self._all_repository_files()
        if not mapped_files:
            return self.code_chunks

        intent_lower = (user_intent or "").lower()
        anchor_files = self._files_for_anchor_terms(anchor_terms)
        mode_files = self._files_for_query_mode(intent_lower, query_mode)

        selected_files: Set[str] = set()
        selected_files.update(anchor_files)
        selected_files.update(mode_files)

        if not selected_files:
            return self.code_chunks

        selected_chunks = [chunk for chunk in self.code_chunks if chunk.file_path in selected_files]
        if selected_chunks:
            return selected_chunks

        return []

    def _all_repository_files(self) -> Set[str]:
        """Return union of all files tracked in repository map."""
        groups = [
            self.repository_map.entry_points,
            self.repository_map.routing_files,
            self.repository_map.api_files,
            self.repository_map.state_files,
            self.repository_map.ui_files,
            self.repository_map.data_files,
            self.repository_map.debug_files,
            self.repository_map.config_files,
        ]
        all_files: Set[str] = set()
        for group in groups:
            all_files.update(group)
        for files in self.repository_map.symbol_to_files.values():
            all_files.update(files)
        return all_files

    def _files_for_anchor_terms(self, anchor_terms: List[str]) -> Set[str]:
        """Resolve anchor terms to candidate files via symbol index and path match."""
        files: Set[str] = set()
        if not anchor_terms:
            return files

        searchable_files = self._all_repository_files()
        for term in anchor_terms:
            normalized = term.lower().strip()
            if not normalized:
                continue

            for key in {normalized, *self._symbol_name_tokens(normalized)}:
                files.update(self.repository_map.symbol_to_files.get(key, set()))
                for symbol in self.symbol_index.get(key, []):
                    files.add(symbol.file_path)

            for file_path in searchable_files:
                lower_path = file_path.lower()
                if normalized in lower_path:
                    files.add(file_path)
                elif any(token in lower_path for token in self._symbol_name_tokens(normalized)):
                    files.add(file_path)

        return files

    def _files_for_query_mode(self, intent_lower: str, query_mode: str) -> Set[str]:
        """Pick repository-map file groups relevant for the query mode."""
        repo_map = self.repository_map

        if query_mode == "config":
            return set(repo_map.config_files) | set(repo_map.entry_points)
        if query_mode in {"overview", "comparison"}:
            return (
                set(repo_map.entry_points)
                | set(repo_map.routing_files)
                | set(repo_map.ui_files)
                | set(repo_map.api_files)
                | set(repo_map.state_files)
                | set(repo_map.data_files)
            )
        if query_mode == "debug":
            return (
                set(repo_map.debug_files)
                | set(repo_map.api_files)
                | set(repo_map.state_files)
                | set(repo_map.entry_points)
            )
        if query_mode == "location":
            if any(token in intent_lower for token in ("route", "router", "path", "navigation")):
                return set(repo_map.routing_files) | set(repo_map.entry_points)
            if any(token in intent_lower for token in ("api", "endpoint", "backend", "server")):
                return set(repo_map.api_files) | set(repo_map.entry_points)
            if any(token in intent_lower for token in ("state", "redux", "context", "store", "slice")):
                return set(repo_map.state_files) | set(repo_map.entry_points)
            if any(token in intent_lower for token in ("db", "database", "schema", "model")):
                return set(repo_map.data_files) | set(repo_map.api_files)
            return (
                set(repo_map.routing_files)
                | set(repo_map.api_files)
                | set(repo_map.ui_files)
                | set(repo_map.state_files)
                | set(repo_map.entry_points)
            )

        # specific mode
        if any(token in intent_lower for token in ("route", "router", "navigation", "path")):
            return set(repo_map.routing_files) | set(repo_map.entry_points)
        if any(token in intent_lower for token in ("api", "endpoint", "backend", "server")):
            return set(repo_map.api_files) | set(repo_map.entry_points)
        if any(token in intent_lower for token in ("state", "redux", "context", "store", "slice")):
            return set(repo_map.state_files) | set(repo_map.ui_files)
        if any(token in intent_lower for token in ("component", "ui", "page", "screen", "shimmer", "skeleton")):
            return set(repo_map.ui_files)
        return (
            set(repo_map.entry_points)
            | set(repo_map.ui_files)
            | set(repo_map.routing_files)
            | set(repo_map.api_files)
            | set(repo_map.state_files)
        )

    def _is_entry_file(self, path_lower: str, basename: str) -> bool:
        return bool(
            basename.startswith(("main.", "app.", "index.", "router.", "routes.", "server."))
            or any(token in path_lower for token in ("/main.", "/app.", "/index.", "/router.", "/routes."))
        )

    def _is_config_file(self, path_lower: str, basename: str) -> bool:
        return bool(
            any(token in basename for token in ("config", "tsconfig", "webpack", "vite", "babel", "eslint", "prettier"))
            or "package.json" in path_lower
        )

    def _is_routing_file(self, path_lower: str, content_lower: str, symbols: List[CodeSymbol]) -> bool:
        route_symbol = any(symbol.kind == "route" for symbol in symbols)
        return bool(
            route_symbol
            or any(token in path_lower for token in ("router", "route"))
            or any(token in content_lower for token in ("createbrowserrouter", "browserrouter", "routerprovider", "<route", "path:"))
        )

    def _is_api_file(self, path_lower: str, content_lower: str, symbols: List[CodeSymbol]) -> bool:
        endpoint_symbol = any(symbol.kind == "endpoint" for symbol in symbols)
        return bool(
            endpoint_symbol
            or any(token in path_lower for token in ("api", "controller", "service", "route", "routes", "backend"))
            or any(token in content_lower for token in ("app.get(", "app.post(", "router.get(", "router.post(", "fetch(", "axios"))
        )

    def _is_state_file(self, path_lower: str, content_lower: str) -> bool:
        return bool(
            any(token in path_lower for token in ("store", "state", "slice", "reducer", "context"))
            or any(token in content_lower for token in ("configurestore", "createslice", "redux", "createcontext", "usecontext"))
        )

    def _is_ui_file(self, path_lower: str, basename: str) -> bool:
        return bool(
            path_lower.endswith((".jsx", ".tsx"))
            or any(token in path_lower for token in ("/components/", "\\components\\", "/pages/", "\\pages\\", "/views/", "\\views\\"))
            or basename.endswith(("component.js", "component.ts"))
        )

    def _is_data_file(self, path_lower: str, content_lower: str) -> bool:
        return bool(
            any(token in path_lower for token in ("db", "database", "model", "schema", "repository"))
            or any(token in content_lower for token in ("prisma", "sequelize", "mongoose", "sqlalchemy", "sqlite", "postgres", "mongodb"))
        )

    def _is_debug_file(self, path_lower: str, content_lower: str) -> bool:
        return bool(
            any(token in path_lower for token in ("error", "exception", "debug", "logger", "handler"))
            or any(token in content_lower for token in ("try", "catch", "except", "traceback", "fallback"))
        )
    
    def _generate_file_summary(self, file_path: str, content: str) -> str:
        """
        Generate AI summary of file.
        
        Args:
            file_path: Path to file
            content: File content
            
        Returns:
            Summary string
        """
        try:
            # Truncate content if too long
            max_chars = 3000
            truncated_content = content[:max_chars]
            
            prompt = f"""Analyze this code file and provide a brief summary (2-3 sentences) of what it does:

File: {file_path}

Code:
```
{truncated_content}
```

Summary:"""
            
            summary = self.orchestrator.generate_completion(prompt, max_tokens=150)
            return summary.strip()
        
        except Exception as e:
            logger.warning(f"Failed to generate summary for {file_path}: {e}")
            return f"Code file: {file_path}"
    
    def _score_chunks_with_ai(
        self,
        intent: str,
        chunks: List[CodeChunk],
        top_k: int
    ) -> List[CodeChunk]:
        """
        Score chunks using AI for relevance.
        
        Args:
            intent: User intent
            chunks: List of code chunks
            top_k: Number to return
            
        Returns:
            Top k relevant chunks
        """
        try:
            logger.info(f"Scoring {len(chunks)} chunks for intent: {intent}")
            query_mode = self._classify_query_mode(intent)
            query_is_config = query_mode == "config"
            query_is_overview = query_mode == "overview"
            query_is_location = query_mode == "location"
            query_is_comparison = query_mode == "comparison"
            query_is_debug = query_mode == "debug"
            logger.info(f"Detected query mode: {query_mode}")

            keywords = self._extract_keywords(intent)
            anchor_terms = self._extract_anchor_terms(keywords, intent)
            logger.info(f"Extracted keywords: {keywords}")
            logger.info(f"Anchor terms: {anchor_terms}")
            strict_mode = self._is_strict_mode(
                query_mode,
                anchor_terms=anchor_terms,
                user_intent=intent,
            )

            scored_chunks = []
            for chunk in chunks:
                score = self._compute_chunk_score(
                    chunk=chunk,
                    keywords=keywords,
                    anchor_terms=anchor_terms,
                    strict_mode=strict_mode,
                    query_is_config=query_is_config,
                    query_is_overview=query_is_overview,
                    query_is_location=query_is_location,
                    query_is_comparison=query_is_comparison,
                    query_is_debug=query_is_debug,
                )
                if score <= 0:
                    continue
                chunk.relevance_score = score
                scored_chunks.append(chunk)

            if strict_mode and anchor_terms:
                scored_chunks = [
                    chunk for chunk in scored_chunks
                    if self._anchor_hits_for_chunk(chunk, anchor_terms) > 0
                ]

            if not scored_chunks:
                if query_is_overview or query_is_comparison or query_is_config:
                    logger.warning("No high-confidence matches found, using heuristic fallback")
                    fallback = self._fallback_chunks(
                        chunks=chunks,
                        top_k=top_k,
                        query_is_config=query_is_config,
                        query_is_overview=query_is_overview,
                        query_is_location=query_is_location,
                        query_is_comparison=query_is_comparison,
                        query_is_debug=query_is_debug,
                    )
                    for rank, chunk in enumerate(fallback, start=1):
                        chunk.relevance_score = max(0.1, 1.0 - rank * 0.01)
                    return fallback

                logger.warning("No grounded matches for strict query mode")
                return []

            scored_chunks.sort(key=lambda x: x.relevance_score, reverse=True)
            if self._should_use_llm_rerank(query_mode, len(scored_chunks)):
                scored_chunks = self._apply_llm_rerank(
                    intent=intent,
                    scored_chunks=scored_chunks,
                    top_k=top_k,
                )
            if query_mode not in {"specific", "location"}:
                scored_chunks = self._apply_hybrid_rerank(
                    intent=intent,
                    scored_chunks=scored_chunks,
                )

            if strict_mode and scored_chunks[0].relevance_score < 1.2:
                logger.warning(
                    "Top relevance score %.2f is below strict threshold; returning no match",
                    scored_chunks[0].relevance_score,
                )
                return []

            top_score = scored_chunks[0].relevance_score
            min_kept_score = max(0.9 if strict_mode else 0.35, top_score * (0.32 if strict_mode else 0.22))
            scored_chunks = [chunk for chunk in scored_chunks if chunk.relevance_score >= min_kept_score]

            per_file_limit = 1 if (query_is_overview or query_is_comparison) else 2
            candidates = self._select_diverse_chunks(scored_chunks, top_k=top_k, per_file_limit=per_file_limit)
            logger.info(f"Returning {len(candidates)} candidates")
            return candidates
        
        except Exception as e:
            logger.error(f"AI scoring failed: {e}", exc_info=True)
            # Fallback to first chunks
            logger.warning("Falling back to first chunks")
            return chunks[:top_k] if chunks else []

    def _compute_chunk_score(
        self,
        chunk: CodeChunk,
        keywords: List[str],
        anchor_terms: List[str],
        strict_mode: bool,
        query_is_config: bool,
        query_is_overview: bool,
        query_is_location: bool,
        query_is_comparison: bool,
        query_is_debug: bool,
    ) -> float:
        """Compute weighted relevance score for a chunk."""
        content_lower = chunk.content.lower()
        path_lower = chunk.file_path.lower()

        score = 0.0
        keyword_hits = 0
        for keyword in keywords:
            if keyword in content_lower:
                keyword_hits += 1
            if keyword in path_lower:
                score += 0.8

        score += keyword_hits * 1.6

        if not query_is_location:
            hybrid_term_score = self._hybrid_term_score(
                query_terms=keywords + anchor_terms,
                content_text=chunk.content,
                path_text=chunk.file_path,
            )
            score += hybrid_term_score * 2.1

            hybrid_path_similarity = self._hybrid_path_similarity(
                query_text=" ".join(keywords + anchor_terms),
                path_text=chunk.file_path,
                symbol_name=chunk.name,
            )
            score += hybrid_path_similarity * 1.2

        anchor_hits_path, anchor_hits_content = self._anchor_hit_counts(
            path_lower=path_lower,
            content_lower=content_lower,
            anchor_terms=anchor_terms,
        )
        score += anchor_hits_content * 2.0
        score += anchor_hits_path * 1.3
        if strict_mode and anchor_terms and (anchor_hits_path + anchor_hits_content == 0):
            score -= 1.8

        # Prefer central app files when query is broad/overview.
        feature_signal = self._feature_signal_score(content_lower, path_lower)
        if query_is_overview:
            score += feature_signal
            score += self._entry_file_score(path_lower)
            # Penalize chunks that are broad but lack user-facing feature signals.
            if feature_signal < 0.8:
                score -= 0.7
        else:
            score += self._entry_file_score(path_lower) * 0.4

        if query_is_location:
            score += self._location_signal_score(content_lower, path_lower, keywords)
        if query_is_comparison:
            score += feature_signal * 0.6
            if keyword_hits >= 2:
                score += 0.8
        if query_is_debug:
            score += self._debug_signal_score(content_lower, path_lower)

        if not query_is_config:
            score -= self._noise_penalty(path_lower, content_lower)
            if query_is_overview and any(token in path_lower for token in self.NOISE_FILE_HINTS):
                score -= 0.8
        else:
            # For config questions, noise files become relevant.
            if any(token in path_lower for token in self.NOISE_FILE_HINTS):
                score += 1.4

        if query_is_overview and "path" in content_lower:
            score += 0.6
        if query_is_overview and ("fetch(" in content_lower or "axios" in content_lower):
            score += 0.6
        if query_is_overview and ("usestate" in content_lower or "redux" in content_lower or "context" in content_lower):
            score += 0.5

        return max(0.0, score)

    def _is_strict_mode(
        self,
        query_mode: str,
        anchor_terms: List[str] | None = None,
        user_intent: str = "",
    ) -> bool:
        """Decide whether strict grounding should be enforced."""
        if query_mode == "location":
            return True
        if query_mode != "specific":
            return False

        anchor_terms = anchor_terms or []
        if anchor_terms:
            return True

        query = (user_intent or "").lower()
        if self._is_broad_overview_query(query, [], anchor_terms):
            return False
        return False

    def _extract_anchor_terms(self, keywords: List[str], intent: str) -> List[str]:
        """Extract high-signal anchor terms from query keywords and explicit entities."""
        anchors: List[str] = []
        seen = set()

        def add_term(term: str) -> None:
            normalized = term.strip().lower().strip("`'\".,:;()[]{}")
            if not normalized or len(normalized) <= 2:
                return
            if normalized in self.LOW_SIGNAL_KEYWORDS:
                return
            if normalized in seen:
                return
            seen.add(normalized)
            anchors.append(normalized)

        for keyword in keywords:
            add_term(keyword)

        for token in re.findall(r"`([^`]+)`", intent or ""):
            add_term(token)

        for token in re.findall(r'"([^"]+)"|\'([^\']+)\'', intent or ""):
            for candidate in token:
                if candidate:
                    add_term(candidate)

        for route in re.findall(r"/[A-Za-z0-9_:/-]+", intent or ""):
            add_term(route)
            for part in re.split(r"[/:-]", route):
                add_term(part)

        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_./:-]{2,}", intent or ""):
            lowered = token.lower()
            is_code_like = (
                "/" in token
                or "." in token
                or "_" in token
                or ":" in token
                or any(char.isupper() for char in token[1:])
            )
            if is_code_like and lowered not in self.LOW_SIGNAL_KEYWORDS:
                add_term(lowered)

        return anchors[:10]

    def _anchor_hit_counts(
        self,
        path_lower: str,
        content_lower: str,
        anchor_terms: List[str],
    ) -> Tuple[int, int]:
        """Count anchor matches in path/content for scoring."""
        if not anchor_terms:
            return (0, 0)

        expanded = self._expand_query_keywords(anchor_terms)
        path_hits = 0
        content_hits = 0

        for term in expanded:
            if not term:
                continue
            if term in path_lower:
                path_hits += 1
            if term in content_lower:
                content_hits += 1

        return (path_hits, content_hits)

    def _anchor_hits_for_chunk(self, chunk: CodeChunk, anchor_terms: List[str]) -> int:
        """Return total anchor hits for a chunk."""
        path_hits, content_hits = self._anchor_hit_counts(
            path_lower=chunk.file_path.lower(),
            content_lower=chunk.content.lower(),
            anchor_terms=anchor_terms,
        )
        return path_hits + content_hits

    def _should_use_llm_rerank(self, query_mode: str, candidate_count: int) -> bool:
        """Decide whether to run lightweight LLM reranking."""
        if candidate_count < 2:
            return False
        if not self.orchestrator or not hasattr(self.orchestrator, "generate_completion"):
            return False
        return query_mode in {"specific", "location", "debug", "comparison"}

    def _apply_llm_rerank(
        self,
        intent: str,
        scored_chunks: List[CodeChunk],
        top_k: int,
    ) -> List[CodeChunk]:
        """Apply LLM-based direct-answer reranking on top candidates."""
        if not scored_chunks:
            return scored_chunks

        candidate_limit = min(len(scored_chunks), max(6, top_k * 2))
        candidates = scored_chunks[:candidate_limit]
        candidate_signature = tuple(
            f"{chunk.file_path}:{chunk.start_line}:{chunk.end_line}"
            for chunk in candidates
        )
        cache_key = (intent.strip().lower(), candidate_signature)
        ranking = self.rerank_cache.get(cache_key)

        if ranking is None:
            prompt = self._build_rerank_prompt(intent, candidates)
            try:
                try:
                    response = self.orchestrator.generate_completion(
                        prompt,
                        max_tokens=320,
                        temperature=0.0,
                    )
                except TypeError:
                    response = self.orchestrator.generate_completion(
                        prompt,
                        max_tokens=320,
                    )
                ranking = self._parse_rerank_response(str(response or ""), len(candidates))
            except Exception as exc:
                logger.warning(f"LLM reranking failed, using deterministic ranking: {exc}")
                ranking = {}
            self.rerank_cache[cache_key] = ranking

        if not ranking:
            return scored_chunks

        query_mode = self._classify_query_mode(intent)
        for index, chunk in enumerate(candidates, start=1):
            llm_score = ranking.get(index)
            if llm_score is None:
                continue
            llm_norm = max(0.0, min(1.0, llm_score / 100.0))
            if query_mode in {"specific", "location"}:
                # For direct lookup/location questions, trust reranker more strongly.
                chunk.relevance_score = max(
                    0.0,
                    (float(chunk.relevance_score) * 0.55) + (llm_norm * 2.4),
                )
            else:
                # For broad questions keep deterministic score primary.
                chunk.relevance_score = max(
                    0.0,
                    float(chunk.relevance_score) + ((llm_norm - 0.5) * 1.6),
                )

        scored_chunks.sort(key=lambda item: item.relevance_score, reverse=True)
        return scored_chunks

    def _apply_hybrid_rerank(self, intent: str, scored_chunks: List[CodeChunk]) -> List[CodeChunk]:
        """Final deterministic rerank using lexical overlap + fuzzy path similarity."""
        if not scored_chunks:
            return scored_chunks

        keywords = self._extract_keywords(intent)
        anchors = self._extract_anchor_terms(keywords, intent)
        query_text = " ".join(keywords + anchors)

        for chunk in scored_chunks:
            lexical = self._hybrid_term_score(
                query_terms=keywords + anchors,
                content_text=chunk.content,
                path_text=chunk.file_path,
            )
            fuzzy = self._hybrid_path_similarity(
                query_text=query_text,
                path_text=chunk.file_path,
                symbol_name=chunk.name,
            )
            # Keep prior score (including LLM rerank) primary; hybrid signal is a light tie-breaker.
            chunk.relevance_score = float(chunk.relevance_score) + (lexical * 0.22) + (fuzzy * 0.08)

        scored_chunks.sort(key=lambda item: item.relevance_score, reverse=True)
        return scored_chunks

    def _build_rerank_prompt(self, intent: str, candidates: List[CodeChunk]) -> str:
        """Build compact prompt for direct-answer snippet reranking."""
        lines = [
            "Rank repository snippets for direct-answer relevance.",
            f'User question: "{intent}"',
            "",
            "Rules:",
            "- Higher score if snippet directly answers the question.",
            "- Prefer explicit entity/route/function matches.",
            "- Penalize generic setup/config snippets.",
            "- Do not infer beyond snippet text.",
            "- Output JSON only, no markdown and no extra text.",
            "- JSON schema: {\"ranking\":[{\"id\":<int>,\"score\":<0-100 int>,\"reason\":\"<short text>\"}]}",
            "- Include every candidate id exactly once.",
            "",
            "Candidates:",
        ]

        for idx, chunk in enumerate(candidates, start=1):
            excerpt = re.sub(r"\s+", " ", chunk.content or "").strip()[:220]
            lines.append(
                f"{idx}|{chunk.file_path}:{chunk.start_line}-{chunk.end_line}|{excerpt}"
            )

        return "\n".join(lines)

    def _parse_rerank_response(self, response: str, max_id: int) -> Dict[int, int]:
        """Parse reranker output into {candidate_id: score}."""
        if not response:
            return {}
        if response.lower().startswith("error generating response"):
            return {}

        json_payload = self._extract_first_json_object(response)
        if json_payload:
            try:
                parsed = json.loads(json_payload)
                ranking_items = parsed.get("ranking", [])
                ranking: Dict[int, int] = {}
                for item in ranking_items:
                    if not isinstance(item, dict):
                        continue
                    try:
                        candidate_id = int(item.get("id"))
                        score = int(item.get("score"))
                    except Exception:
                        continue
                    if candidate_id < 1 or candidate_id > max_id:
                        continue
                    ranking[candidate_id] = max(0, min(100, score))
                if ranking:
                    return ranking
            except Exception:
                # Fall through to backward-compatible line parsing.
                pass

        return self._parse_rerank_line_fallback(response, max_id)

    def _extract_first_json_object(self, text: str) -> str:
        """Extract first JSON object from a model response."""
        if not text:
            return ""
        start = text.find("{")
        if start < 0:
            return ""

        depth = 0
        for index in range(start, len(text)):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
        return ""

    def _parse_rerank_line_fallback(self, response: str, max_id: int) -> Dict[int, int]:
        """Fallback parser for legacy line-based reranker format."""
        ranking: Dict[int, int] = {}
        line_pattern = re.compile(r"^\s*(\d+)\s*\|\s*(-?\d{1,3})\b")

        for line in response.splitlines():
            match = line_pattern.match(line.strip())
            if not match:
                continue
            candidate_id = int(match.group(1))
            if candidate_id < 1 or candidate_id > max_id:
                continue
            score = int(match.group(2))
            ranking[candidate_id] = max(0, min(100, score))

        return ranking

    def _classify_query_mode(self, intent: str) -> str:
        """Classify query into retrieval mode."""
        query = intent.lower()
        keywords = self._extract_keywords(intent)
        anchor_terms = self._extract_anchor_terms(keywords, intent)
        if any(pattern in query for pattern in self.CONFIG_PATTERNS):
            return "config"
        if any(pattern in query for pattern in self.LOCATION_PATTERNS):
            return "location"
        if any(pattern in query for pattern in self.COMPARISON_PATTERNS):
            return "comparison"
        if any(pattern in query for pattern in self.DEBUG_PATTERNS):
            return "debug"
        if any(pattern in query for pattern in self.OVERVIEW_PATTERNS):
            return "overview"
        if self._is_broad_overview_query(query, keywords, anchor_terms):
            return "overview"
        if "feature" in query and ("what" in query or "which" in query):
            return "overview"
        return "specific"

    def _is_broad_overview_query(self, query: str, keywords: List[str], anchor_terms: List[str]) -> bool:
        """Detect broad, high-level repository questions without specific entities."""
        query_lower = (query or "").lower()
        has_context = any(term in query_lower for term in self.BROAD_CONTEXT_TERMS)
        has_overview_cue = any(term in query_lower for term in self.BROAD_OVERVIEW_CUES)
        has_file_like_ref = bool(
            re.search(
                r"[A-Za-z0-9_./-]+\.(?:jsx|tsx|py|js|ts|java|go|rb|php|cs|json|yaml|yml|toml)",
                query_lower,
                flags=re.IGNORECASE,
            )
        )
        has_specific_anchor = bool(anchor_terms)

        # Generic "about this repo/app/codebase" prompts should stay broad.
        if has_context and has_overview_cue and not has_specific_anchor and not has_file_like_ref:
            return True

        # Extremely short broad prompts (e.g., "codebase overview", "app summary").
        if has_context and len(keywords) <= 2 and not has_specific_anchor and not has_file_like_ref:
            return True

        return False

    def _feature_signal_score(self, content_lower: str, path_lower: str) -> float:
        """Extra score for user-facing behavior and architecture signals."""
        score = 0.0
        if any(token in path_lower for token in self.FEATURE_FILE_HINTS):
            score += 1.2
        if any(token in path_lower for token in ("/pages/", "\\pages\\", "/components/", "\\components\\")):
            score += 1.0
        if any(token in content_lower for token in ("createbrowserrouter", "browserrouter", "<route", "path:", "routerprovider")):
            score += 1.3
        if any(token in content_lower for token in ("lazy(", "suspense", "errorelement")):
            score += 0.8
        if any(token in content_lower for token in ("cart", "menu", "restaurant", "search", "filter", "shimmer")):
            score += 0.9
        return score

    def _entry_file_score(self, path_lower: str) -> float:
        """Boost probable entry points and main UI files."""
        score = 0.0
        entry_names = ("app.", "main.", "index.", "router.", "routes.", "layout.")
        if any(name in os.path.basename(path_lower) for name in entry_names):
            score += 1.0
        if path_lower.endswith((".jsx", ".tsx", ".js", ".ts")):
            score += 0.2
        return score

    def _location_signal_score(self, content_lower: str, path_lower: str, keywords: List[str]) -> float:
        """Boost symbols likely to answer 'where is X implemented' queries."""
        score = 0.0
        expanded_keywords = self._expand_query_keywords(keywords)
        if any(keyword in path_lower for keyword in expanded_keywords):
            score += 1.6
        if any(token in content_lower for token in ("export default", "export const", "export function", "class ", "function ")):
            score += 0.6
        if any(keyword in content_lower for keyword in expanded_keywords):
            score += 0.5
        if any(token in path_lower for token in ("component", "page", "route", "router", "service", "controller", "hook")):
            score += 0.5
        return score

    def _expand_query_keywords(self, keywords: List[str]) -> List[str]:
        """Expand query keywords with light stemming and domain synonyms."""
        expanded = set(keywords)
        synonyms = {
            "routing": {"route", "router"},
            "routes": {"route", "router"},
            "authentication": {"auth", "login", "token"},
            "authorization": {"auth", "role", "permission"},
            "state": {"store", "context", "redux"},
            "loading": {"shimmer", "skeleton", "loader"},
        }
        for keyword in list(expanded):
            if keyword.endswith("ing") and len(keyword) > 5:
                expanded.add(keyword[:-3])
            if keyword.endswith("ed") and len(keyword) > 4:
                expanded.add(keyword[:-2])
            for alias in synonyms.get(keyword, set()):
                expanded.add(alias)
        return list(expanded)

    def _debug_signal_score(self, content_lower: str, path_lower: str) -> float:
        """Boost error-handling and fallback logic for debugging questions."""
        score = 0.0
        if any(token in content_lower for token in ("try:", "except", "try {", "catch", "throw", "raise")):
            score += 1.0
        if any(token in content_lower for token in ("error", "exception", "fallback", "retry", "timeout", "status", "traceback")):
            score += 0.9
        if any(token in path_lower for token in ("error", "exception", "debug", "log", "handler")):
            score += 0.8
        return score

    def _noise_penalty(self, path_lower: str, content_lower: str) -> float:
        """Penalty for boilerplate/config/test files when not explicitly asked."""
        penalty = 0.0
        if any(token in path_lower for token in self.NOISE_FILE_HINTS):
            penalty += 1.4
        if any(token in path_lower for token in ("test", "__tests__", ".spec.", ".test.")):
            penalty += 1.0
        if "eslint" in content_lower or "prettier" in content_lower:
            penalty += 0.6
        return penalty

    def _tokenize_text(self, text: str) -> Set[str]:
        """Tokenize text into normalized terms for lexical overlap scoring."""
        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_:-]{1,}", (text or "").lower())
        normalized: Set[str] = set()
        for token in tokens:
            t = token.strip()
            if len(t) <= 2:
                continue
            if t in self.LOW_SIGNAL_KEYWORDS:
                continue
            normalized.add(t)
        return normalized

    def _hybrid_term_score(self, query_terms: List[str], content_text: str, path_text: str) -> float:
        """Compute lexical overlap score between query terms and chunk text/path."""
        query_tokens = self._tokenize_text(" ".join(query_terms))
        if not query_tokens:
            return 0.0

        content_tokens = self._tokenize_text(content_text)
        path_tokens = self._tokenize_text(path_text.replace("/", " ").replace("\\", " "))
        if not content_tokens and not path_tokens:
            return 0.0

        content_overlap = len(query_tokens & content_tokens) / max(len(query_tokens), 1)
        path_overlap = len(query_tokens & path_tokens) / max(len(query_tokens), 1)
        return (content_overlap * 0.7) + (path_overlap * 0.3)

    def _hybrid_path_similarity(self, query_text: str, path_text: str, symbol_name: str) -> float:
        """Use fuzzy similarity to reward close file/symbol naming matches."""
        query = (query_text or "").strip().lower()
        if not query:
            return 0.0

        path = (path_text or "").strip().lower()
        symbol = (symbol_name or "").strip().lower()
        path_sim = SequenceMatcher(None, query, path).ratio()
        symbol_sim = SequenceMatcher(None, query, symbol).ratio() if symbol else 0.0
        return max(path_sim, symbol_sim)

    def _select_diverse_chunks(self, chunks: List[CodeChunk], top_k: int, per_file_limit: int = 2) -> List[CodeChunk]:
        """Select top chunks while maintaining file diversity."""
        selected: List[CodeChunk] = []
        file_counts: Dict[str, int] = {}

        for chunk in chunks:
            current = file_counts.get(chunk.file_path, 0)
            if current >= per_file_limit:
                continue
            selected.append(chunk)
            file_counts[chunk.file_path] = current + 1
            if len(selected) >= top_k:
                break

        if len(selected) < top_k:
            for chunk in chunks:
                if chunk in selected:
                    continue
                selected.append(chunk)
                if len(selected) >= top_k:
                    break

        return selected

    def _fallback_chunks(
        self,
        chunks: List[CodeChunk],
        top_k: int,
        query_is_config: bool,
        query_is_overview: bool,
        query_is_location: bool,
        query_is_comparison: bool,
        query_is_debug: bool,
    ) -> List[CodeChunk]:
        """Fallback ranking when keyword matching is weak."""
        rescored = []
        for chunk in chunks:
            content_lower = chunk.content.lower()
            path_lower = chunk.file_path.lower()

            score = self._entry_file_score(path_lower)
            if query_is_overview:
                score += self._feature_signal_score(content_lower, path_lower)
            if query_is_location:
                score += self._location_signal_score(content_lower, path_lower, [])
            if query_is_debug:
                score += self._debug_signal_score(content_lower, path_lower)
            if not query_is_config:
                score -= self._noise_penalty(path_lower, content_lower)
            rescored.append((score, chunk))

        rescored.sort(key=lambda item: item[0], reverse=True)
        ordered = [chunk for _, chunk in rescored if _ > -2.0]
        if not ordered:
            ordered = [item[1] for item in rescored]
        per_file_limit = 1 if (query_is_overview or query_is_comparison) else 2
        return self._select_diverse_chunks(ordered, top_k=top_k, per_file_limit=per_file_limit)
    
    def _calculate_relevance(self, intent: str, content: str) -> float:
        """
        Calculate relevance score between intent and content.
        
        Args:
            intent: User intent
            content: Code content
            
        Returns:
            Relevance score (0-1)
        """
        try:
            # Simple keyword-based scoring (can be enhanced with embeddings)
            keywords = self._extract_keywords(intent)
            content_lower = content.lower()
            
            matches = sum(1 for kw in keywords if kw.lower() in content_lower)
            score = min(matches / max(len(keywords), 1), 1.0)
            
            return score
        
        except Exception as e:
            logger.warning(f"Relevance calculation failed: {e}")
            return 0.0
    
    def _extract_keywords(self, text: str) -> List[str]:
        """
        Extract keywords from text.
        
        Args:
            text: Input text
            
        Returns:
            List of keywords
        """
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'should', 'could', 'may', 'might', 'must', 'can', 'i', 'you', 'he',
            'she', 'it', 'we', 'they', 'what', 'which', 'who', 'when', 'where',
            'why', 'how', 'this', 'that', 'these', 'those', 'code', 'codebase',
            'repo', 'repository', 'app', 'key', 'feature', 'features', 'file',
            'files', 'implemented', 'implementation', 'explain'
        }

        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text.lower())
        keywords: List[str] = []
        seen = set()

        for token in tokens:
            normalized = token.rstrip("s") if token.endswith("s") and len(token) > 4 else token
            if normalized in stop_words or len(normalized) <= 2:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            keywords.append(normalized)

        return keywords
    
    def _get_language(self, extension: str) -> str:
        """Get language from file extension."""
        lang_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.go': 'go',
            '.rb': 'ruby'
        }
        return lang_map.get(extension, 'text')
