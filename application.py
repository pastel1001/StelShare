import os
import random
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "stellive_giveaway_secret_key"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 최대 16MB 파일 업로드

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db = SQLAlchemy(app)

# ================= 데이터베이스 모델 정의 =================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    naver_id = db.Column(db.String(100), unique=True, nullable=False)
    nickname = db.Column(db.String(50), nullable=False)
    is_student = db.Column(db.Boolean, default=True)      # 학생 여부
    sub_months = db.Column(db.Integer, default=0)         # 구독 개월 수 (네이버 API 연동 시 동기화)
    is_following = db.Column(db.Boolean, default=False)    # 치지직 팔로우 여부

class Giveaway(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    giver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    image_url = db.Column(db.String(200), nullable=False)
    member_tag = db.Column(db.String(50), nullable=False)
    giveaway_type = db.Column(db.String(20), nullable=False)  # '현장' 또는 '통판'
    condition_type = db.Column(db.String(20), nullable=False) # 'follow'(학생), 'sub'(성인), 'praise'(주접글)
    min_sub_months = db.Column(db.Integer, default=0)        # 성인 조건: 최소 구독 개월
    end_date = db.Column(db.DateTime, nullable=False)        # 마감 기간
    status = db.Column(db.String(20), default="진행중")       # '진행중', '마감', '발송완료'
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    giveaway_id = db.Column(db.Integer, db.ForeignKey('giveaway.id'), nullable=False)
    applicant_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    fan_text = db.Column(db.Text, nullable=True)               # 주접글 내용
    cert_image_url = db.Column(db.String(200), nullable=True)  # 학생증 인증 이미지
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default="대기중")        # '대기중', '당첨', '탈락'

# ================= 라우트 로직 =================
@app.route('/')
def index():
    # 마감 기한 체크 및 자동 추첨 실행
    check_and_draw_winners()
    giveaways = Giveaway.query.order_by(Giveaway.id.desc()).all()
    return render_template('index.html', giveaways=giveaways)

# 네이버 가상 로그인 (테스트용)
@app.route('/login/naver')
def login_naver():
    # 실제 네이버 API 연동 시 Access Token으로 구독/팔로우 정보 수집
    user = User.query.filter_by(naver_id="test_naver_user").first()
    if not user:
        user = User(naver_id="test_naver_user", nickname="파스텔1호", is_student=True, sub_months=3, is_following=True)
        db.session.add(user)
        db.session.commit()
    session['user_id'] = user.id
    flash("네이버 계정으로 로그인되었습니다.")
    return redirect(url_for('index'))

# [나눔하는 사람] 나눔 물품 등록
@app.route('/create', methods=['GET', 'POST'])
def create():
    if 'user_id' not in session:
        flash("로그인이 필요합니다.")
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        file = request.files['image']
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%dT%H:%M')
        
        new_giveaway = Giveaway(
            giver_id=session['user_id'],
            title=request.form['title'],
            image_url=filename,
            member_tag=request.form['member_tag'],
            giveaway_type=request.form['giveaway_type'],
            condition_type=request.form['condition_type'],
            min_sub_months=int(request.form.get('min_sub_months', 0)),
            end_date=end_date
        )
        db.session.add(new_giveaway)
        db.session.commit()
        return redirect(url_for('index'))
        
    return render_template('create.html')

# [나눔 신청하는 사람] 상세 보기 및 신청
@app.route('/giveaway/<int:id>', methods=['GET', 'POST'])
def detail(id):
    giveaway = Giveaway.query.get_or_404(id)
    user = User.query.get(session.get('user_id')) if 'user_id' in session else None
    
    # 조건 통과 여부 검증
    can_apply = False
    fail_reason = ""
    
    if user:
        if giveaway.condition_type == 'follow':
            if user.is_following:
                can_apply = True
            else:
                fail_reason = "치지직 팔로우 정보가 필요합니다."
        elif giveaway.condition_type == 'sub':
            if user.sub_months >= giveaway.min_sub_months:
                can_apply = True
            else:
                fail_reason = f"구독 기간이 부족합니다. (최소 {giveaway.min_sub_months}개월)"
        elif giveaway.condition_type == 'praise':
            can_apply = True

    if request.method == 'POST' and can_apply:
        cert_filename = None
        if 'cert_image' in request.files and request.files['cert_image'].filename != '':
            cert_file = request.files['cert_image']
            cert_filename = "cert_" + secure_filename(cert_file.filename)
            cert_file.save(os.path.join(app.config['UPLOAD_FOLDER'], cert_filename))

        application = Application(
            giveaway_id=giveaway.id,
            applicant_id=user.id,
            fan_text=request.form.get('fan_text'),
            cert_image_url=cert_filename
        )
        db.session.add(application)
        db.session.commit()
        flash("나눔 신청이 완료되었습니다!")
        return redirect(url_for('mypage'))

    return render_template('detail.html', giveaway=giveaway, user=user, can_apply=can_apply, fail_reason=fail_reason)

# 마이페이지
@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    user_id = session['user_id']
    my_applications = Application.query.filter_by(applicant_id=user_id).all()
    my_giveaways = Giveaway.query.filter_by(giver_id=user_id).all()
    return render_template('mypage.html', applications=my_applications, giveaways=my_giveaways)

# 자동 추첨 함수 (기한 만료 시)
def check_and_draw_winners():
    now = datetime.utcnow()
    expired_giveaways = Giveaway.query.filter(Giveaway.end_date <= now, Giveaway.status == "진행중").all()
    
    for giveaway in expired_giveaways:
        applicants = Application.query.filter_by(giveaway_id=giveaway.id).all()
        if applicants:
            winner_app = random.choice(applicants)
            winner_app.status = "당첨"
            giveaway.winner_id = winner_app.applicant_id
            giveaway.status = "마감"
            
            # 낙첨자 처리
            for app in applicants:
                if app.id != winner_app.id:
                    app.status = "탈락"
        else:
            giveaway.status = "마감 (신청자 없음)"
        db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)