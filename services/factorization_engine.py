"""Bounded polynomial input, deterministic exercises and exact factorization grading.

Student text is parsed by our small grammar, never by eval/sympify/parse_expr.
The original expression tree is kept so equivalent but unfinished answers fail.
"""

from __future__ import annotations

import random
import re
import uuid
from dataclasses import dataclass
from typing import Optional

import sympy as sp


X = sp.Symbol("x")
MAX_LENGTH = 240
MAX_DEGREE = 12
SKILLS = {
    "common_factor": "提公因式",
    "common_expression": "括号公因式",
    "difference_squares": "平方差公式",
    "perfect_square": "完全平方公式",
    "repeated_squares": "连续平方差",
    "mixed_methods": "多方法综合",
    "substitution": "换元与整体观察",
    "completion": "添项与配方",
}


class MathInputError(ValueError):
    """A correctable input problem; it does not consume the first attempt."""


def _bounded(values) -> tuple[int, ...]:
    values = list(values)
    while len(values) > 1 and values[-1] == 0:
        values.pop()
    if len(values) > MAX_DEGREE + 1 or any(abs(v) > 10**10 for v in values):
        raise MathInputError("式子的次数或数字过大，请检查输入。")
    return tuple(values)


def _add(a, b, sign=1):
    return _bounded((a[i] if i < len(a) else 0) + sign * (b[i] if i < len(b) else 0)
                    for i in range(max(len(a), len(b))))


def _multiply(a, b):
    if len(a) + len(b) - 2 > MAX_DEGREE:
        raise MathInputError("式子的次数过大，请检查平方的位置。")
    values = [0] * (len(a) + len(b) - 1)
    for i, left in enumerate(a):
        for j, right in enumerate(b):
            values[i + j] += left * right
    return _bounded(values)


@dataclass(frozen=True)
class Expression:
    coefficients: tuple[int, ...]
    kind: str = "atom"
    children: tuple[Expression, ...] = ()


def parse_expression(text: str) -> Expression:
    if not text or len(text) > MAX_LENGTH:
        raise MathInputError(f"请输入答案，最多 {MAX_LENGTH} 个字符。")
    superscripts = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
    source = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", lambda m: "^" + m[0].translate(superscripts), text)
    source = source.translate(str.maketrans({"−": "-", "–": "-", "×": "*", "·": "*", "（": "(", "）": ")"}))
    source = re.sub(r"\s+", "", source.replace("**", "^")).lower()
    if "=" in source or "t" in source:
        raise MathInputError("最终答案只填写含 x 的因式乘积；换元等式可以写在草稿中。")
    tokens = re.findall(r"\d+|x|[+*^()\-]", source)
    if "".join(tokens) != source or len(tokens) > 160:
        raise MathInputError("仅支持整数、x、括号、加减乘和 1—8 次方。")
    position = 0
    depth = 0

    def peek():
        return tokens[position] if position < len(tokens) else ""

    def atom():
        nonlocal position, depth
        current = peek()
        if current == "x":
            position += 1
            result = Expression((0, 1))
        elif current.isdigit():
            if len(current) > 5:
                raise MathInputError("单个数字不能超过五位，请检查输入。")
            position += 1
            result = Expression((int(current),))
        elif current == "(":
            depth += 1
            if depth > 12:
                raise MathInputError("括号层数过多，请简化输入。")
            position += 1
            result = sum_expression()
            if peek() != ")":
                raise MathInputError("请补齐右括号。")
            position += 1
            depth -= 1
        else:
            raise MathInputError("这里还缺少数字、x 或完整的括号。")
        if peek() == "^":
            position += 1
            exponent = peek()
            if exponent not in {str(i) for i in range(1, 9)}:
                raise MathInputError("指数需要是 1—8 的整数。")
            position += 1
            coefficients = (1,)
            for _ in range(int(exponent)):
                coefficients = _multiply(coefficients, result.coefficients)
            result = Expression(coefficients, "power", (result,) * int(exponent))
        return result

    def unary():
        nonlocal position
        # Iterative signs prevent deeply nested unary recursion from user input.
        sign = 1
        while peek() in ("+", "-"):
            if peek() == "-":
                sign *= -1
            position += 1
        result = atom()
        if sign == -1:
            result = Expression(_multiply((-1,), result.coefficients), "multiply", (Expression((-1,)), result))
        return result

    def product():
        nonlocal position
        result = unary()
        while peek() == "*" or peek() == "x" or peek() == "(" or peek().isdigit():
            if peek() == "*":
                position += 1
            right = unary()
            result = Expression(_multiply(result.coefficients, right.coefficients), "multiply", (result, right))
        return result

    def sum_expression():
        nonlocal position
        result = product()
        while peek() in ("+", "-"):
            sign = -1 if peek() == "-" else 1
            position += 1
            right = product()
            result = Expression(_add(result.coefficients, right.coefficients, sign), "sum", (result, right))
        return result

    result = sum_expression()
    if position != len(tokens):
        raise MathInputError("请检查括号或指数的位置。")
    return result


