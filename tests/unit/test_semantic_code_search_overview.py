"""Regression tests for semantic search ranking in overview/config modes."""

from types import SimpleNamespace

from analyzers.semantic_code_search import SemanticCodeSearch, CodeChunk


class _DummyOrchestrator:
    def generate_completion(self, prompt, max_tokens=150):
        return ""


class _RerankOrchestrator:
    def generate_completion(self, prompt, max_tokens=320, temperature=0.0):
        if "User question" not in prompt:
            return ""
        # Prefer candidate 2 over candidate 1.
        return (
            '{"ranking": ['
            '{"id": 1, "score": 20, "reason": "Only UI wrapper text"},'
            '{"id": 2, "score": 94, "reason": "Direct checkout implementation details"}'
            "]} "
        )


def _chunk(file_path: str, content: str) -> CodeChunk:
    return CodeChunk(
        file_path=file_path,
        content=content,
        start_line=1,
        end_line=max(1, len(content.splitlines())),
        language="javascript",
        chunk_type="block",
        name=file_path,
    )


def test_overview_query_prioritizes_feature_files_over_config_noise():
    engine = SemanticCodeSearch(_DummyOrchestrator())
    engine.code_chunks = [
        _chunk(
            "vite.config.js",
            "import { defineConfig } from 'vite'; export default defineConfig({ plugins: [] });",
        ),
        _chunk(
            "src/router.jsx",
            "import { createBrowserRouter } from 'react-router-dom'; const router = createBrowserRouter([{ path: '/' }]);",
        ),
        _chunk(
            "src/components/Shimmer.jsx",
            "export const Shimmer = () => <div className='skeleton shimmer'>Loading...</div>;",
        ),
        _chunk(
            "src/pages/Home.jsx",
            "export default function Home() { return <main>Home</main>; }",
        ),
    ]

    results = engine.search_by_intent("what are the key features in this codebase?", top_k=3)
    files = [item.file_path.lower() for item in results]

    assert files
    assert "src/router.jsx" in files
    assert "src/components/shimmer.jsx" in files
    assert "vite.config.js" not in files


def test_config_query_can_return_config_files():
    engine = SemanticCodeSearch(_DummyOrchestrator())
    engine.code_chunks = [
        _chunk(
            "vite.config.js",
            "import { defineConfig } from 'vite'; export default defineConfig({ plugins: [] });",
        ),
        _chunk(
            "src/router.jsx",
            "import { createBrowserRouter } from 'react-router-dom'; const router = createBrowserRouter([{ path: '/' }]);",
        ),
    ]

    results = engine.search_by_intent("explain the vite config and build setup", top_k=2)
    files = [item.file_path.lower() for item in results]

    assert files
    assert files[0] == "vite.config.js"


def test_location_query_prefers_files_that_define_target_behavior():
    engine = SemanticCodeSearch(_DummyOrchestrator())
    engine.code_chunks = [
        _chunk(
            "src/components/Header.jsx",
            "export default function Header() { return <header>Hi</header>; }",
        ),
        _chunk(
            "src/router.jsx",
            "import { createBrowserRouter } from 'react-router-dom'; const router = createBrowserRouter([{ path: '/' }]);",
        ),
    ]

    results = engine.search_by_intent("which file routing is implemented in?", top_k=1)
    assert results
    assert results[0].file_path.lower() == "src/router.jsx"


def test_debug_query_prefers_error_handling_chunks():
    engine = SemanticCodeSearch(_DummyOrchestrator())
    engine.code_chunks = [
        _chunk(
            "src/components/Cart.jsx",
            "export default function Cart() { return <div>Cart</div>; }",
        ),
        _chunk(
            "src/utils/errorHandler.js",
            "export function handleError(err) { try { throw err; } catch (e) { return e.message; } }",
        ),
    ]

    results = engine.search_by_intent("app is not working, debug this exception and bug", top_k=1)
    assert results
    assert results[0].file_path.lower() == "src/utils/errorhandler.js"


def test_specific_query_requires_anchor_match_and_avoids_noise_fallback():
    engine = SemanticCodeSearch(_DummyOrchestrator())
    engine.code_chunks = [
        _chunk(
            "src/router.jsx",
            "import { createBrowserRouter } from 'react-router-dom'; const router = createBrowserRouter([{ path: '/' }]);",
        ),
        _chunk(
            "src/components/Header.jsx",
            "export default function Header() { return <header>Hi</header>; }",
        ),
    ]

    results = engine.search_by_intent("where is payment gateway implemented?", top_k=3)
    assert results == []


def test_specific_entity_query_prioritizes_entity_matching_chunks():
    engine = SemanticCodeSearch(_DummyOrchestrator())
    engine.code_chunks = [
        _chunk(
            "src/components/Shimmer.jsx",
            "export default function Shimmer() { return <div className='shimmer'>Loading</div>; }",
        ),
        _chunk(
            "src/router.jsx",
            "import { createBrowserRouter } from 'react-router-dom'; const router = createBrowserRouter([{ path: '/' }]);",
        ),
        _chunk(
            "src/pages/Home.jsx",
            "export default function Home() { return <main>Home</main>; }",
        ),
    ]

    results = engine.search_by_intent("what is shimmer in this repo and why we use that", top_k=2)
    files = [item.file_path.lower() for item in results]

    assert files
    assert files[0] == "src/components/shimmer.jsx"
    assert "src/router.jsx" not in files


