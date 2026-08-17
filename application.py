import os
import random
import json
import urllib.parse
import urllib.request
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'stel_secret_key_1234'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = 'uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db = SQLAlchemy(app)

# ---------------------------------------------------------
# 스텔라이브 멤버 11명 정의
# ---------------------------------------------------------
STELLIVE_MEMBERS = [
    "스텔라이브 전체",
    "강칸나",
    "아야츠노 유니",
    "시라유키 히나",
    "네코야마 세나",
    "아카네 리제",
    "아라하시 타비",
    "텐코 시부키",
    "아오구모 린",
    "하나코 나나",
    "유즈하 리코"
]

# 네이버 OAuth 설정
NAVER_CLIENT_ID = "YOUR_NAVER_CLIENT_ID"
NAVER_CLIENT_SECRET = "YOUR_NAVER_CLIENT_SECRET"
NAVER_REDIRECT_URI = "http://127.0.0.1:5000/login/naver/callback"

# ---------------------------------------------------------
# 데이터베이스 모델
# ---------------------------------------------------------
class Giveaway(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    image_url = db.Column(db.String(200))
    giver_id = db.Column(db.String(50), nullable=False)
    target_member = db.Column(db.String(50), nullable=False, default="스텔라이브 전체")
    min_months = db.Column(db.Integer, default=1, nullable=False)
    require_comment = db.Column(db.Boolean, default=False)
    end_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='진행중')
    winner_id = db.Column(db.String(50))

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    giveaway_id = db.Column(db.Integer, db.ForeignKey('giveaway.id'), nullable=False)
    applicant_id = db.Column(db.String(50), nullable=False)
    x_nickname = db.Column(db.String(50), nullable=False)
    chzzk_nickname = db.Column(db.String(50), nullable=False)
    chzzk_proof_image = db.Column(db.String(200))
    is_student = db.Column(db.Boolean, default=False)
    proof_image = db.Column(db.String(200))
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

    giveaway = db.relationship('Giveaway', backref=db.backref('applications', lazy=True))

# ---------------------------------------------------------
# 자동 당첨자 추첨 로직
# ---------------------------------------------------------
def check_and_draw_winners():
    now = datetime.now()
    expired_giveaways = Giveaway.query.filter(Giveaway.end_date <= now, Giveaway.status == '진행중').all()
    
    for giveaway in expired_giveaways:
        applications = Application.query.filter_by(giveaway_id=giveaway.id).all()
        if applications:
            winner = random.choice(applications)
            giveaway.winner_id = f"{winner.applicant_id} (X: {winner.x_nickname})"
        else:
            giveaway.winner_id = "신청자 없음"
        giveaway.status = '마감'
    db.session.commit()

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ---------------------------------------------------------
# 네이버 로그인 라우트 (파이썬 기본 내장 모듈 사용)
# ---------------------------------------------------------
@app.route('/login/naver')
def naver_login():
    state = "random_state_string"
    session['state'] = state
    naver_url = (
        f"https://nid.naver.com/oauth2.0/authorize?response_type=code"
        f"&client_id={NAVER_CLIENT_ID}&redirect_uri={urllib.parse.quote(NAVER_REDIRECT_URI)}&state={state}"
    )
    return redirect(naver_url)

