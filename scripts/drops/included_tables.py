"""Bounded expansion of parameterized /Drops source templates.

This is intentionally a small Wiki interpreter, not arbitrary template execution.
Unknown expressions in a drop row fail the export rather than inventing a rate.

Copyright (c) 2026, TSPS contributors.
Distributed under the GNU General Public License, version 3 or later,
without any warranty. See the repository LICENSE for the full terms.
"""

import ast
import html
import math
import re
from fractions import Fraction
from functools import cache

import mwparserfromhell


DROP_ROWS = ("dropsline", "dropslineclue")
RATE_FIELDS = ("rarity", "altrarity")


def template_titles(text):
    return list(
        dict.fromkeys(
            str(t.name).strip()
            for t in mwparserfromhell.parse(text).filter_templates()
            if str(t.name).strip().lower().endswith("/drops")
        )
    )


def number(expression, exact=False):
    from scripts.drops.drops_wikitext import evaluate_expression

    expression = expression.strip().replace("^", "**")
    rounded = re.search(r"\s+round\s+(-?\d+)\s*$", expression, re.I)
    body = expression[: rounded.start()] if rounded else expression
    tree = ast.parse(body, mode="eval")
    if len(list(ast.walk(tree))) > 128:
        raise ValueError("Oversized included drop expression")

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            result = Fraction(str(node.value))
        elif isinstance(node, ast.UnaryOp) and isinstance(
            node.op, (ast.UAdd, ast.USub)
        ):
            result = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                result = a + b
            elif isinstance(node.op, ast.Sub):
                result = a - b
            elif isinstance(node.op, ast.Mult):
                result = a * b
            elif isinstance(node.op, ast.Div):
                result = a / b
            elif isinstance(node.op, ast.Pow) and abs(b) <= 16:
                result = a**b
            else:
                raise ValueError("Unsupported included drop operator")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and not node.keywords
        ):
            funcs = {"floor": math.floor, "sqrt": math.sqrt, "min": min, "max": max}
            if node.func.id not in funcs:
                raise ValueError("Unsupported included drop function")
            result = funcs[node.func.id](*[visit(a) for a in node.args])
        elif isinstance(node, ast.Compare) and len(node.ops) == 1:
            a, b = visit(node.left), visit(node.comparators[0])
            op = node.ops[0]
            if isinstance(op, ast.Lt):
                result = a < b
            elif isinstance(op, ast.Gt):
                result = a > b
            elif isinstance(op, ast.LtE):
                result = a <= b
            elif isinstance(op, ast.GtE):
                result = a >= b
            elif isinstance(op, ast.Eq):
                result = a == b
            elif isinstance(op, ast.NotEq):
                result = a != b
            else:
                raise ValueError("Unsupported included drop comparison")
        else:
            raise ValueError("Unsupported included drop expression")
        if not math.isfinite(result) or abs(result) > 1e15:
            raise ValueError("Unbounded included drop expression")
        return result

    value = visit(tree.body)
    if exact:
        value = Fraction(value)
        return (
            str(value.numerator)
            if value.denominator == 1
            else f"{value.numerator}/{value.denominator}"
        )
    value = float(value)
    suffix = rounded.group(0) if rounded else ""
    if not rounded:
        return format(value, ".15f").rstrip("0").rstrip(".") or "0"
    result = evaluate_expression(format(value, ".15f") + suffix)
    if result is None:
        raise ValueError("Invalid included drop expression")
    return result


