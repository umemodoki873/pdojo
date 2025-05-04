# run_code.py
import os
import subprocess
import tempfile
import py_compile
import re

def extract_relevant_error(stderr):
    """
    VS Code や debugpy の長いスタックトレースから、
    一時ファイル（.tmp など）と実際のエラー箇所だけを抽出する
    """
    lines = stderr.strip().split("\n")
    start_index = 0
    pattern = re.compile(r'File ".*tmp.*\.(?:py|tmp)"')
    for i, line in enumerate(lines):
        if pattern.search(line):
            start_index = i
    relevant_lines = lines[start_index:]
    if not relevant_lines:
        relevant_lines = lines
    return "\n".join(relevant_lines)

def check_syntax(user_code):
    """
    ユーザーコードの構文チェックを行う。
    一時ファイルの拡張子は .tmp とすることで VS Code の影響を避ける。
    構文エラーがあればエラーメッセージを返し、問題なければ None を返す。
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tmp', delete=False) as tmp:
        tmp.write(user_code)
        tmp_filename = tmp.name

    try:
        py_compile.compile(tmp_filename, doraise=True)
        return None
    except py_compile.PyCompileError as e:
        return str(e)
    finally:
        os.remove(tmp_filename)

def run_code(user_code, input_data):
    """
    ユーザーコードを一時ファイル（.tmp）に書き出して実行する。
    実行結果（stdout, stderr, returncode）を返す。
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tmp', delete=False) as tmp:
        tmp.write(user_code)
        tmp_filename = tmp.name

    try:
        result = subprocess.run(
            ["python", tmp_filename],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=5  # タイムアウト 5秒
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Time Limit Exceeded", -1
    finally:
        os.remove(tmp_filename)
