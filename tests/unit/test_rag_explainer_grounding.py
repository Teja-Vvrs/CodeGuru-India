"""Regression tests for grounded RAG explanations."""

import re
from types import SimpleNamespace

from analyzers.rag_explainer import RAGExplainer
from analyzers.semantic_code_search import CodeChunk


class _DummyOrchestrator:
    def generate_completion(self, prompt, max_tokens=300):
        # Intentionally hallucinates BrowserRouter style code.
        return (
            "This repo uses BrowserRouter.\n\n"
            "```javascript\n"
            "import { BrowserRouter } from 'react-router-dom';\n"
            "function App() { return <BrowserRouter /> }\n"
            "```\n"
            "Routing is configured in router file."
        )


class _CountingOrchestrator:
    def __init__(self):
        self.calls = 0

    def generate_completion(self, prompt, max_tokens=300):
        self.calls += 1
        return "This should not be used for deterministic feature overview."


def test_rag_explainer_strips_synthetic_code_and_keeps_grounded_evidence():
    explainer = RAGExplainer(_DummyOrchestrator(), web_search_available=False)
    repo_context = SimpleNamespace(
        repo_url="local-repo",
        languages={"javascript": 10},
    )
    chunks = [
        CodeChunk(
            file_path="frontend/src/router.js",
            start_line=1,
            end_line=24,
            language="javascript",
            chunk_type="block",
            name="router",
            content=(
                "import { createBrowserRouter } from 'react-router-dom';\n"
                "const router = createBrowserRouter([\n"
                "  { path: '/', element: <Home/> },\n"
                "  { path: '/restaurant/:resId', element: <RestaurantMenu/> }\n"
                "]);\n"
                "export default router;\n"
            ),
        )
    ]

    result = explainer.generate_detailed_explanation(
        intent="which routing system used for the routing in this codebase and explain about that",
        relevant_chunks=chunks,
        repo_context=repo_context,
        use_web_search=False,
        output_language="english",
    )

    text = result["explanation"]
    assert re.search(r"\bBrowserRouter\b", text) is None
    assert "createBrowserRouter" in text
    assert "Relevant files:" in text
    assert "frontend/src/router.js" in text


def test_feature_overview_query_is_deterministic_and_filters_config_noise():
    orchestrator = _CountingOrchestrator()
    explainer = RAGExplainer(orchestrator, web_search_available=False)
    repo_context = SimpleNamespace(
        repo_url="local-repo",
        languages={"javascript": 10},
    )
    chunks = [
        CodeChunk(
            file_path="frontend/src/router.js",
            start_line=1,
            end_line=35,
            language="javascript",
            chunk_type="block",
            name="router",
            content=(
                "import { createBrowserRouter } from 'react-router-dom';\n"
                "const router = createBrowserRouter([{ path: '/', element: <Home/> }]);\n"
                "export default router;\n"
            ),
        ),
        CodeChunk(
            file_path="frontend/src/components/Shimmer.jsx",
            start_line=1,
            end_line=24,
            language="javascript",
            chunk_type="block",
            name="shimmer",
            content=(
                "export default function Shimmer() {\n"
                "  return <div className='skeleton shimmer'>Loading...</div>;\n"
                "}\n"
            ),
        ),
        CodeChunk(
            file_path="vite.config.js",
            start_line=1,
            end_line=20,
            language="javascript",
            chunk_type="block",
            name="vite",
            content=(
                "import { defineConfig } from 'vite';\n"
                "export default defineConfig({ plugins: [] });\n"
            ),
        ),
    ]

    result = explainer.generate_detailed_explanation(
        intent="what are the key features in this codebase?",
        relevant_chunks=chunks,
        repo_context=repo_context,
        use_web_search=False,
        output_language="english",
    )

    text = result["explanation"].lower()
    refs = [item["file"].lower() for item in result["code_references"]]

    assert "key features in this codebase" in text
    assert "createbrowserrouter" in text
    assert "loading experience" in text or "shimmer" in text
    assert "vite.config.js" not in text
    assert all("vite.config.js" not in ref for ref in refs)
    assert orchestrator.calls == 0