def expand(text, templates, page_title="", stack=()):
    if templates is None:
        return text
    if len(stack) > 12:
        raise ValueError("Included drop template depth exceeded")
    code = mwparserfromhell.parse(text)
    # Only include sources are interpreted; ordinary monster pages are unchanged.
    for template in reversed(code.filter_templates()):
        name = str(template.name).strip()
        if not name.lower().endswith("/drops"):
            continue
        if name in stack or name not in templates:
            raise ValueError(f"Missing or cyclic included drop template: {name}")
        params = {str(p.name).strip(): str(p.value) for p in template.params}
        body = re.sub(
            r"<noinclude>.*?</noinclude>", "", templates[name], flags=re.S | re.I
        )
        body = re.sub(r"</?includeonly>", "", body, flags=re.I)
        body_code = mwparserfromhell.parse(body)
        for argument in reversed(body_code.filter_arguments()):
            key = str(argument.name).strip()
            value = params.get(
                key, str(argument.default) if argument.default is not None else ""
            )
            body_code.replace(argument, value)
        body = expand(str(body_code), templates, page_title, (*stack, name))
        body = interpret(body, page_title)
        code.replace(template, body)
    return str(code)


def _escape_ifexpr_comparisons(text):
    # Preserve real markup in the branches. A pipe ends the condition only
    # if it belongs to the #ifexpr itself, so track nested template arguments.
    frames = []
    conditions = 0

    def escape_token(match):
        nonlocal conditions
        token = match[0]
        if token.startswith("{{"):
            condition = token.endswith(":")
            frames.append((3 if token == "{{{" else 2, condition))
            conditions += condition
        elif token.startswith("}}"):
            remaining = len(token)
            while frames and remaining >= frames[-1][0]:
                width, condition = frames.pop()
                remaining -= width
                conditions -= condition
        elif token == "|":
            if frames and frames[-1][1]:
                frames[-1] = (2, False)
                conditions -= 1
        elif conditions:
            return html.escape(token)
        return token

    return re.sub(
        r"\{\{\s*#ifexpr:|\{\{\{?|\}{2,}|[|<>]", escape_token, text, flags=re.I
    )


def interpret(text, page_title):
    # The wikitext tokenizer would otherwise treat comparisons as HTML tags.
    text = _escape_ifexpr_comparisons(text)

    def bind_variable(expression, variables, depth):
        # A rate can use the unrounded form of a variable, including earlier
        # definitions it referenced. Keep the scope at the point of assignment.
        scope = variables.copy()

        @cache
        def rate():
            return render(expression, scope.copy(), depth, exact=True)

        return render(expression, variables, depth), rate

    def render(value, variables, depth=0, exact=False):
        if depth > 32:
            raise ValueError("Cyclic included drop variable")

        def nested(value, exact=exact):
            return render(value, variables, depth + 1, exact)

        code = mwparserfromhell.parse(value)
        for t in list(code.filter_templates(recursive=False)):
            name = str(t.name).strip()
            key, _, argument = name.partition(":")
            key = key.lower()
            args = [str(p.value) for p in t.params]
            result = None
            if key in ("#vardefine", "#vardefineecho"):
                defined, rate = bind_variable(
                    args[0] if args else "", variables, depth + 1
                )
                variables[argument.strip().lower()] = (defined, rate)
                result = (
                    (rate() if exact else defined) if key == "#vardefineecho" else ""
                )
            elif key == "#var":
                variable = variables.get(argument.strip().lower())
                if variable is None:
                    result = nested(args[0]) if args else ""
                else:
                    defined, rate = variable
                    result = rate() if exact else defined
            elif key == "pagename":
                result = page_title
            elif key == "#expr":
                try:
                    result = number(nested(argument), exact=exact)
                    if exact and "/" in result:
                        result = f"({result})"
                except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
                    pass
            elif key == "min" or key == "max":
                try:
                    result = number(
                        key + "(" + ",".join(nested(a) for a in args) + ")",
                        exact=exact,
                    )
                    if exact and "/" in result:
                        result = f"({result})"
                except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
                    pass
            elif key == "#if":
                branch = 0 if nested(argument, exact=False).strip() else 1
                result = nested(args[branch]) if branch < len(args) else ""
            elif key == "#ifexpr":
                try:
                    truth = (
                        float(number(html.unescape(nested(argument, exact=False)))) != 0
                    )
                except (
                    ValueError,
                    SyntaxError,
                    ZeroDivisionError,
                    OverflowError,
                ) as exc:
                    raise ValueError("Unresolved included drop condition") from exc
                branch = 0 if truth else 1
                result = nested(args[branch]) if branch < len(args) else ""
            elif key == "#switch":
                selected = nested(argument, exact=False).strip()
                default = ""
                fallthrough = False
                for index, p in enumerate(t.params):
                    case = str(p.name).strip()
                    value = str(p.value)
                    if not p.showkey:
                        if index == len(t.params) - 1:
                            default = value
                        elif not fallthrough:
                            fallthrough = nested(value, exact=False).strip() == selected
                        continue
                    if case == "#default":
                        default = value
                    if case == selected or fallthrough:
                        result = nested(value)
                        break
                if result is None:
                    result = nested(default)
            if result is None:
                for p in t.params:
                    rate_field = (
                        key in DROP_ROWS and str(p.name).strip().lower() in RATE_FIELDS
                    )
                    rendered = nested(str(p.value), exact=exact or rate_field)
                    if rate_field and re.fullmatch(r"[\d\s.()+*/-]+", rendered):
                        rendered = number(rendered, exact=True)
                    p.value = rendered
            else:
                code.replace(t, result)
        return str(code)

    output = render(text, {})
    control = re.search(r"\{\{\s*(#(?:if\w*|switch)\b)", output, flags=re.I)
    if control:
        raise ValueError(f"Unresolved included drop control: {control[1]}")
    for t in mwparserfromhell.parse(output).filter_templates():
        key = str(t.name).strip().lower()
        if key.endswith("/drops") or (
            key.startswith("#")
            and any(
                str(child.name).strip().lower() in DROP_ROWS
                for child in mwparserfromhell.parse(str(t)).filter_templates()[1:]
            )
        ):
            raise ValueError(f"Unresolved included drop control: {t.name}")
        if key in DROP_ROWS:
            for p in t.params:
                if str(p.name).strip().lower() in (
                    "quantity",
                    *RATE_FIELDS,
                ) and "{{" in str(p.value):
                    raise ValueError(f"Unresolved included drop field: {p}")
    return output