def _leaves(expression):
    if expression.kind in ("multiply", "power"):
        for child in expression.children:
            yield from _leaves(child)
    else:
        yield expression.coefficients


def fully_factored(expression: Expression) -> bool:
    for coefficients in _leaves(expression):
        if len(coefficients) == 1:
            continue
        polynomial = sp.Poly.from_list(list(reversed(coefficients)), X, domain=sp.ZZ)
        content, factors = polynomial.factor_list()
        if abs(content) != 1 or len(factors) != 1 or factors[0][1] != 1:
            return False
    return True


def grade_answer(question: dict, answer: str, skipped: bool = False) -> dict:
    if skipped:
        return {"correct": False, "error_code": "skipped", "feedback": "本题暂未完成，可以对照解析再试一次。"}
    actual = parse_expression(answer)
    expected = parse_expression(question["expression"])
    if actual.coefficients != expected.coefficients:
        return {"correct": False, "error_code": "not_equivalent", "feedback": "展开后与原式不同，请检查各项系数、正负号和乘法。"}
    if not fully_factored(actual):
        return {"correct": False, "error_code": "incomplete", "feedback": "变形正确，但还没有分解彻底。检查公因式和每个括号能否继续分解。"}
    return {"correct": True, "error_code": None, "feedback": "正确，已经分解彻底。"}


def math_text(expression) -> str:
    return str(expression).replace("**", "^")