def test_generic_codebase_about_query_is_treated_as_overview():
    engine = SemanticCodeSearch(_DummyOrchestrator())
    engine.code_chunks = [
        _chunk(
            "vite.config.js",
            "import { defineConfig } from 'vite'; export default defineConfig({ plugins: [] });",
        ),
        _chunk(
            "src/router.jsx",
            "import { createBrowserRouter } from 'react-router-dom'; const router = createBrowserRouter([{ path: '/' }]);",
        ),
        _chunk(
            "src/pages/Home.jsx",
            "export default function Home() { return <main>Home</main>; }",
        ),
    ]

    mode = engine._classify_query_mode("actually tell me what is this codebase about")
    results = engine.search_by_intent("actually tell me what is this codebase about", top_k=3)
    files = [item.file_path.lower() for item in results]

    assert mode == "overview"
    assert files
    assert "src/router.jsx" in files
    assert files[0] != "vite.config.js"


def test_specific_mode_without_anchor_terms_is_not_forced_strict():
    engine = SemanticCodeSearch(_DummyOrchestrator())
    assert not engine._is_strict_mode(
        "specific",
        anchor_terms=[],
        user_intent="tell me about this codebase",
    )
    assert engine._is_strict_mode(
        "specific",
        anchor_terms=["routing"],
        user_intent="which routing system is used?",
    )


def test_analyze_query_clarity_flags_ambiguous_short_query():
    engine = SemanticCodeSearch(_DummyOrchestrator())
    engine.code_chunks = [
        _chunk("src/router.jsx", "const router = createBrowserRouter([{ path: '/' }]);"),
    ]
    clarity = engine.analyze_query_clarity("explain this")
    assert clarity["is_ambiguous"] is True
    assert clarity["reason"] in {"low_specificity", "too_short"}
    assert clarity["suggested_focus"]


def test_hybrid_candidate_augmentation_uses_file_summaries():
    engine = SemanticCodeSearch(_DummyOrchestrator())
    core_chunk = _chunk("src/router.jsx", "const router = createBrowserRouter([{ path: '/' }]);")
    api_chunk = _chunk("src/api/client.js", "export async function fetchMenu() { return fetch('/menu'); }")
    engine.code_chunks = [core_chunk, api_chunk]
    engine.file_summaries = {
        "src/router.jsx": "Routing setup and app navigation",
        "src/api/client.js": "API client for menu data",
    }

    augmented = engine._augment_candidates_with_summary_files(
        "where is menu api client implemented?",
        [core_chunk],
    )
    files = [item.file_path for item in augmented]
    assert "src/api/client.js" in files


def test_llm_reranker_can_reorder_close_candidates_for_direct_answer():
    engine = SemanticCodeSearch(_RerankOrchestrator())
    engine.code_chunks = [
        _chunk(
            "src/components/CheckoutBanner.jsx",
            "export default function CheckoutBanner() { return <div>Checkout now</div>; }",
        ),
        _chunk(
            "src/pages/Checkout.jsx",
            "export default function Checkout() { const checkout = true; return <main>Checkout flow</main>; }",
        ),
    ]

    results = engine.search_by_intent("where is checkout implemented?", top_k=2)
    files = [item.file_path.lower() for item in results]

    assert files
    assert files[0] == "src/pages/checkout.jsx"


def test_repository_index_builds_symbol_map_and_routes_query_to_router_file(tmp_path):
    engine = SemanticCodeSearch(_DummyOrchestrator())

    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    router_file = src_dir / "router.jsx"
    router_file.write_text(
        "\n".join([
            "import { createBrowserRouter } from 'react-router-dom';",
            "const router = createBrowserRouter([",
            "  { path: '/', element: <Home /> },",
            "  { path: '/cart', element: <Cart /> },",
            "]);",
            "export default router;",
        ]),
        encoding="utf-8",
    )
    header_file = src_dir / "Header.jsx"
    header_file.write_text(
        "export default function Header() { return <header>Header</header>; }",
        encoding="utf-8",
    )

    repo_analysis = SimpleNamespace(
        file_tree={
            "src": [
                SimpleNamespace(path="src/router.jsx", extension=".jsx"),
                SimpleNamespace(path="src/Header.jsx", extension=".jsx"),
            ]
        }
    )
    engine.index_repository(str(tmp_path), repo_analysis)

    assert "router" in engine.repository_map.symbol_to_files
    assert "src/router.jsx" in engine.repository_map.routing_files

    results = engine.search_by_intent("which file routing system is implemented in?", top_k=1)
    assert results
    assert results[0].file_path.lower() == "src/router.jsx"


def test_reranker_parser_falls_back_to_legacy_pipe_format():
    engine = SemanticCodeSearch(_DummyOrchestrator())
    parsed = engine._parse_rerank_response(
        "\n".join([
            "2|95|Direct checkout implementation details",
            "1|25|Only UI wrapper text",
        ]),
        max_id=3,
    )
    assert parsed == {2: 95, 1: 25}