def test_generic_unsupported_code_entities_are_filtered_from_answer():
    class _HallucinatingOrchestrator:
        def generate_completion(self, prompt, max_tokens=300):
            return (
                "The code uses `createBrowserRouter` from `frontend/src/router.js`.\n"
                "It also has `MagicRouterEngine` in `src/magic_router.ts`."
            )

    explainer = RAGExplainer(_HallucinatingOrchestrator(), web_search_available=False)
    repo_context = SimpleNamespace(
        repo_url="local-repo",
        languages={"javascript": 10},
    )
    chunks = [
        CodeChunk(
            file_path="frontend/src/router.js",
            start_line=1,
            end_line=20,
            language="javascript",
            chunk_type="block",
            name="router",
            content=(
                "import { createBrowserRouter } from 'react-router-dom';\n"
                "const router = createBrowserRouter([{ path: '/', element: <Home/> }]);\n"
                "export default router;\n"
            ),
        )
    ]

    result = explainer.generate_detailed_explanation(
        intent="which routing system is used",
        relevant_chunks=chunks,
        repo_context=repo_context,
        use_web_search=False,
        output_language="english",
    )

    text = result["explanation"]
    assert "createBrowserRouter" in text
    assert "frontend/src/router.js" in text
    assert "MagicRouterEngine" not in text
    assert "src/magic_router.ts" not in text


def test_location_file_query_without_match_returns_clear_not_found():
    class _HallucinatingOrchestrator:
        def generate_completion(self, prompt, max_tokens=300):
            return "The backend entry file is `backend/index.js`."

    explainer = RAGExplainer(_HallucinatingOrchestrator(), web_search_available=False)
    repo_context = SimpleNamespace(
        repo_url="local-repo",
        languages={"javascript": 10},
    )
    chunks = [
        CodeChunk(
            file_path="frontend/src/Components/Shimmer.jsx",
            start_line=1,
            end_line=20,
            language="javascript",
            chunk_type="block",
            name="shimmer",
            content="export default function Shimmer() { return <div>Loading</div>; }",
        ),
        CodeChunk(
            file_path="frontend/src/main.jsx",
            start_line=1,
            end_line=15,
            language="javascript",
            chunk_type="block",
            name="main",
            content="import router from './router.jsx';",
        ),
    ]

    result = explainer.generate_detailed_explanation(
        intent="where is backend index.js file",
        relevant_chunks=chunks,
        repo_context=repo_context,
        use_web_search=False,
        output_language="english",
    )

    text = result["explanation"].lower()
    assert "index.js" in text
    assert "not found" in text
    assert result["code_references"] == []
    assert "shimmer" not in text


def test_file_existence_query_returns_deterministic_no_without_irrelevant_content():
    class _HallucinatingOrchestrator:
        def generate_completion(self, prompt, max_tokens=300):
            return "It likely exists in backend/index.js and uses RouterProvider."

    explainer = RAGExplainer(_HallucinatingOrchestrator(), web_search_available=False)
    repo_context = SimpleNamespace(
        repo_url="local-repo",
        languages={"javascript": 10},
        file_tree={
            "frontend/src": [
                SimpleNamespace(path="frontend/src/main.jsx"),
                SimpleNamespace(path="frontend/src/router.jsx"),
            ]
        },
    )
    chunks = [
        CodeChunk(
            file_path="frontend/src/Components/Shimmer.jsx",
            start_line=1,
            end_line=20,
            language="javascript",
            chunk_type="block",
            name="shimmer",
            content="export default function Shimmer() { return <div>Loading</div>; }",
        )
    ]

    result = explainer.generate_detailed_explanation(
        intent="is there backend index.js file",
        relevant_chunks=chunks,
        repo_context=repo_context,
        use_web_search=False,
        output_language="english",
    )

    text = result["explanation"].lower()
    assert "no" in text or "could not find" in text
    assert "index.js" in text
    assert "shimmer" not in text
    assert "routerprovider" not in text