def generate_questions(rng: Optional[random.Random] = None) -> list[dict]:
    rng = rng or random.SystemRandom()
    questions = []

    def push(expression, skill, hints, steps, challenge=False):
        if not isinstance(expression, str):
            expression = math_text(sp.expand(expression))
        parsed = parse_expression(expression)
        polynomial = sum(value * X**i for i, value in enumerate(parsed.coefficients))
        answer = math_text(sp.factor(polynomial))
        questions.append({
            "id": str(uuid.uuid4()), "position": len(questions) + 1,
            "skill": skill, "skill_label": SKILLS[skill],
            "is_challenge": challenge, "expression": expression,
            "correct_answer": answer, "hints": hints,
            "solution_steps": steps + [f"最终答案：{answer}"],
        })

    c, a = rng.randint(2, 6), rng.randint(2, 7)
    push(c * X * (X + a), "common_factor",
         ["先观察系数和字母有没有共同的部分。", f"两项都含有 {c}x，先把它提出来。"],
         [f"数字公因数是 {c}，两项还都含有 x。", f"提取 {c}x，括号中留下 x + {a}。"])

    a, b = rng.sample(range(1, 7), 2)
    push(f"x*(x+{a})+{b}*(x+{a})", "common_expression",
         ["一个括号也可以看作整体的公因式。", f"两项都含有 (x + {a})。"],
         [f"把 (x + {a}) 作为整体提取，剩下 x + {b}。"])

    a, b = rng.choice([(a, b) for a in range(1, 4) for b in range(2, 8) if sp.gcd(a, b) == 1])
    push(a*a*X**2 - b*b, "difference_squares",
         ["这两项分别是谁的平方？", f"利用 A² − B² = (A − B)(A + B)，这里 A = {a}x，B = {b}。"],
         [f"原式是 ({a}x)² − {b}²，使用平方差公式。"])

    a, b, sign = rng.randint(1, 3), rng.randint(1, 5), rng.choice([-1, 1])
    while sp.gcd(a, b) != 1:
        b = rng.randint(1, 5)
    push((a*X + sign*b)**2, "perfect_square",
         ["检查首尾是否为平方，中间项是否等于两者乘积的两倍。", f"首尾对应 {a}x 和 {b}，再根据中间项确定正负号。"],
         ["首尾是平方项，中间项符合完全平方公式。"])

    a = rng.randint(2, 4)
    push(X**4 - a**4, "repeated_squares",
         ["x⁴ 可以看成 (x²)²，先尝试平方差。", f"第一步得到 (x² − {a*a})(x² + {a*a})，第一个括号还能分解。"],
         [f"先得到 (x² − {a*a})(x² + {a*a})。", f"继续分解 x² − {a*a}；x² + {a*a} 在整数系数范围内不能再分解。"])

    a = rng.randint(2, 5)
    push(a**4 - X**4, "repeated_squares",
         ["先把两项看成平方，再检查分解后的每个因式。", f"得到 ({a*a} − x²)({a*a} + x²) 后继续分解第一个括号。"],
         [f"连续使用平方差：({a*a} − x²)({a*a} + x²)。", f"{a*a} − x² = ({a} − x)({a} + x)，注意正负号。"])

    c, a, power = rng.randint(2, 5), rng.randint(2, 4), rng.randint(1, 2)
    push(c*X**power*(X**2-a*a), "mixed_methods",
         ["先提公因式，再检查括号里的结构。", f"提取 {c}x^{power} 后，括号中是 x² − {a*a}。"],
         [f"先提取公因式 {c}x^{power}。", f"将 x² − {a*a} 再按平方差公式分解。"])

    a = rng.randint(1, 4)
    push((X**2-a*a)**2, "mixed_methods",
         ["先把 x² 看作一个整体，检查是否符合完全平方公式。", f"得到 (x² − {a*a})² 后，括号中还可以继续用平方差公式。"],
         [f"先写成 (x² − {a*a})²。", "括号里的平方差也要分解，两个因式都保留外面的平方。"])

    a, b = sorted(rng.sample(range(1, 5), 2))
    push((X**2-a*a)*(X**2-b*b), "substitution",
         ["观察各项的次数，能否把反复出现的部分看作一个新字母？", f"令 t = x²，得到 t² − {a*a+b*b}t + {a*a*b*b}。", f"分解为 (t − {a*a})(t − {b*b})，换回 x 后继续分解。"],
         [f"令 t = x²，原式变为 t² − {a*a+b*b}t + {a*a*b*b}。",
          f"分解为 (t − {a*a})(t − {b*b})。", "把 t 换回 x²，再分别使用平方差公式。"], True)

    if rng.choice([True, False]):
        b = rng.randint(2, 4)
        push(X**4+2*X**2+1-b*b, "completion",
             ["前两项离一个完全平方式还差什么？", "可以补上 +1，同时减去 1，保持原式不变。", f"配成 (x² + 1)² − {b*b} 后，再用平方差。"],
             [f"原式 = x⁴ + 2x² + 1 − 1 + ({1-b*b})。", f"配方得到 (x² + 1)² − {b*b}。", f"分解为 (x² + 1 − {b})(x² + 1 + {b})，再检查是否还能分解。"], True)
    else:
        a = rng.randint(1, 3)
        push(X**4+4*a**4, "completion",
             ["两项是相加的，不能直接套平方差。试着构造一个完全平方。", f"补上 {4*a*a}x²，再减去 {4*a*a}x²。", f"得到 (x² + {2*a*a})² − ({2*a}x)²，再用平方差。"],
             [f"原式 = x⁴ + {4*a*a}x² + {4*a**4} − {4*a*a}x²。", f"写成 (x² + {2*a*a})² − ({2*a}x)²。", "使用平方差公式，得到两个不能继续分解的二次因式。"], True)

    return questions
