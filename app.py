# app.py
from flask import Flask, request, render_template, redirect, url_for, flash, abort, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from run_code import extract_relevant_error, check_syntax, run_code, check_forbidden_operations
from gpt_hint import get_ai_hint, get_wrong_answer, get_forbidden_hint
import os
from datetime import datetime, timezone
from sqlalchemy import distinct

app = Flask(__name__)

app.jinja_env.globals.update(enumerate=enumerate)

app.secret_key = "your_secret_key"  # セッション用の秘密鍵。実際は安全な値にしてください。

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, '/data/pdojo.sqlite3')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # ユーザーがログインしていればそのID、匿名の場合はNULLにしておく
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    # 'problem' または 'hint' といった対象のタイプ
    target_type = db.Column(db.String(50), nullable=False)
    # 対象のID（問題IDやヒントID）
    target_id = db.Column(db.Integer, nullable=False)
    # フィードバックの種類："good" または "bad"
    feedback = db.Column(db.String(10), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True)
    password_hash = db.Column(db.String(256))
    free_hints_used = db.Column(db.Integer, default=0)   # 当日の無料ヒント利用回数
    purchased_hints = db.Column(db.Integer, default=0)     # 追加購入したヒントの回数
    last_hint_reset = db.Column(db.DateTime, default=datetime.now(timezone.utc))  # 最後に無料ヒント回数がリセットされた日時

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def reset_free_hints(self):
        self.free_hints_used = 0
        self.last_hint_reset = datetime.now(timezone.utc)

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    problem_id = db.Column(db.Integer, nullable=False)  # 提出された問題のID
    submission_time = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    status = db.Column(db.String(50))  # "Accepted", "Wrong Answer", "Error"など
    code = db.Column(db.Text)          # ユーザーが提出したコード
    hint = db.Column(db.Text)          # GPTから得たヒント

class Problem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    # 必要に応じて難易度やカテゴリなどのカラムを追加
    # e.g. difficulty = db.Column(db.String(50)), category = db.Column(db.String(100))

    def __repr__(self):
        return f"<Problem {self.title}>"
    
class TestCase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    problem_id = db.Column(db.Integer, db.ForeignKey('problem.id'), nullable=False)
    input_data = db.Column(db.Text, nullable=True)
    expected_output = db.Column(db.Text, nullable=True)

    problem = db.relationship('Problem', backref=db.backref('test_cases', lazy=True))

with app.app_context():
    db.create_all()
    if not Problem.query.first():
        p1 = Problem(
            title="Hello World",
            description="画面に「Hello, World!」と出力するプログラムを作成してください。"
        )
        db.session.add(p1)
        db.session.commit()

        t1 = TestCase(problem_id=p1.id, input_data="", expected_output="Hello, World!\n")
        db.session.add(t1)

        p2 = Problem(
            title="Sum Two Numbers",
            description="2つの整数を入力として受け取り、その和を出力するプログラムを作成してください。"
        )
        db.session.add(p2)
        db.session.commit()

        t2_1 = TestCase(problem_id=p2.id, input_data="2 3\n", expected_output="5\n")
        t2_2 = TestCase(problem_id=p2.id, input_data="10 20\n", expected_output="30\n")
        db.session.add_all([t2_1, t2_2])
        db.session.commit()

def admin_required(func):
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.username != 'admin':
            abort(403)
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

@app.route('/admin/problems')
@admin_required
def admin_problems():
    all_problems = Problem.query.all()
    return render_template('admin_problems.html', problems=all_problems)

@app.route('/feedback', methods=['POST'])
@login_required  # ログインしていないと送信できないようにする
def submit_feedback():
    target_type = request.form.get('target_type')
    target_id = request.form.get('target_id')
    feedback_value = request.form.get('feedback')  # "good" または "bad"

    if target_type not in ['problem', 'hint'] or feedback_value not in ['good', 'bad']:
        abort(400)

    try:
        target_id = int(target_id)
    except (ValueError, TypeError):
        abort(400)

    new_feedback = Feedback(
        user_id=current_user.id,
        target_type=target_type,
        target_id=target_id,
        feedback=feedback_value
    )
    db.session.add(new_feedback)
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/admin/problems/add', methods=['GET', 'POST'])
@admin_required
def admin_add_problem():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']

        if not title or not description:
            flash('タイトルと説明文は必須です。')
            return redirect(request.url)
        
        new_problem = Problem(title=title, description=description)
        db.session.add(new_problem)
        db.session.commit()
        
        for i in range(1, 4):
            input_key = f'input_data{i}'
            expected_output_key = f'expected_output{i}'

            input_data = request.form.get(input_key, '').strip()
            expected_output = request.form.get(expected_output_key, '').strip()

            if i == 1 and not expected_output:
                flash(f'テストケース1は必須です。')
                return redirect(request.url)

            if input_data or expected_output:
                testcase = TestCase(
                    problem_id=new_problem.id,
                    input_data=input_data,
                    expected_output=expected_output
                )
                db.session.add(testcase)
        db.session.commit()

        flash('問題を追加しました。')
        return redirect(url_for('admin_problems'))

    return render_template('admin_add_problem.html')

