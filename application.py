import os
import random
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'stel_secret_key_1234'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = 'uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db = SQLAlchemy(app)

# ---------------------------------------------------------
# 데이터베이스 모델
# ---------------------------------------------------------
class Giveaway(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    image_url = db.Column(db.String(200))
    giver_id = db.Column(db.String(50), nullable=False)
    min_months = db.Column(db.Integer, default=1, nullable=False)  # 팔로우/구독 최소 개월 수 (필수)
    require_comment = db.Column(db.Boolean, default=False)        # 주접글 필수 여부 (True/False)
    end_date = db.Column(db.DateTime, nullable=False)             # 마감 기간
    status = db.Column(db.String(20), default='진행중')           # 진행중 / 마감
    winner_id = db.Column(db.String(50))                          # 당첨자 ID/닉네임

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    giveaway_id = db.Column(db.Integer, db.ForeignKey('giveaway.id'), nullable=False)
    applicant_id = db.Column(db.String(50), nullable=False)
    x_nickname = db.Column(db.String(50), nullable=False)         # 본인 X(트위터) 닉네임
    is_student = db.Column(db.Boolean, default=False)             # 학생 여부 (학생: 팔로우+학생증, 성인: 구독)
    proof_image = db.Column(db.String(200))                       # 학생증/인증샷 사진 경로
    comment = db.Column(db.Text)                                  # 주접글 내용
    created_at = db.Column(db.DateTime, default=datetime.now)

# ---------------------------------------------------------
# 자동 당첨자 추첨 로직
# ---------------------------------------------------------
def check_and_draw_winners():
    now = datetime.now()
    expired_giveaways = Giveaway.query.filter(Giveaway.end_date <= now, Giveaway.status == '진행중').all()
    
    for giveaway in expired_giveaways:
        applications = Application.query.filter_by(giveaway_id=giveaway.id).all()
        if applications:
            # 신청자 중 무작위 1명 추첨
            winner = random.choice(applications)
            giveaway.winner_id = f"{winner.applicant_id} (X: {winner.x_nickname})"
        else:
            giveaway.winner_id = "신청자 없음"
        giveaway.status = '마감'
    db.session.commit()

# ---------------------------------------------------------
# 라우트 (페이지 기능)
# ---------------------------------------------------------
@app.route('/')
def index():
    check_and_draw_winners()
    giveaways = Giveaway.query.order_by(Giveaway.id.desc()).all()
    return render_template('index.html', giveaways=giveaways)

# 나눔 물품 등록 (나눔하는 사람)
@app.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        title = request.form.get('title')
        min_months = int(request.form.get('min_months', 1))
        require_comment = (request.form.get('require_comment') == 'true')
        end_date_str = request.form.get('end_date')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%dT%H:%M')
        
        # 이미지 업로드
        file = request.files.get('image')
        image_url = ''
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = f"/uploads/{filename}"

        new_giveaway = Giveaway(
            title=title,
            image_url=image_url,
            giver_id=session.get('user_id', '익명나눔러'),
            min_months=min_months,
            require_comment=require_comment,
            end_date=end_date
        )
        db.session.add(new_giveaway)
        db.session.commit()
        return redirect(url_for('index'))
    
    return render_template('create.html')

# 상세 페이지 및 나눔 조건/기간 수정, 신청
@app.route('/giveaway/<int:id>')
def detail(id):
    check_and_draw_winners()
    giveaway = Giveaway.query.get_or_404(id)
    applications = Application.query.filter_by(giveaway_id=id).all()
    return render_template('detail.html', giveaway=giveaway, applications=applications)

# 조건 및 기간 수정하기 (나눔하는 사람 전용)
@app.route('/giveaway/<int:id>/edit', methods=['POST'])
def edit_giveaway(id):
    giveaway = Giveaway.query.get_or_404(id)
    if giveaway.giver_id == session.get('user_id', '익명나눔러') and giveaway.status == '진행중':
        giveaway.title = request.form.get('title')
        giveaway.min_months = int(request.form.get('min_months', 1))
        giveaway.require_comment = (request.form.get('require_comment') == 'true')
        end_date_str = request.form.get('end_date')
        if end_date_str:
            giveaway.end_date = datetime.strptime(end_date_str, '%Y-%m-%dT%H:%M')
        db.session.commit()
        flash('나눔 정보 및 조건이 수정되었습니다.')
    return redirect(url_for('detail', id=id))

# 나눔 신청하기 (나눔 신청하는 사람)
@app.route('/giveaway/<int:id>/apply', methods=['POST'])
def apply(id):
    giveaway = Giveaway.query.get_or_404(id)
    if giveaway.status != '진행중':
        return redirect(url_for('detail', id=id))

    x_nickname = request.form.get('x_nickname')
    is_student = (request.form.get('user_type') == 'student')
    comment = request.form.get('comment', '')

    # 네이버 연동 인증 확인 과정 (치지직 구독/팔로우 개월 수 연동 확인)
    # 네이버 API 연동 시 실제 개월 수 데이터와 giveaway.min_months 비교
    naver_sub_months = session.get('naver_sub_months', 3) # 예시 데이터
    if naver_sub_months < giveaway.min_months:
        flash(f'최소 {giveaway.min_months}개월 이상 팔로우/구독 회원만 신청할 수 있습니다.')
        return redirect(url_for('detail', id=id))

    # 학생일 경우 학생증 인증샷 업로드 필수
    proof_image = ''
    file = request.files.get('proof_image')
    if is_student and file and file.filename != '':
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        proof_image = f"/uploads/{filename}"

    new_app = Application(
        giveaway_id=id,
        applicant_id=session.get('user_id', '신청자'),
        x_nickname=x_nickname,
        is_student=is_student,
        proof_image=proof_image,
        comment=comment
    )
    db.session.add(new_app)
    db.session.commit()
    flash('나눔 신청이 완료되었습니다!')
    return redirect(url_for('detail', id=id))

# Gunicorn 배포 시 DB 테이블 자동 생성을 위한 설정
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
