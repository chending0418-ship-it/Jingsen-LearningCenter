"""Bounded polynomial input, deterministic exercises and exact factorization grading.

Student text is parsed by our small grammar, never by eval/sympify/parse_expr.
The original expression tree is kept so equivalent but unfinished answers fail.
"""

from __future__ import annotations

import random
import re
import uuid
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

import sympy as sp


VARIABLES = "xyabm"
SYMBOLS = sp.symbols("x y a b m")
X, Y, A, B, M = SYMBOLS
ZERO_POWER = (0,) * len(VARIABLES)
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
    "quadratic": "十字相乘",
    "negative_leading": "负首项与符号处理",
    "rational_square": "分数配方与平方差",
    "reverse_bracket": "相反括号与连续分解",
    "power_common": "幂的公因式与完全平方",
    "nested_square": "整体公式与彻底分解",
}


class MathInputError(ValueError):
    """A correctable input problem; it does not consume the first attempt."""


def _bounded(values):
    values = {power: Fraction(value) for power, value in dict(values).items() if value}
    if (len(values) > 100 or any(sum(power) > MAX_DEGREE for power in values)
            or any(abs(v.numerator) > 10**10 or v.denominator > 10**6 for v in values.values())):
        raise MathInputError("式子的次数、项数或数字过大，请检查输入。")
    return tuple(sorted(values.items()))


def _constant(value):
    return _bounded({ZERO_POWER: value})


def _add(a, b, sign=1):
    values = dict(a)
    for power, value in b:
        values[power] = values.get(power, 0) + sign * value
    return _bounded(values)


def _multiply(a, b):
    values = {}
    for left, v in a:
        for right, w in b:
            power = tuple(i + j for i, j in zip(left, right))
            if sum(power) > MAX_DEGREE:
                raise MathInputError("式子的次数过大，请检查平方的位置。")
            values[power] = values.get(power, 0) + v * w
    return _bounded(values)


def _polynomial(coefficients):
    return sum(sp.Rational(value.numerator, value.denominator)
               * sp.prod(symbol**power for symbol, power in zip(SYMBOLS, powers))
               for powers, value in coefficients)