# 問題編集
@app.route('/admin/problems/edit/<int:problem_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_problem(problem_id):
    problem = Problem.query.get_or_404(problem_id)
    if request.method == 'POST':
        # 問題のタイトルと説明を更新
        problem.title = request.form['title']
        problem.description = request.form['description']

        # 既存のテストケースを一旦削除し、新しいデータを登録
        TestCase.query.filter_by(problem_id=problem_id).delete()

        for i in range(1, 4):
            input_data = request.form.get(f'input_data{i}', '').strip()
            expected_output = request.form.get(f'expected_output{i}', '').strip()

            # テストケース1は必須
            if i == 1 and not expected_output:
                flash('テストケース1は必須です。')
                return redirect(request.url)

            if input_data or expected_output:
                new_testcase = TestCase(
                    problem_id=problem_id,
                    input_data=input_data,
                    expected_output=expected_output
                )
                db.session.add(new_testcase)

        db.session.commit()
        flash('問題を更新しました。')
        return redirect(url_for('admin_problems'))

    return render_template('admin_edit_problem.html', problem=problem)

# 問題削除
@app.route('/admin/problems/delete/<int:problem_id>', methods=['POST'])
@admin_required
def admin_delete_problem(problem_id):
    problem = Problem.query.get_or_404(problem_id)
    # 関連するテストケースも削除
    TestCase.query.filter_by(problem_id=problem_id).delete()
    db.session.delete(problem)
    db.session.commit()
    flash('問題を削除しました。')
    return redirect(url_for('admin_problems'))

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (ValueError, TypeError):
        return None
    
@app.route('/support')
def support():
    # support.html を templates フォルダに置いておく
    return render_template('support.html')

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user_exists = User.query.filter_by(username=username).first()
        if user_exists:
            flash('ユーザー名は既に使われています。')
            return redirect(url_for('register'))

        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash('ユーザー登録が完了しました。ログインしてください。')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))  # ログイン成功後、トップに戻す
        else:
            flash('ログインに失敗しました。ユーザー名またはパスワードが間違っています。')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/problems')
def show_problems():
    all_problems = Problem.query.all()
    return render_template('problems.html', problems=all_problems)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# 他のルートで @login_required を利用すると、認証が必要なページになります。

@app.route('/')
def index():
    all_problems = Problem.query.all()
    solved_problems_ids = set()
    if current_user.is_authenticated:
        solved = db.session.query(distinct(Submission.problem_id)).filter_by(
            user_id=current_user.id, status="Accepted"
        ).all()
        # solved は [(1,), (3,), ...] のようなタプルのリストになるので、setに変換
        solved_problems_ids = {pid for (pid,) in solved}
    return render_template('index.html', problems=all_problems, current_user=current_user, solved_problems_ids=solved_problems_ids)


@app.route('/problem/<int:problem_id>')
def problem(problem_id):
    problem = Problem.query.get_or_404(problem_id)
    # GETの場合は hint_prompt を空文字列にしておく
    return render_template('problem.html', problem=problem, problem_id=problem.id, user_code="", hint_params={})

