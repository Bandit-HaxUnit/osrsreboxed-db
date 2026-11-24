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

import mwparserfromhell


def template_titles(text):
    return list(
        dict.fromkeys(
            str(t.name).strip()
            for t in mwparserfromhell.parse(text).filter_templates()
            if str(t.name).strip().lower().endswith("/drops")
        )
    )


def number(expression):
    from scripts.drops.drops_wikitext import evaluate_expression

    expression = expression.strip().replace("^", "**")
    rounded = re.search(r"\s+round\s+(-?\d+)\s*$", expression, re.I)
    body = expression[: rounded.start()] if rounded else expression
    tree = ast.parse(body, mode="eval")
    if len(list(ast.walk(tree))) > 128:
        raise ValueError("Oversized included drop expression")

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            result = node.value
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
        return float(result)

    value = visit(tree.body)
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
    for template in list(code.filter_templates(recursive=False)):
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


def interpret(text, page_title):
    from scripts.drops.drops_wikitext import collect_page_vars

    # The wikitext tokenizer otherwise mistakes <10 ... >50 for an HTML tag
    # spanning nested conditions. Encode comparison tokens before tokenizing.
    text = re.sub(
        r"(#ifexpr:[^|]*?)(<=|>=|<|>)", lambda m: m[1] + html.escape(m[2]), text
    )
    variables = collect_page_vars(text)

    def render(value, depth=0):
        if depth > 32:
            raise ValueError("Cyclic included drop variable")
        code = mwparserfromhell.parse(value)
        for t in list(code.filter_templates(recursive=False)):
            name = str(t.name).strip()
            key, _, argument = name.partition(":")
            key = key.lower()
            args = [str(p.value) for p in t.params]
            result = None
            if key in ("#vardefine", "#vardefineecho"):
                result = ""
            elif key == "#var":
                if argument.strip().lower() in variables:
                    result = render(variables[argument.strip().lower()], depth + 1)
            elif key == "pagename":
                result = page_title
            elif key == "#expr":
                try:
                    result = number(render(argument, depth + 1))
                except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
                    pass
            elif key == "min" or key == "max":
                try:
                    result = number(
                        key + "(" + ",".join(render(a, depth + 1) for a in args) + ")"
                    )
                except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
                    pass
            elif key == "#ifexpr":
                try:
                    truth = (
                        float(number(html.unescape(render(argument, depth + 1)))) != 0
                    )
                except (
                    ValueError,
                    SyntaxError,
                    ZeroDivisionError,
                    OverflowError,
                ) as exc:
                    raise ValueError("Unresolved included drop condition") from exc
                result = render(
                    (
                        args[0]
                        if truth and args
                        else args[1] if not truth and len(args) > 1 else ""
                    ),
                    depth + 1,
                )
            elif key == "#switch":
                selected = render(argument, depth + 1).strip()
                default = ""
                for p in t.params:
                    case = str(p.name).strip()
                    if case == "#default":
                        default = str(p.value)
                    if case == selected:
                        result = render(str(p.value), depth + 1)
                        break
                if result is None:
                    result = render(default, depth + 1)
            if result is None:
                for p in t.params:
                    p.value = render(str(p.value), depth + 1)
            else:
                code.replace(t, result)
        return str(code)

    output = render(text)
    for t in mwparserfromhell.parse(output).filter_templates():
        if str(t.name).strip().lower() in ("dropsline", "dropslineclue"):
            for p in t.params:
                if str(p.name).strip().lower() in (
                    "quantity",
                    "rarity",
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