def test_file_existence_query_returns_matching_path_when_present():
    class _HallucinatingOrchestrator:
        def generate_completion(self, prompt, max_tokens=300):
            return "No clue."

    explainer = RAGExplainer(_HallucinatingOrchestrator(), web_search_available=False)
    repo_context = SimpleNamespace(
        repo_url="local-repo",
        languages={"javascript": 10},
        file_tree={
            "backend": [
                SimpleNamespace(path="backend/index.js"),
                SimpleNamespace(path="backend/server.js"),
            ]
        },
    )

    result = explainer.generate_detailed_explanation(
        intent="is there backend index.js file",
        relevant_chunks=[],
        repo_context=repo_context,
        use_web_search=False,
        output_language="english",
    )

    text = result["explanation"].lower()
    assert "yes" in text
    assert "backend/index.js" in text


def test_rag_explainer_keeps_step_output_when_requested():
    class _StepOrchestrator:
        def generate_completion(self, prompt, max_tokens=300):
            return (
                "1. Identify `createBrowserRouter` usage in `frontend/src/router.js`.\n"
                "2. Check route definitions including dynamic params like `:resId`.\n"
                "3. Confirm app mount flow through `RouterProvider` in `frontend/src/main.jsx`."
            )

    explainer = RAGExplainer(_StepOrchestrator(), web_search_available=False)
    repo_context = SimpleNamespace(
        repo_url="local-repo",
        languages={"javascript": 10},
    )
    chunks = [
        CodeChunk(
            file_path="frontend/src/router.js",
            start_line=1,
            end_line=20,
            language="javascript",
            chunk_type="block",
            name="router",
            content="import { createBrowserRouter } from 'react-router-dom'; const router = createBrowserRouter([]);",
        ),
        CodeChunk(
            file_path="frontend/src/main.jsx",
            start_line=1,
            end_line=12,
            language="javascript",
            chunk_type="block",
            name="main",
            content="import { RouterProvider } from 'react-router-dom';",
        ),
    ]

    result = explainer.generate_detailed_explanation(
        intent="explain routing step by step with examples",
        relevant_chunks=chunks,
        repo_context=repo_context,
        use_web_search=False,
        output_language="english",
        response_profile={"depth": "deep", "format": "steps", "include_examples": True},
    )

    text = result["explanation"]
    assert "1." in text
    assert "2." in text
    assert "3." in text
    assert "Relevant files:" in text


def test_rag_explainer_removes_meta_chatter_and_duplicate_revisions():
    class _RepeatingOrchestrator:
        def generate_completion(self, prompt, max_tokens=300):
            return (
                "About the codebase\n"
                "The codebase uses `createBrowserRouter` in `frontend/src/router.jsx`.\n\n"
                "Please let me provide a revised answer that meets strict requirements.\n\n"
                "About the codebase\n"
                "The codebase uses `createBrowserRouter` in `frontend/src/router.jsx`.\n\n"
                "Let me know if I can assist you further."
            )

    explainer = RAGExplainer(_RepeatingOrchestrator(), web_search_available=False)
    repo_context = SimpleNamespace(
        repo_url="local-repo",
        languages={"javascript": 10},
    )
    chunks = [
        CodeChunk(
            file_path="frontend/src/router.jsx",
            start_line=1,
            end_line=20,
            language="javascript",
            chunk_type="block",
            name="router",
            content=(
                "import { createBrowserRouter } from 'react-router-dom';\n"
                "const router = createBrowserRouter([{ path: '/', element: <Home/> }]);\n"
                "export default router;\n"
            ),
        )
    ]

    result = explainer.generate_detailed_explanation(
        intent="tell me about the codebase",
        relevant_chunks=chunks,
        repo_context=repo_context,
        use_web_search=False,
        output_language="english",
    )

    text = result["explanation"]
    assert text.lower().count("about the codebase") <= 1
    assert "revised answer" not in text.lower()
    assert "let me know if i can assist" not in text.lower()
    assert "createBrowserRouter" in text
    assert "frontend/src/router.jsx" in text