def split_versions(body):
    """Duplicate common blocks, retaining one declared condition per table."""
    blocks = list(
        re.finditer(
            r"\{\{DropsTableHead\b.*?\{\{DropsTableBottom\}\}", body, re.S | re.I
        )
    )
    versions = []
    for block in blocks:
        head = mwparserfromhell.parse(block.group()).filter_templates()[0]
        if head.has("dropversion"):
            version = str(head.get("dropversion").value).strip()
            if version not in versions:
                versions.append(version)
    if len(versions) < 2:
        return None
    result = []
    for version in versions:
        text, cursor = "", 0
        for block in blocks:
            head = mwparserfromhell.parse(block.group()).filter_templates()[0]
            keep = (
                not head.has("dropversion")
                or str(head.get("dropversion").value).strip() == version
            )
            text += body[cursor : block.start()]
            if keep:
                text += block.group()
            cursor = block.end()
        result.append((version, text + body[cursor:]))
    return result


# Source policy describes roll structure, never item rows or repaired output.
# https://oldschool.runescape.wiki/w/Template:Revenants/Drops
# Its unique and secondary rolls are separate from the ancient/main/coins roll.
INDEPENDENT_SOURCE_SECTIONS = {
    "revenants/drops": ("unique", "unique (on-task)", "secondary")
}


def independent_sections(names):
    return {
        section
        for name in names
        for section in INDEPENDENT_SOURCE_SECTIONS.get(name.lower(), ())
    }


def mark_independent_pools(drops, independent_sections):
    """Mark source sections that roll separately from the ordinary main pool."""
    for drop in drops:
        section = drop.subsection.lower()
        if drop.section == "Main" and section in independent_sections:
            drop.roll_group = section
