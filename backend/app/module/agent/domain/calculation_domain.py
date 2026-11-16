"""Safe, precise arithmetic for the ``calculate`` tool.

The evaluator is built per call and locked down twice. First, an AST allowlist
reduces the grammar to numeric literals, the named constants, whitelisted
function calls, and arithmetic; there are no attributes, subscripts,
comparisons, strings, or comprehensions. Second, the power operator refuses an
exponent that could allocate an enormous integer *before* it runs. Every result
is normalized to a finite number and every failure becomes a short
``CalculationError`` message that is safe to show to the user and the model.
"""

import ast
import math
import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from simpleeval import (
    FeatureNotAvailable,
    InvalidExpression,
    NumberTooHigh,
    SimpleEval,
)

from app.module.agent.exception.domain_error import AgentError

MAX_EXPRESSION_CHARS = 300
MAX_EXPONENT = 10_000
MAX_POWER_BITS = 100_000
MAX_RESULT_BITS = 100_000
SIGNIFICANT_DIGITS = 12

# ``ast.Expression`` is the parse root; the operator and ``Load`` context nodes
# are visited by ``ast.walk`` and therefore have to be allowed explicitly.
_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Call,
    ast.Name,
    ast.List,
    ast.Tuple,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
)

_SAFE_CONSTANTS: dict[str, float] = {"pi": math.pi, "e": math.e, "tau": math.tau}


class CalculationError(AgentError):
    """An expression that is invalid, too large, or not a finite number."""


@dataclass(frozen=True)
class CalculationResult:
    """One evaluated expression, its numeric value, and its display form."""

    expression: str
    result: int | float
    formatted: str


def evaluate_expression(expression: str) -> CalculationResult:
    """Evaluate one arithmetic expression and normalize the result.

    A fresh evaluator is created for every call, so no mutable state is shared
    between turns or between parallel tool calls.
    """
    source = expression.strip()
    if not source:
        raise CalculationError("expression is empty.")
    if len(source) > MAX_EXPRESSION_CHARS:
        raise CalculationError("expression is too long.")
    tree = _parse(source)
    try:
        value = _SafeEvaluator().eval(source, previously_parsed=tree.body)
    except ZeroDivisionError as exc:
        raise CalculationError("division by zero.") from exc
    except NumberTooHigh as exc:
        raise CalculationError("the result is too large.") from exc
    except OverflowError as exc:
        raise CalculationError("the result is too large.") from exc
    except (InvalidExpression, FeatureNotAvailable) as exc:
        raise CalculationError("expression is invalid.") from exc
    except (ArithmeticError, RecursionError, TypeError, ValueError) as exc:
        raise CalculationError("expression is invalid.") from exc
    normalized = _normalize_result(value)
    return CalculationResult(
        expression=source,
        result=normalized,
        formatted=_format_result(normalized),
    )


class _SafeEvaluator(SimpleEval):
    """A per-call evaluator with arithmetic operators and a bounded power."""

    def __init__(self) -> None:
        super().__init__(
            operators=dict(_OPERATORS),
            functions=dict(_SAFE_FUNCTIONS),
            names=dict(_SAFE_CONSTANTS),
        )
        # simpleeval dispatches ``ast.Pow`` through its operator table; it has
        # no ``_eval_power`` hook, so the guarded implementation is bound here.
        self.operators[ast.Pow] = self._power
        # simpleeval has no list/tuple node by default. The parser only admits
        # literal numbers inside them, so these handlers stay numeric.
        self.nodes[ast.List] = self._eval_numeric_sequence
        self.nodes[ast.Tuple] = self._eval_numeric_sequence

    def _eval_numeric_sequence(self, node: Any) -> list[int | float]:
        """Evaluate a literal list/tuple whose items the parser already checked."""
        return [element.value for element in node.elts]

    def _power(self, base: Any, exponent: Any) -> Any:
        """Reject an exponent that would allocate an enormous integer."""
        if isinstance(base, bool) or not isinstance(base, (int, float)):
            raise NumberTooHigh("the base must be a number")
        if isinstance(exponent, bool) or not isinstance(exponent, (int, float)):
            raise NumberTooHigh("the exponent must be a number")
        if abs(exponent) > MAX_EXPONENT:
            raise NumberTooHigh("the exponent is too large")
        # The estimate must happen before ``base ** exponent`` runs, otherwise a
        # single 9 ** 9 ** 9 would already be materialized. ``bit_length`` is
        # the exact number of significant bits in the integer base.
        if type(base) is int and type(exponent) is int and exponent > 0:
            if max(base.bit_length(), 1) * exponent > MAX_POWER_BITS:
                raise NumberTooHigh("the result is too large")
        return base**exponent