@dataclass(frozen=True)
class Expression:
    coefficients: tuple
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
        raise MathInputError("最终答案只填写原题字母的因式乘积；换元等式可以写在草稿中。")
    tokens = re.findall(r"\d+|[xyabm]|[+*/^()\-]", source)
    if "".join(tokens) != source or len(tokens) > 160:
        raise MathInputError("支持整数、数字分数、x/y/a/b/m、括号、加减乘和 1—8 次方。")
    position = 0
    depth = 0

    def peek():
        return tokens[position] if position < len(tokens) else ""

    def atom():
        nonlocal position, depth
        current = peek()
        if current in VARIABLES and current:
            position += 1
            power = tuple(int(v == current) for v in VARIABLES)
            result = Expression(_bounded({power: 1}))
        elif current.isdigit():
            if len(current) > 5:
                raise MathInputError("单个数字不能超过五位，请检查输入。")
            position += 1
            result = Expression(_constant(int(current)))
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
            raise MathInputError("这里还缺少数字、原题字母或完整的括号。")
        if peek() == "^":
            position += 1
            exponent = peek()
            if exponent not in {str(i) for i in range(1, 9)}:
                raise MathInputError("指数需要是 1—8 的整数。")
            position += 1
            coefficients = _constant(1)
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
            result = Expression(_multiply(_constant(-1), result.coefficients), "multiply", (Expression(_constant(-1)), result))
        return result

    def product():
        nonlocal position
        result = unary()
        while peek() in ("*", "/", "(") or (peek() and peek() in VARIABLES) or peek().isdigit():
            if peek() == "/":
                position += 1
                denominator = peek()
                if not denominator.isdigit() or len(denominator) > 5 or int(denominator) == 0:
                    raise MathInputError("分母须为非零正整数，例如 1/4 或 (x+y)/2。")
                position += 1
                right = Expression(_constant(Fraction(1, int(denominator))))
                result = Expression(_multiply(result.coefficients, right.coefficients), "multiply", (result, right))
                continue
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
        polynomial = sp.Poly(_polynomial(coefficients), *SYMBOLS, domain=sp.QQ)
        if polynomial.total_degree() == 0:
            continue
        content, factors = polynomial.factor_list()
        # Rational scalar normalizations are equivalent (x-y/2 vs (2x-y)/2).
        # A non-unit integer common factor still needs to be extracted.
        if abs(content.p) != 1 or len(factors) != 1 or factors[0][1] != 1:
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
    """Ten varied exercises, aligned to the supplied seven-grade week-2 sheet.

    Retain the existing 8+2 session contract; rotate the sheet's fifteen structures.
    Symbolic n exponents are instantiated to small integer powers for bounded input.
    """
    rng = rng or random.SystemRandom()
    questions = []

    def push(expression, skill, hints, steps, challenge=False):
        if not isinstance(expression, str):
            expression = math_text(sp.expand(expression))
        parsed = parse_expression(expression)
        answer = math_text(sp.factor(_polynomial(parsed.coefficients)))
        questions.append({
            "id": str(uuid.uuid4()), "position": len(questions) + 1,
            "skill": skill, "skill_label": SKILLS[skill],
            "is_challenge": challenge, "expression": expression,
            "correct_answer": answer, "hints": hints,
            "solution_steps": steps + [f"最终答案：{answer}"],
        })

    p, q = rng.randint(2, 8), rng.randint(1, 5)
    while p == q:
        q = rng.randint(1, 5)
    push(X**2 + (q-p)*X - p*q, "quadratic",
         ["找两个数，乘积等于常数项，和等于一次项系数。", f"这两个数是 {-p} 和 {q}。"],
         [f"因为 ({-p})×{q}={-p*q}，且 {-p}+{q}={q-p}，所以用十字相乘。"])

    p, q = sorted(rng.sample(range(1, 8), 2))
    push(-X**2+(p+q)*X-p*q, "negative_leading",
         ["首项为负，先提取 −1。", f"括号内变成 x²−{p+q}x+{p*q}，再找和为 {-p-q} 的两个数。"],
         [f"原式 = −(x²−{p+q}x+{p*q})。", f"括号内分解为 (x−{p})(x−{q})，保留外面的负号。"])

    p, q = rng.randint(3, 7), rng.randint(1, 2)
    push(X*(X-p)*(X+q), "mixed_methods",
         ["先提取每项共有的 x。", f"提取 x 后得到 x²−{p-q}x−{p*q}，再用十字相乘。"],
         [f"先提取 x，再将 x²−{p-q}x−{p*q} 分解为 (x−{p})(x+{q})。"])

    if rng.choice([True, False]):
        push("a^3-2*a^2*b+a*b^2", "perfect_square",
             ["先提公因式，再看括号里的三项。", "提取 a 后，a²−2ab+b² 是完全平方式。"],
             ["原式 = a(a²−2ab+b²)。", "括号内 = (a−b)²。"])
    else:
        push("a^2*(x-y)+b^2*(y-x)", "reverse_bracket",
             ["两个括号互为相反数，先统一方向。", "y−x = −(x−y)，因此可提出 (x−y)。"],
             ["原式 = (x−y)(a²−b²)。", "继续将 a²−b² 分解为 (a−b)(a+b)。"])

    p, q = rng.choice([(6, 4), (8, 3), (9, 3), (5, 2)])
    inner = rng.choice(["(a-b)", "(2*x+y)"])
    push(f"{inner}^2-{p-q}*{inner}-{p*q}", "common_expression",
         ["把重复出现的整个括号看成一个新字母。", f"令 t={inner}，得到 t²−{p-q}t−{p*q}。"],
         [f"令 t={inner}，用十字相乘得到 (t−{p})(t+{q})。", "将 t 换回原来的括号，并检查各因式。"])

    if rng.choice([True, False]):
        k = rng.choice([2, 3, 4])
        push(f"3*a*(a+b)^2-{3*k*k}*a*b^2", "mixed_methods",
             ["先提取公因式 3a。", f"括号内为 (a+b)²−({k}b)²，可用平方差公式。"],
             [f"原式 = 3a((a+b)²−{k*k}b²)。", f"平方差得到 3a(a+b−{k}b)(a+b+{k}b)，合并同类项。"])
    else:
        n = rng.randint(2, 4)
        push(f"4*x^{n+1}*y^{n+1}-8*x^{n}*y^{n}+4*x^{n-1}*y^{n-1}", "power_common",
             ["字母公因式取各项中相同字母的最低次幂。", f"提取 4x^{n-1}y^{n-1} 后，括号内为 x²y²−2xy+1。"],
             [f"提取 4x^{n-1}y^{n-1}。", "将 xy 看成整体，x²y²−2xy+1 = (xy−1)²。"])

    d = rng.choice([2, 3, 4])
    push(f"x^2-2/{d}*x*y+1/{d*d}*y^2-1", "rational_square",
         ["先将含 x、y 的三项配成完全平方，再观察剩下的 −1。", f"前三项 = (x−y/{d})²，因此是 (x−y/{d})²−1。"],
         [f"原式 = (x−y/{d})²−1。", f"用平方差公式得到 (x−y/{d}−1)(x−y/{d}+1)。分数系数的等价写法也可。"])

    r = rng.randint(1, 3)
    push(f"m^2*(m-{r})-{4*r}*({r}-m)^2", "reverse_bracket",
         [f"注意 ({r}−m)² = (m−{r})²，平方后不再多一个负号。", f"提取 m−{r}，得到 (m−{r})(m²−{4*r}(m−{r}))。"],
         [f"统一括号方向后提取 m−{r}，得到 (m−{r})(m²−{4*r}m+{4*r*r})。", f"后一个括号是完全平方式 (m−{2*r})²，继续分解到底。"])

    c = rng.choice([2, 4, 6])
    # t²−t−c(c+1)=(t−c−1)(t+c), with t=x²+cx.
    push(f"(x^2+{c}*x)^2-(x^2+{c}*x)-{c*(c+1)}", "substitution",
         ["重复出现的二次式也可以整体换元。", f"令 t=x²+{c}x，得到 t²−t−{c*(c+1)}。", f"分解为 (t−{c+1})(t+{c})；换回 x 后还要逐个检查。"],
         [f"令 t=x²+{c}x，先分解为 (t−{c+1})(t+{c})。", f"换回得到 (x²+{c}x−{c+1})(x²+{c}x+{c})。", f"第一因式 = (x−1)(x+{c+1})；再检查另一个二次因式。"], True)

    k = rng.choice([1, 2, 3])
    if rng.choice([True, False]):
        push(f"(x^2+{k*k})^2-{4*k*k}*x^2", "nested_square",
             ["先把 x² 加常数作为整体，用平方差公式。", f"得到 (x²+{k*k}−{2*k}x)(x²+{k*k}+{2*k}x)。", "两个二次因式都是完全平方式，需要继续分解。"],
             [f"原式 = (x²−{2*k}x+{k*k})(x²+{2*k}x+{k*k})。", f"两个括号分别是 (x−{k})² 和 (x+{k})²。"], True)
    else:
        push(f"(x^2+{k*k})^2-{4*k}*x*(x^2+{k*k})+{4*k*k}*x^2", "nested_square",
             ["把 x² 加常数看成 A，把含 x 的一次式看成 B，观察 A²−2AB+B²。", f"整体配方得到 (x²+{k*k}−{2*k}x)²。", "里面的三项还能再写成一个完全平方。"],
             [f"原式 = ((x²+{k*k})−{2*k}x)²。", f"内层 = (x−{k})²，因此原式 = (x−{k})⁴。"], True)

    return questions