@app.route('/login/naver/callback')
def naver_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    
    token_url = (
        f"https://nid.naver.com/oauth2.0/token?grant_type=authorization_code"
        f"&client_id={NAVER_CLIENT_ID}&client_secret={NAVER_CLIENT_SECRET}"
        f"&code={code}&state={state}"
    )
    
    try:
        req = urllib.request.Request(token_url)
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode())
        access_token = res.get('access_token')

        if access_token:
            profile_req = urllib.request.Request(
                "https://openapi.naver.com/v1/nid/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            with urllib.request.urlopen(profile_req) as profile_res_raw:
                profile_res = json.loads(profile_res_raw.read().decode())

            if profile_res.get('resultcode') == '00':
                user_data = profile_res.get('response')
                session['user_id'] = user_data.get('id', user_data.get('email', 'naver_user'))
                session['user_name'] = user_data.get('nickname', user_data.get('name', '네이버 유저'))
                session['login_type'] = 'naver'
                flash(f"네이버 계정({session['user_id']})으로 로그인되었습니다.")
                return redirect(url_for('index'))
    except Exception as e:
        print("네이버 로그인 오류:", e)

    flash("네이버 로그인 실패")
    return redirect(url_for('index'))

@app.route('/login/mock/<naver_id>')
def mock_login(naver_id):
    session['user_id'] = naver_id
    session['user_name'] = f"스텔파더_{naver_id}"
    session['login_type'] = 'naver'
    flash(f"네이버 아이디 '{naver_id}'(으)로 로그인되었습니다.")
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash("로그아웃되었습니다.")
    return redirect(url_for('index'))

# ---------------------------------------------------------
# 일반 라우트
# ---------------------------------------------------------
@app.route('/')
def index():
    check_and_draw_winners()
    giveaways = Giveaway.query.order_by(Giveaway.id.desc()).all()
    return render_template('index.html', giveaways=giveaways)

@app.route('/create', methods=['GET', 'POST'])
def create():
    if 'user_id' not in session:
        flash("로그인이 필요한 서비스입니다.")
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form.get('title')
        target_member = request.form.get('target_member', '스텔라이브 전체')
        min_months = int(request.form.get('min_months', 1))
        require_comment = (request.form.get('require_comment') == 'true')
        end_date_str = request.form.get('end_date')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%dT%H:%M')
        
        file = request.files.get('image')
        image_url = ''
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = f"/uploads/{filename}"

        new_giveaway = Giveaway(
            title=title,
            image_url=image_url,
            giver_id=session['user_id'],
            target_member=target_member,
            min_months=min_months,
            require_comment=require_comment,
            end_date=end_date
        )
        db.session.add(new_giveaway)
        db.session.commit()
        flash("나눔 물품이 등록되었습니다!")
        return redirect(url_for('index'))
    
    return render_template('create.html', members=STELLIVE_MEMBERS)

@app.route('/giveaway/<int:id>')
def detail(id):
    check_and_draw_winners()
    giveaway = Giveaway.query.get_or_404(id)
    applications = Application.query.filter_by(giveaway_id=id).all()
    return render_template('detail.html', giveaway=giveaway, applications=applications)

@app.route('/giveaway/<int:id>/apply', methods=['POST'])
def apply(id):
    if 'user_id' not in session:
        flash("로그인 후 신청할 수 있습니다.")
        return redirect(url_for('detail', id=id))

    giveaway = Giveaway.query.get_or_404(id)
    if giveaway.status != '진행중':
        flash("이미 마감된 나눔입니다.")
        return redirect(url_for('detail', id=id))

    x_nickname = request.form.get('x_nickname')
    chzzk_nickname = request.form.get('chzzk_nickname')
    is_student = (request.form.get('user_type') == 'student')
    comment = request.form.get('comment', '')

    chzzk_proof = request.files.get('chzzk_proof_image')
    chzzk_proof_url = ''
    if chzzk_proof and chzzk_proof.filename != '':
        filename = secure_filename(chzzk_proof.filename)
        chzzk_proof.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        chzzk_proof_url = f"/uploads/{filename}"

    proof_image_url = ''
    file = request.files.get('proof_image')
    if is_student and file and file.filename != '':
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        proof_image_url = f"/uploads/{filename}"

    new_app = Application(
        giveaway_id=id,
        applicant_id=session['user_id'],
        x_nickname=x_nickname,
        chzzk_nickname=chzzk_nickname,
        chzzk_proof_image=chzzk_proof_url,
        is_student=is_student,
        proof_image=proof_image_url,
        comment=comment
    )
    db.session.add(new_app)
    db.session.commit()
    flash('나눔 신청이 성공적으로 제출되었습니다!')
    return redirect(url_for('detail', id=id))

@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        flash("마이페이지에 접근하려면 로그인이 필요합니다.")
        return redirect(url_for('index'))

    user_id = session['user_id']
    my_giveaways = Giveaway.query.filter_by(giver_id=user_id).order_by(Giveaway.id.desc()).all()
    my_applications = Application.query.filter_by(applicant_id=user_id).order_by(Application.id.desc()).all()
    return render_template('mypage.html', my_giveaways=my_giveaways, my_applications=my_applications)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