_OPERATORS: dict[type[ast.AST], Callable[..., Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _numbers(values: tuple[Any, ...]) -> list[int | float]:
    """Flatten an optional single list/tuple and require numeric items only."""
    if len(values) == 1 and isinstance(values[0], (list, tuple)):
        items: list[Any] = list(values[0])
    else:
        items = list(values)
    numbers: list[int | float] = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError("numeric arguments are required")
        numbers.append(item)
    return numbers


def _sum(*values: Any) -> int | float:
    """Sum a single list/tuple or the positional numbers."""
    numbers = _numbers(values)
    if not numbers:
        raise ValueError("sum needs at least one number")
    return sum(numbers)


def _minimum(*values: Any) -> int | float:
    """Return the smallest of a single list/tuple or the positional numbers."""
    numbers = _numbers(values)
    if not numbers:
        raise ValueError("min needs at least one number")
    return min(numbers)


def _maximum(*values: Any) -> int | float:
    """Return the largest of a single list/tuple or the positional numbers."""
    numbers = _numbers(values)
    if not numbers:
        raise ValueError("max needs at least one number")
    return max(numbers)


def _mean(*values: Any) -> int | float:
    """Return the arithmetic mean of a single list/tuple or positional numbers."""
    numbers = _numbers(values)
    if not numbers:
        raise ValueError("mean needs at least one number")
    return sum(numbers) / len(numbers)


_SAFE_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "abs": abs,
    "round": round,
    "min": _minimum,
    "max": _maximum,
    "sum": _sum,
    "avg": _mean,
    "mean": _mean,
    "sqrt": math.sqrt,
    "exp": math.exp,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "floor": math.floor,
    "ceil": math.ceil,
    "trunc": math.trunc,
    "radians": math.radians,
    "degrees": math.degrees,
    "hypot": math.hypot,
    "fabs": math.fabs,
}


def _parse(source: str) -> ast.Expression:
    """Parse ``source`` as one expression and enforce the AST allowlist."""
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise CalculationError("expression is invalid.") from exc
    # A whitelisted function name is only legal as the ``func`` of a call; the
    # same identifier used as a bare value stays rejected like any other name.
    call_functions = {
        id(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise CalculationError("expression is invalid.")
        if isinstance(node, ast.Constant):
            # ``type`` rather than ``isinstance`` so bool and complex literals
            # (both subclasses or numeric lookalikes) never slip through.
            if type(node.value) not in (int, float):
                raise CalculationError("expression is invalid.")
        elif isinstance(node, ast.Name):
            if node.id not in _SAFE_CONSTANTS and id(node) not in call_functions:
                raise CalculationError("expression is invalid.")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCTIONS:
                raise CalculationError("expression is invalid.")
            if node.keywords:
                raise CalculationError("expression is invalid.")
        elif isinstance(node, (ast.List, ast.Tuple)):
            if any(
                not isinstance(element, ast.Constant)
                or type(element.value) not in (int, float)
                for element in node.elts
            ):
                raise CalculationError("expression is invalid.")
    return tree


def _normalize_result(value: Any) -> int | float:
    """Accept a finite int or float and round floats to 12 significant digits."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalculationError("the result is not a number.")
    if isinstance(value, int):
        if value.bit_length() > MAX_RESULT_BITS:
            raise CalculationError("the result is too large.")
        return value
    if not math.isfinite(value):
        raise CalculationError("the result is not a finite number.")
    rounded = float(format(value, f".{SIGNIFICANT_DIGITS}g"))
    if not math.isfinite(rounded):
        raise CalculationError("the result is too large.")
    # An integral float is reported as an int so ``19.0`` never reaches the UI
    # as a misleading decimal. Very large magnitudes stay float because their
    # integer form would be noise.
    if rounded.is_integer() and abs(rounded) < 1e15:
        return int(rounded)
    return rounded


def _format_result(value: int | float) -> str:
    """Render the display form with at most 12 significant digits."""
    if isinstance(value, int):
        return str(value)
    return format(value, f".{SIGNIFICANT_DIGITS}g")
