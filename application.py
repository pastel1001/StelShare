# 1. DB 모델 수정
class Giveaway(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    giver_id = db.Column(db.String(50), nullable=False)
    image_url = db.Column(db.String(200))
    member_tag = db.Column(db.String(50)) # 대상 멤버
    min_months = db.Column(db.Integer, default=1) # 팔로우/구독 개월 수 (필수)
    require_comment = db.Column(db.Boolean, default=False) # 주접글 작성 여부 (True: 필수, False: 없음)
    end_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='진행중')
    winner_id = db.Column(db.String(50))

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    giveaway_id = db.Column(db.Integer, db.ForeignKey('giveaway.id'), nullable=False)
    applicant_id = db.Column(db.String(50), nullable=False)
    x_nickname = db.Column(db.String(50), nullable=False) # X(트위터) 닉네임 추가
    comment = db.Column(db.Text) # 주접글 내용
    proof_image = db.Column(db.String(200))

# 2. 나눔 조건 수정 라우트 추가
@app.route('/giveaway/<int:id>/edit_conditions', methods=['POST'])
def edit_conditions(id):
    giveaway = Giveaway.query.get_or_404(id)
    # 등록자 본인만 수정 가능
    user_id = session.get('user_id')
    if giveaway.giver_id == user_id and giveaway.status == '진행중':
        giveaway.min_months = int(request.form.get('min_months', 1))
        giveaway.require_comment = (request.form.get('require_comment') == 'true')
        db.session.commit()
    return redirect(url_for('detail', id=id))

# 3. 나눔 신청 라우트 수정 (X 닉네임 수집)
@app.route('/giveaway/<int:id>/apply', methods=['POST'])
def apply(id):
    giveaway = Giveaway.query.get_or_404(id)
    x_nickname = request.form.get('x_nickname') # X 닉네임
    comment = request.form.get('comment', '')
    
    # 신청 저장 로직에 x_nickname 반영
    new_app = Application(
        giveaway_id=id,
        applicant_id=session.get('user_id'),
        x_nickname=x_nickname,
        comment=comment
    )
    db.session.add(new_app)
    db.session.commit()
    return redirect(url_for('detail', id=id))
