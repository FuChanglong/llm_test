from app.mcp.server import evaluate_expression


def test_evaluate_expression_accepts_numeric_math() -> None:
    assert evaluate_expression("24*7") == {"expression": "24*7", "result": 168}


def test_evaluate_expression_rejects_non_numeric_input() -> None:
    assert "error" in evaluate_expression("__import__('os')")