@app.route('/submit/<int:problem_id>', methods=['POST'])
def submit(problem_id):
    problem = Problem.query.get_or_404(problem_id)

    user_code = request.form['code']
    results = []
    all_passed = True
    hint_params = {}  # ヒント生成に使うパラメータを保持する辞書
    hint_prompt = None  # ヒント取得を促すメッセージを保持する変数
    # 静的チェックを実行
    forbidden = check_forbidden_operations(user_code)
    if forbidden:
        error_type, message = forbidden
        hint_prompt = "禁止操作が検出されました。ヒントをもらいますか？"
        hint_params = {
            "error_type": error_type,
            "error_message": message,
            "user_code": user_code,
            "problem_description": problem.description
        }
        result = {
            "input": "",
            "expected": "",
            "output": "",
            "error": message,
            "status": error_type  # Forbidden Command, File Operation, or Exit Function
        }
        results.append(result)
        all_passed = False
    else:
        # 各テストケースについて実行
        for test in problem.test_cases:
            input_data = test.input_data
            expected_output = test.expected_output

            try:
                stdout, stderr, returncode = run_code(user_code, input_data)
            except MemoryError:
                stdout, stderr, returncode = "", "Memory Overuse", -1

            # スタックトレースからユーザーコード関連部分だけを抽出
            short_stderr = extract_relevant_error(stderr)
            stdout_norm = stdout.strip()
            expected_norm = expected_output.strip()

            if short_stderr:
                if not hint_params:
                    hint_prompt = "エラーが発生しました。ヒントをもらいますか？"
                    hint_params = {
                        "error_type": "Error",
                        "error_message": short_stderr,
                        "user_code": user_code,
                        "problem_description": problem.description,
                        "input_example": input_data,
                        "output_example": expected_output
                    }
                result = {
                    "input": input_data,
                    "expected": expected_output,
                    "output": stdout,
                    "error": short_stderr,
                    "status": "Error"
                }
                all_passed = False
            elif stdout_norm != expected_norm:
                if not hint_params:
                    hint_prompt = "不正解でした。ヒントをもらいますか？"
                    hint_params = {
                        "error_type": "Wrong Answer",
                        "error_message": f"Expected: {expected_norm}\nGot: {stdout_norm}",
                        "user_code": user_code,
                        "problem_description": problem.description,
                        "input_example": input_data,
                        "output_example": expected_output
                    }
                result = {
                    "input": input_data,
                    "expected": expected_output,
                    "output": stdout,
                    "error": "",
                    "status": "Wrong Answer"
                }
                all_passed = False
            else:
                result = {
                    "input": input_data,
                    "expected": expected_output,
                    "output": stdout,
                    "error": "",
                    "status": "Accepted"
                }
            results.append(result)

    overall = "Accepted" if all_passed else "Failed"

    # ループ終了後、全体の判定を得た後
    if current_user.is_authenticated:
        new_submission = Submission(
            user_id=current_user.id,
            problem_id=problem_id,
            submission_time=datetime.now(timezone.utc),
            status=overall,
            code=user_code,
            hint=hint_prompt if hint_prompt else ""
        )
        db.session.add(new_submission)
        db.session.commit()
    return render_template('problem.html', problem=problem, problem_id=problem_id, results=results, overall=overall, user_code=user_code, hint_prompt=hint_prompt, hint_params=hint_params)

@app.route('/use_hint', methods=['POST'])
@login_required
def use_hint_route():
    # フォームから必要なパラメータを取得
    problem_id = request.form.get('problem_id')
    code = request.form.get('code')
    error_type = request.form.get('error_type', '')  # 例: "Forbidden", "Error", "Wrong Answer"
    error_message = request.form.get('error_message', '')
    app.logger.info("Received code for hint: %s", code)
    # problem_idから問題を取得
    problem = db.session.get(Problem, problem_id)
    if not problem:
        return jsonify({"status": "failed", "message": "問題が見つかりません。"}), 404

    # ここで実際の問題の説明を取得する
    problem_description = problem.description

    try:    
        if error_type == 'Forbidden':
            hint_text = get_forbidden_hint(code, error_message)
        elif error_type in ['Error', 'Wrong Answer']:
            wrong_answer_info = f"Error Details: {error_message}"
            hint_text = get_wrong_answer(code, problem_description, "", "", wrong_answer_info)
        else:
            hint_text = get_ai_hint(code, problem_description, "", "", error_message)

        return jsonify({"status": "success", "hint": hint_text})

    except Exception as e:
        error_msg = str(e)
        app.logger.error("Hint generation failed: %s", error_msg)

        # 💡 quota or 残高不足っぽい文言なら「quota」コードを返す
        if "quota" in error_msg or "insufficient" in error_msg or "billing" in error_msg:
            return jsonify({
                "status": "error",
                "code": "quota",
                "message": "GPT APIの残高が不足している可能性があります。"
            })

        # その他のエラー
        return jsonify({
            "status": "error",
            "code": "other",
            "message": "ヒントの生成に失敗しました。"
        })

@app.route('/submissions')
@login_required
def submissions():
    submissions = Submission.query.filter_by(user_id=current_user.id).order_by(Submission.submission_time.desc()).all()
    return render_template('submissions.html', submissions=submissions)

@app.route('/submission/<int:submission_id>')
@login_required
def submission_detail(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    # 自分の提出でなければアクセスを拒否
    if submission.user_id != current_user.id:
        abort(403)
    return render_template('submission_detail.html', submission=submission)

def can_use_hint(user):
    # ユーザーの無料ヒント利用状況を日付でリセットする処理
    now = datetime.now(timezone.utc)
    if user.last_hint_reset.date() < now.date():
        user.reset_free_hints()
        db.session.commit()
    
    total_available = (3 - user.free_hints_used) + user.purchased_hints
    return total_available > 0

def use_hint(user):
    """
    ユーザーがヒントを利用する場合の処理。
    利用可能なら、無料ヒントが残っていればそれを使い、
    なくなっている場合は購入済みヒントを消費する。
    利用可能なヒントがなければFalseを返す。
    """
    now = datetime.now(timezone.utc)
    if user.last_hint_reset.date() < now.date():
        user.reset_free_hints()
        db.session.commit()

    # 無料ヒント利用枠
    free_remaining = 3 - user.free_hints_used

    if free_remaining > 0:
        user.free_hints_used += 1
        db.session.commit()
        return True
    elif user.purchased_hints > 0:
        user.purchased_hints -= 1
        db.session.commit()
        return True
    else:
        return False

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
