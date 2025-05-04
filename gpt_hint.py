# gpt_hint.py
import openai
import os
from dotenv import load_dotenv

# 必要に応じて load_dotenv() で環境変数を読み込む（.env ファイルがある場合）
load_dotenv()

# 既に環境変数から API キーを読み込む場合は、この行は不要
openai.api_key = os.getenv("OPENAI_API_KEY")

def get_ai_hint(user_code: str, problem_statement: str, input_example: str, output_example: str, error_message: str = "") -> str:
    """
    ユーザーのコード、問題文、入力例、出力例、エラー内容を元に、AI にヒントを出してもらう関数
    """
    system_prompt = (
        "あなたはプログラミング学習をサポートするAIアシスタントです。"
        "コードの誤りがあっても、直接答えを丸ごと提供せず、"
        "あくまでヒントだけを短めに出してください。"
        "答えにたどり着くための考え方を示唆する程度で、"
        "修正方法をズバリ書かないでください。"
    )

    user_prompt = f"""\ 
    【問題文】
    {problem_statement}
    
    【入力例】
    {input_example}
    
    【出力例】
    {output_example}
    
    【ユーザーのコード】
    ```python
    {user_code}
    【エラーや実行結果】
    {error_message}
    
    【要望】 コードの誤りを直接書かず、考え方や注意点を示唆する形で教えてください。詳しい修正コードは提示せず、ユーザーが自力で修正を思いつけるようアドバイスだけお願いします。"""
    response = openai.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    temperature=0.7,
    max_tokens=300,
    )
    return response.choices[0].message.content

def get_wrong_answer(user_code: str, problem_statement: str, input_example: str, output_example: str, error_message: str = "") -> str:
    """
    ユーザーのコードや問題文などを元に、AIに警告アンサー（注意点を示す）を出してもらう関数
    """
    system_prompt = ( 
        "あなたはプログラミング学習をサポートするAIアシスタントです。"
        "コードの誤りを直接修正コードとして提示せず、"
        "ユーザーが自力で修正案を思いつくための考え方や注意点を、ヒントとして簡潔に示してください。"
    )

    user_prompt = f"""\ 
    【問題文】
    {problem_statement}

    【入力例】
    {input_example}

    【出力例】
    {output_example}

    【ユーザーのコード】
    {user_code}

    【エラーや実行結果】
    {error_message}

    【要望】 コードの誤りを直接修正コードとして提示せず、警告として注意すべき点や考え方を短く示してください。"""
    response = openai.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    temperature=0.7,
    max_tokens=300,
    )
    return response.choices[0].message.content

def get_forbidden_hint(user_code: str, forbidden_op: str) -> str:
    """
    禁止された操作 (forbidden_op) をユーザーコード内で検出したとき、 なぜ禁止されているのか・どんなリスクがあるのか・代替手段は何かを GPT に説明してもらうための関数。
    """
    system_prompt = (
        "あなたはプログラミング学習をサポートするAIアシスタントです。"
        "禁止されている操作を使おうとしているユーザーに、セキュリティや学習上の理由を簡潔に示唆し、"
        "代わりにどうするのが望ましいかヒントを短めに教えてください。"
        "修正コードを丸ごと書くのではなく、考え方を示すに留めてください。"
    )

    user_prompt = f"""\ 
    【禁止された操作】
    {forbidden_op}
    【ユーザーのコード】
    {user_code}
    【要望】 なぜこの操作が禁止されているのか、どのようなリスクがあるのか、 また代わりにどのようなアプローチがあるかを、短いヒントとして教えてください。 修正コードは直接書かずに、考え方や注意点を示唆する形でお願いします。 """

    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=300,
    )
    return response.choices[0].message.content