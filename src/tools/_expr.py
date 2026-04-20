"""
受限的数学表达式求值工具。

LLM 经常需要传入 "x**2 + sin(x)" 这样的字符串表达式给数值积分、方程求解等工具。
直接 eval() 极度危险（任意代码执行），所以这里用白名单方式构造受限命名空间：
只允许 numpy 数学函数和基本运算符，不允许导入、属性访问等危险操作。
"""

import ast
import math
import numpy as np


_ALLOWED_FUNCS = {
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan,
    "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh,
    "exp": np.exp, "log": np.log, "log2": np.log2, "log10": np.log10,
    "sqrt": np.sqrt, "abs": np.abs,
    "floor": np.floor, "ceil": np.ceil, "round": np.round,
    "min": np.minimum, "max": np.maximum,
    "pow": np.power,
}

_ALLOWED_CONSTS = {
    "pi": math.pi,
    "e": math.e,
    "inf": math.inf,
}


_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name,
    ast.Call, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd,
)


def _validate(node: ast.AST, var_names: set[str]) -> None:
    """递归校验 AST，确保只包含安全节点。"""
    if not isinstance(node, _ALLOWED_NODES):
        raise ValueError(f"不允许的语法元素: {type(node).__name__}")

    if isinstance(node, ast.Name):
        if node.id not in var_names and node.id not in _ALLOWED_FUNCS and node.id not in _ALLOWED_CONSTS:
            raise ValueError(f"未知的标识符: {node.id}")

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            raise ValueError(f"不允许的函数调用: {ast.dump(node.func)}")

    for child in ast.iter_child_nodes(node):
        _validate(child, var_names)


def make_function(expr: str, var_names: list[str] = None):
    """把字符串表达式编译成可调用函数。

    Args:
        expr: 数学表达式，如 "x**2 + sin(x)"
        var_names: 自变量名列表，默认 ["x"]

    Returns:
        可调用对象 f(*args)，参数顺序与 var_names 一致

    Raises:
        ValueError: 表达式包含不允许的元素
        SyntaxError: 表达式语法错误
    """
    if var_names is None:
        var_names = ["x"]
    var_set = set(var_names)

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise SyntaxError(f"表达式语法错误: {e}") from e

    _validate(tree, var_set)
    code = compile(tree, "<expr>", "eval")

    namespace = {**_ALLOWED_FUNCS, **_ALLOWED_CONSTS, "__builtins__": {}}

    def func(*args):
        if len(args) != len(var_names):
            raise TypeError(f"期望 {len(var_names)} 个参数，得到 {len(args)}")
        local = {name: val for name, val in zip(var_names, args)}
        return eval(code, namespace, local)

    return func
